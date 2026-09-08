from __future__ import annotations

import importlib.util
import time
from typing import Any

from fieldkit_tell.adapters import AdapterStatus, DetectorResult

_MODEL = "roberta-base-openai-detector"
_NAME = "roberta-openai"
_DISPLAY_NAME = "roberta-openai (local)"
_CAVEAT = "trained on GPT-2-era outputs; treat this as a historical signal"


def ml_available() -> bool:
    """Return whether both packages for the optional local model are importable."""

    return (
        importlib.util.find_spec("transformers") is not None
        and importlib.util.find_spec("torch") is not None
    )


def run_local_detector(text: str) -> DetectorResult:
    """Run the opt-in local model, downloading weights only after explicit use."""

    if not ml_available():
        return DetectorResult(
            _NAME,
            _DISPLAY_NAME,
            AdapterStatus.SKIPPED,
            None,
            "",
            [],
            "install with: uv sync --extra ml",
            0.0,
        )

    started = time.perf_counter()
    try:
        from transformers import pipeline

        classifier = pipeline("text-classification", model=_MODEL, top_k=None)
        output = classifier(text, truncation=True)
        candidates = _flatten(output)
        selected = next(
            (
                item
                for item in candidates
                if isinstance(item.get("label"), str)
                and item["label"].lower() in {"fake", "ai", "label_1"}
            ),
            None,
        )
        if selected is None:
            raise ValueError("model response has no AI/Fake label")
        probability = float(selected["score"])
        if not 0 <= probability <= 1:
            raise ValueError("model score is outside 0..1")
        return DetectorResult(
            _NAME,
            _DISPLAY_NAME,
            AdapterStatus.RAN,
            round(probability, 6),
            str(selected["label"]),
            [],
            _CAVEAT,
            round((time.perf_counter() - started) * 1000, 1),
        )
    except Exception as exc:
        return DetectorResult(
            _NAME,
            _DISPLAY_NAME,
            AdapterStatus.ERROR,
            None,
            "",
            [],
            f"local model failed: {' '.join(str(exc).split())[:160]}",
            round((time.perf_counter() - started) * 1000, 1),
        )


def _flatten(output: Any) -> list[dict[str, Any]]:
    if isinstance(output, list) and output and isinstance(output[0], list):
        output = output[0]
    if not isinstance(output, list) or not all(isinstance(item, dict) for item in output):
        raise ValueError("model returned an unexpected payload")
    return output
