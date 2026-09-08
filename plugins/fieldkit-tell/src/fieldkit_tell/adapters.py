from __future__ import annotations

import os
import math
import time
import uuid
from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

import httpx


class AdapterStatus(StrEnum):
    RAN = "ran"
    SKIPPED = "skipped"
    ERROR = "error"


@dataclass(frozen=True)
class DetectorRequest:
    text: str
    timeout: float = 20.0


@dataclass(frozen=True)
class DetectorSpan:
    start: int
    end: int
    score: float


@dataclass(frozen=True)
class DetectorResult:
    adapter: str
    display_name: str
    status: AdapterStatus
    ai_probability: float | None
    label: str
    spans: list[DetectorSpan]
    detail: str
    latency_ms: float


AdapterCall = Callable[
    ["Adapter", DetectorRequest, httpx.Client, Mapping[str, str]], DetectorResult
]


@dataclass(frozen=True)
class Adapter:
    name: str
    display_name: str
    env_vars: tuple[str, ...]
    min_chars: int
    max_chars: int
    call: AdapterCall


def run_detectors(
    text: str,
    *,
    offline: bool = True,
    include_ml: bool = False,
    timeout: float = 20.0,
    client: httpx.Client | None = None,
) -> list[DetectorResult]:
    """Run detectors in registry order; remote vendors require ``offline=False``."""

    if timeout <= 0:
        raise ValueError("timeout must be greater than zero")

    results: list[DetectorResult | None] = [None] * len(ADAPTERS)
    eligible: list[tuple[int, Adapter, dict[str, str]]] = []
    for index, adapter in enumerate(ADAPTERS):
        skipped, credentials = _preflight(adapter, text, offline=offline)
        if skipped is not None:
            results[index] = skipped
        else:
            eligible.append((index, adapter, credentials))

    owned_client = client is None and bool(eligible)
    active_client = (client or httpx.Client(timeout=timeout)) if eligible else None
    if active_client is not None:
        try:
            with ThreadPoolExecutor(max_workers=len(eligible)) as pool:
                futures = {
                    pool.submit(
                        _execute,
                        adapter,
                        DetectorRequest(text, timeout),
                        active_client,
                        credentials,
                    ): index
                    for index, adapter, credentials in eligible
                }
                for future in as_completed(futures):
                    results[futures[future]] = future.result()
        finally:
            if owned_client:
                active_client.close()

    ordered = [result for result in results if result is not None]
    if include_ml:
        from fieldkit_tell.ml import run_local_detector

        ordered.append(run_local_detector(text))
    return ordered


def active_remote_adapters(text: str, *, offline: bool = True) -> list[Adapter]:
    """Return eligible remote adapters only when ``offline=False`` is explicit."""

    return [
        adapter
        for adapter in ADAPTERS
        if _preflight(adapter, text, offline=offline)[0] is None
    ]


def adapter_is_keyed(adapter: Adapter) -> bool:
    """Report credential presence without revealing values or making a request."""

    return all(bool(os.environ.get(name)) for name in adapter.env_vars)


def _preflight(
    adapter: Adapter, text: str, *, offline: bool
) -> tuple[DetectorResult | None, dict[str, str]]:
    if offline:
        return _skipped(adapter, "offline mode"), {}

    credentials: dict[str, str] = {}
    for name in adapter.env_vars:
        value = os.environ.get(name)
        if not value:
            return _skipped(adapter, f"no {name} set"), {}
        credentials[name] = value
    if len(text) < adapter.min_chars:
        return _skipped(adapter, "text under vendor minimum"), {}
    if len(text) > adapter.max_chars:
        return _skipped(adapter, "text over vendor maximum"), {}
    return None, credentials


def _execute(
    adapter: Adapter,
    request: DetectorRequest,
    client: httpx.Client,
    credentials: Mapping[str, str],
) -> DetectorResult:
    started = time.perf_counter()
    try:
        result = adapter.call(adapter, request, client, credentials)
        return DetectorResult(
            adapter=result.adapter,
            display_name=result.display_name,
            status=result.status,
            ai_probability=result.ai_probability,
            label=result.label,
            spans=result.spans,
            detail=result.detail,
            latency_ms=round((time.perf_counter() - started) * 1000, 1),
        )
    except httpx.TimeoutException:
        detail = "request timed out"
    except httpx.HTTPStatusError as exc:
        detail = f"HTTP {exc.response.status_code}"
    except httpx.HTTPError as exc:
        detail = f"request failed: {_one_line(str(exc))}"
    except (KeyError, TypeError, ValueError) as exc:
        detail = f"unexpected payload: {_one_line(str(exc))}"
    return _error(adapter, detail, started)


def _call_pangram(
    adapter: Adapter,
    request: DetectorRequest,
    client: httpx.Client,
    credentials: Mapping[str, str],
) -> DetectorResult:
    headers = {"x-api-key": credentials["FIELDKIT_TELL_PANGRAM_KEY"]}
    response = client.post(
        "https://text.external-api.pangram.com/task",
        headers=headers,
        json={"text": request.text, "public_dashboard_link": False},
        timeout=request.timeout,
    )
    response.raise_for_status()
    payload = _json_object(response)
    if _has_pangram_score(payload):
        return _pangram_result(adapter, payload)

    task_id = _string(payload, "task_id")
    deadline = time.perf_counter() + request.timeout
    while time.perf_counter() < deadline:
        response = client.get(
            f"https://text.external-api.pangram.com/task/{task_id}",
            headers=headers,
            timeout=request.timeout,
        )
        response.raise_for_status()
        payload = _json_object(response)
        if _has_pangram_score(payload):
            return _pangram_result(adapter, payload)
        if payload.get("stage") == "STAGE_FAILED":
            raise ValueError(_label(payload, "headline") or "Pangram task failed")
        time.sleep(0.1)
    raise httpx.ReadTimeout("Pangram task did not finish", request=response.request)


def _pangram_result(adapter: Adapter, payload: dict[str, Any]) -> DetectorResult:
    # `ai_likelihood` is kept for the prior synchronous schema. The current API
    # returns `fraction_ai` after its task reaches STAGE_SUCCESS.
    score_field = "ai_likelihood" if "ai_likelihood" in payload else "fraction_ai"
    spans = _numeric_spans(
        payload.get("windows"),
        start_keys=("start_index", "start"),
        end_keys=("end_index", "end"),
        score_keys=("ai_assistance_score", "score"),
    )
    return _ran(
        adapter,
        _probability(payload[score_field]),
        _label(payload, "label", "prediction", "prediction_short", "headline"),
        spans=spans,
    )


def _call_gptzero(
    adapter: Adapter,
    request: DetectorRequest,
    client: httpx.Client,
    credentials: Mapping[str, str],
) -> DetectorResult:
    response = client.post(
        "https://api.gptzero.me/v2/predict/text",
        headers={"x-api-key": credentials["FIELDKIT_TELL_GPTZERO_KEY"]},
        json={"document": request.text},
        timeout=request.timeout,
    )
    response.raise_for_status()
    payload = _json_object(response)
    document = _object(_list(payload, "documents")[0], "documents[0]")
    probabilities = _object(document["class_probabilities"], "class_probabilities")
    spans = _numeric_spans(
        document.get("sentences"),
        start_keys=("start_index", "start"),
        end_keys=("end_index", "end"),
        score_keys=("generated_prob", "ai_probability", "score"),
    )
    return _ran(
        adapter,
        _probability(probabilities["ai"]),
        _label(document, "label", "predicted_class"),
        spans=spans,
    )


def _call_originality(
    adapter: Adapter,
    request: DetectorRequest,
    client: httpx.Client,
    credentials: Mapping[str, str],
) -> DetectorResult:
    response = client.post(
        "https://api.originality.ai/api/v1/scan/ai",
        headers={"X-OAI-API-KEY": credentials["FIELDKIT_TELL_ORIGINALITY_KEY"]},
        json={"content": request.text},
        timeout=request.timeout,
    )
    response.raise_for_status()
    payload = _json_object(response)
    score = _object(payload["score"], "score")
    return _ran(
        adapter,
        _probability(score["ai"]),
        _label(payload, "label", "prediction", "classification"),
    )


def _call_copyleaks(
    adapter: Adapter,
    request: DetectorRequest,
    client: httpx.Client,
    credentials: Mapping[str, str],
) -> DetectorResult:
    login = client.post(
        "https://id.copyleaks.com/v3/account/login/api",
        json={
            "email": credentials["FIELDKIT_TELL_COPYLEAKS_EMAIL"],
            "key": credentials["FIELDKIT_TELL_COPYLEAKS_KEY"],
        },
        timeout=request.timeout,
    )
    login.raise_for_status()
    token = _string(_json_object(login), "access_token")
    scan_id = f"fieldkit-{uuid.uuid4().hex}"
    response = client.post(
        f"https://api.copyleaks.com/v2/writer-detector/{scan_id}/check",
        headers={"Authorization": f"Bearer {token}"},
        json={"text": request.text},
        timeout=request.timeout,
    )
    response.raise_for_status()
    payload = _json_object(response)
    summary = _object(payload["summary"], "summary")
    ai_fraction = summary.get("ai", summary.get("aiProbability"))
    if ai_fraction is None:
        raise KeyError("summary.ai")
    return _ran(
        adapter,
        _fraction_or_percent(ai_fraction),
        _label(payload, "label", "classification", "result"),
    )


def _call_sapling(
    adapter: Adapter,
    request: DetectorRequest,
    client: httpx.Client,
    credentials: Mapping[str, str],
) -> DetectorResult:
    response = client.post(
        "https://api.sapling.ai/api/v1/aidetect",
        json={
            "key": credentials["FIELDKIT_TELL_SAPLING_KEY"],
            "text": request.text,
            "sent_scores": True,
        },
        timeout=request.timeout,
    )
    response.raise_for_status()
    payload = _json_object(response)
    return _ran(
        adapter,
        _probability(payload["score"]),
        _label(payload, "label", "prediction", "verdict"),
    )


def _call_winston(
    adapter: Adapter,
    request: DetectorRequest,
    client: httpx.Client,
    credentials: Mapping[str, str],
) -> DetectorResult:
    response = client.post(
        "https://api.gowinston.ai/v2/ai-content-detection",
        headers={
            "Authorization": f"Bearer {credentials['FIELDKIT_TELL_WINSTON_KEY']}"
        },
        json={"text": request.text, "sentences": True, "language": "auto"},
        timeout=request.timeout,
    )
    response.raise_for_status()
    payload = _json_object(response)
    human_score = _number(payload["score"], "score")
    spans = _winston_spans(request.text, payload.get("sentences"))
    return _ran(
        adapter,
        _probability(1 - human_score / 100),
        _label(payload, "label", "result", "prediction"),
        spans=spans,
    )


def _call_zerogpt(
    adapter: Adapter,
    request: DetectorRequest,
    client: httpx.Client,
    credentials: Mapping[str, str],
) -> DetectorResult:
    response = client.post(
        "https://api.zerogpt.com/api/detect/detectText",
        headers={
            "Authorization": f"Bearer {credentials['FIELDKIT_TELL_ZEROGPT_KEY']}"
        },
        json={"input_text": request.text},
        timeout=request.timeout,
    )
    response.raise_for_status()
    payload = _json_object(response)
    data = _object(payload["data"], "data")
    return _ran(
        adapter,
        _probability(_number(data["fakePercentage"], "data.fakePercentage") / 100),
        _label(data, "label", "feedback", "result"),
    )


ADAPTERS: tuple[Adapter, ...] = (
    Adapter(
        "pangram",
        "Pangram",
        ("FIELDKIT_TELL_PANGRAM_KEY",),
        1,
        200_000,
        _call_pangram,
    ),
    Adapter(
        "gptzero",
        "GPTZero",
        ("FIELDKIT_TELL_GPTZERO_KEY",),
        250,
        50_000,
        _call_gptzero,
    ),
    Adapter(
        "originality",
        "Originality",
        ("FIELDKIT_TELL_ORIGINALITY_KEY",),
        100,
        100_000,
        _call_originality,
    ),
    Adapter(
        "copyleaks",
        "Copyleaks",
        ("FIELDKIT_TELL_COPYLEAKS_EMAIL", "FIELDKIT_TELL_COPYLEAKS_KEY"),
        255,
        100_000,
        _call_copyleaks,
    ),
    Adapter(
        "sapling",
        "Sapling",
        ("FIELDKIT_TELL_SAPLING_KEY",),
        1,
        200_000,
        _call_sapling,
    ),
    Adapter(
        "winston",
        "Winston",
        ("FIELDKIT_TELL_WINSTON_KEY",),
        300,
        150_000,
        _call_winston,
    ),
    Adapter(
        "zerogpt",
        "ZeroGPT",
        ("FIELDKIT_TELL_ZEROGPT_KEY",),
        1,
        100_000,
        _call_zerogpt,
    ),
)


def _ran(
    adapter: Adapter,
    probability: float,
    label: str,
    *,
    spans: list[DetectorSpan] | None = None,
    detail: str = "",
) -> DetectorResult:
    return DetectorResult(
        adapter.name,
        adapter.display_name,
        AdapterStatus.RAN,
        probability,
        label,
        spans or [],
        detail,
        0.0,
    )


def _skipped(adapter: Adapter, detail: str) -> DetectorResult:
    return DetectorResult(
        adapter.name,
        adapter.display_name,
        AdapterStatus.SKIPPED,
        None,
        "",
        [],
        detail,
        0.0,
    )


def _error(adapter: Adapter, detail: str, started: float) -> DetectorResult:
    return DetectorResult(
        adapter.name,
        adapter.display_name,
        AdapterStatus.ERROR,
        None,
        "",
        [],
        detail,
        round((time.perf_counter() - started) * 1000, 1),
    )


def _json_object(response: httpx.Response) -> dict[str, Any]:
    payload = response.json()
    return _object(payload, "response")


def _object(value: object, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise TypeError(f"{path} must be an object")
    return value


def _list(payload: dict[str, Any], key: str) -> list[Any]:
    value = payload[key]
    if not isinstance(value, list) or not value:
        raise TypeError(f"{key} must be a non-empty list")
    return value


def _string(payload: dict[str, Any], key: str) -> str:
    value = payload[key]
    if not isinstance(value, str) or not value:
        raise TypeError(f"{key} must be a non-empty string")
    return value


def _label(payload: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str):
            return value
    return ""


def _number(value: object, path: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise TypeError(f"{path} must be a number")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{path} must be finite")
    return number


def _probability(value: object) -> float:
    score = _number(value, "probability")
    if not 0 <= score <= 1:
        raise ValueError("probability must be between 0 and 1")
    return round(score, 6)


def _fraction_or_percent(value: object) -> float:
    score = _number(value, "score")
    if 0 <= score <= 1:
        return _probability(score)
    if 0 <= score <= 100:
        return _probability(score / 100)
    raise ValueError("score must be a fraction or percentage")


def _numeric_spans(
    value: object,
    *,
    start_keys: tuple[str, ...],
    end_keys: tuple[str, ...],
    score_keys: tuple[str, ...],
) -> list[DetectorSpan]:
    if not isinstance(value, list):
        return []
    spans: list[DetectorSpan] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        start = _first_number(item, start_keys)
        end = _first_number(item, end_keys)
        score = _first_number(item, score_keys)
        if start is None or end is None or score is None:
            continue
        if start < 0 or end <= start:
            continue
        spans.append(DetectorSpan(int(start), int(end), _fraction_or_percent(score)))
    return spans


def _first_number(payload: dict[str, Any], keys: tuple[str, ...]) -> float | None:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, int | float) and not isinstance(value, bool):
            return float(value)
    return None


def _winston_spans(text: str, value: object) -> list[DetectorSpan]:
    if not isinstance(value, list):
        return []
    spans: list[DetectorSpan] = []
    cursor = 0
    for item in value:
        if not isinstance(item, dict) or not isinstance(item.get("text"), str):
            continue
        sentence = item["text"]
        start = text.find(sentence, cursor)
        if start < 0:
            continue
        human_score = _first_number(item, ("score",))
        if human_score is None:
            continue
        end = start + len(sentence)
        spans.append(DetectorSpan(start, end, _probability(1 - human_score / 100)))
        cursor = end
    return spans


def _has_pangram_score(payload: dict[str, Any]) -> bool:
    return "ai_likelihood" in payload or (
        payload.get("stage") == "STAGE_SUCCESS" and "fraction_ai" in payload
    )


def _one_line(value: str) -> str:
    return " ".join(value.split())[:180] or "unknown error"
