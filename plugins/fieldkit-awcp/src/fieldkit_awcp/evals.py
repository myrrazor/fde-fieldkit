"""Local golden-suite scoring. This never calls a model or promptfoo."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Optional
from uuid import uuid4

from fieldkit_awcp.numeric import NumericValidationError, finite_number
from fieldkit_awcp.spec import WorkloadSpecError, load_mapping


class EvalError(ValueError):
    """Raised when an eval suite or run is invalid."""


class EvalSafetyMeasurementError(EvalError):
    """Raised when safety evidence is missing or invalid."""

    def __init__(self, metric: str, case_index: int, reason: str) -> None:
        self.metric = metric
        self.case_index = case_index
        self.reason = reason
        super().__init__(f"{reason}: {metric} at case index {case_index}")


@dataclass(frozen=True)
class EvalSuite:
    id: str
    name: str
    description: Optional[str]
    runner: str
    config: dict[str, Any]
    cases: list[dict[str, Any]]
    created_at: str


@dataclass(frozen=True)
class EvalCaseResult:
    case_id: str
    score: float
    passed: bool
    latency_ms: int
    cost_usd_estimate: float
    pii_leakage_rate: Optional[float]
    unsupported_claim_rate: Optional[float]
    reason: str


@dataclass(frozen=True)
class EvalRun:
    id: str
    eval_suite_id: str
    workload_version_id: str
    status: str
    score: float
    metrics: dict[str, Any]
    artifact_uri: str
    workload_spec_hash: str
    created_at: str
    completed_at: Optional[str]
    suite_name: str = ""
    runner: str = "golden"
    results: tuple[EvalCaseResult, ...] = ()
    source: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["results"] = [asdict(result) for result in self.results]
        return payload


@dataclass
class ArtifactStore:
    root: Path

    def write_json(self, namespace: str, artifact_id: str, payload: Mapping[str, Any]) -> str:
        if not _safe_artifact_part(namespace) or not _safe_artifact_part(artifact_id):
            raise EvalError("artifact namespace must be a simple name")
        target_dir = self.root / namespace / artifact_id
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / "result.json"
        target.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return f"artifact://{namespace}/{artifact_id}/result.json"

    def read_json(self, artifact_uri: str) -> dict[str, Any]:
        target = self.resolve(artifact_uri)
        loaded = json.loads(target.read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            raise EvalError(f"artifact {artifact_uri} must contain a JSON object")
        return loaded

    def resolve(self, artifact_uri: str) -> Path:
        prefix = "artifact://"
        if not artifact_uri.startswith(prefix):
            raise EvalError(f"unsupported artifact uri: {artifact_uri}")
        relative_path = Path(artifact_uri.removeprefix(prefix))
        if relative_path.is_absolute() or any(part in {"", ".", ".."} for part in relative_path.parts):
            raise EvalError(f"unsafe artifact uri: {artifact_uri}")
        return self.root.joinpath(*relative_path.parts)


@dataclass
class EvalService:
    """In-memory golden scorer. Runner labels are recorded, never executed."""

    artifact_store: ArtifactStore = field(default_factory=lambda: ArtifactStore(Path(".awcp-artifacts")))
    suites: dict[str, EvalSuite] = field(default_factory=dict)
    runs: dict[str, EvalRun] = field(default_factory=dict)

    def create_suite(
        self,
        name: str,
        *,
        description: Optional[str] = None,
        runner: str = "golden",
        config: Optional[Mapping[str, Any]] = None,
        cases: Optional[list[Mapping[str, Any]]] = None,
        suite_id: Optional[str] = None,
    ) -> EvalSuite:
        if not str(name).strip():
            raise EvalError("eval suite name is required")
        runner_name = str(runner or "golden").strip() or "golden"
        case_dicts = [_plain_dict(case) for case in cases or []]
        if not case_dicts:
            raise EvalError("eval suite requires at least one eval case")
        for index, case in enumerate(case_dicts):
            if not str(case.get("id", "")).strip():
                raise EvalError(f"eval case {index} id is required")
        eval_suite = EvalSuite(
            id=suite_id or _new_id("evals"),
            name=name,
            description=description,
            runner=runner_name,
            config=_plain_dict(config or {}),
            cases=case_dicts,
            created_at=_now(),
        )
        self.suites[eval_suite.id] = eval_suite
        return eval_suite

    def start_run(
        self,
        eval_suite_id: str,
        workload_version_id: str,
        *,
        workload_version_spec: Mapping[str, Any],
        source: str = "",
    ) -> EvalRun:
        try:
            suite = self.suites[eval_suite_id]
        except KeyError as exc:
            raise EvalError(f"eval suite {eval_suite_id} not found") from exc
        spec = _plain_dict(workload_version_spec)
        spec_hash = _hash_json(spec)
        output = _score_suite(suite, workload_version_id, spec, spec_hash)
        run_id = _new_id("evalrun")
        created_at = _now()
        output["run"]["id"] = run_id
        output["run"]["created_at"] = created_at
        artifact_uri = self.artifact_store.write_json("eval-runs", run_id, output)
        run_payload = output["run"]
        results = tuple(EvalCaseResult(**row) for row in output["results"])
        eval_run = EvalRun(
            id=run_id,
            eval_suite_id=eval_suite_id,
            workload_version_id=workload_version_id,
            status=run_payload["status"],
            score=run_payload["score"],
            metrics=run_payload["metrics"],
            artifact_uri=artifact_uri,
            workload_spec_hash=spec_hash,
            created_at=created_at,
            completed_at=_now(),
            suite_name=suite.name,
            runner=suite.runner,
            results=results,
            source=source,
        )
        self.runs[eval_run.id] = eval_run
        return eval_run


def load_eval_suite(path: str | Path) -> dict[str, Any]:
    suite_path = Path(path)
    try:
        raw = suite_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise EvalError(f"could not read {suite_path}: {exc}") from exc
    try:
        return load_mapping(raw, source=str(suite_path))
    except WorkloadSpecError as exc:
        raise EvalError(str(exc)) from exc


def suite_from_mapping(payload: Mapping[str, Any], service: EvalService) -> EvalSuite:
    return service.create_suite(
        name=str(payload.get("name", "")),
        description=payload.get("description") if isinstance(payload.get("description"), str) else None,
        runner=str(payload.get("runner", "golden") or "golden"),
        config=payload.get("config") if isinstance(payload.get("config"), Mapping) else {},
        cases=[item for item in payload.get("cases", []) if isinstance(item, Mapping)]
        if isinstance(payload.get("cases"), list)
        else [],
        suite_id=str(payload["id"]) if isinstance(payload.get("id"), str) and payload["id"].strip() else None,
    )


def run_eval(
    workload: Mapping[str, Any],
    suite_payload: Mapping[str, Any],
    *,
    artifact_dir: Path,
    source: str = "",
) -> EvalRun:
    service = EvalService(artifact_store=ArtifactStore(artifact_dir))
    suite = suite_from_mapping(suite_payload, service)
    fingerprint = _hash_json(_plain_dict(workload))
    workload_version_id = "wlv_local_" + fingerprint.split(":", 1)[1][:12]
    return service.start_run(
        suite.id,
        workload_version_id,
        workload_version_spec=workload,
        source=source,
    )


def _score_suite(
    suite: EvalSuite,
    workload_version_id: str,
    workload_spec: Mapping[str, Any],
    workload_spec_hash: str,
) -> dict[str, Any]:
    gates = _gates_for(suite.config, workload_spec)
    required_safety_metrics = {
        metric for gate, metric in SAFETY_GATE_METRICS.items() if gate in gates
    }
    results = [
        _score_case(case, index, required_safety_metrics)
        for index, case in enumerate(suite.cases)
    ]
    score = _average([result.score for result in results])
    try:
        total_cost = round(
            finite_number(
                sum(result.cost_usd_estimate for result in results),
                field="cost_usd_estimate_total",
                minimum=0.0,
            ),
            6,
        )
    except NumericValidationError as exc:
        raise EvalError(str(exc)) from exc
    p95_latency = _p95([result.latency_ms for result in results])
    pii_leakage_rate = _complete_max([result.pii_leakage_rate for result in results])
    unsupported_claim_rate = _complete_max([result.unsupported_claim_rate for result in results])
    min_score = _float_at(gates, "minOverallScore", 1.0)
    max_p95 = _optional_float_at(gates, "maxP95LatencyMs")
    max_pii = _optional_float_at(gates, "maxPiiLeakageRate")
    max_unsupported = _optional_float_at(gates, "maxUnsupportedClaimRate")
    max_cost = _optional_float_at(gates, "maxCostUsdEstimate")
    passed = (
        score >= min_score
        and (max_p95 is None or p95_latency <= max_p95)
        and (max_pii is None or (pii_leakage_rate is not None and pii_leakage_rate <= max_pii))
        and (
            max_unsupported is None
            or (unsupported_claim_rate is not None and unsupported_claim_rate <= max_unsupported)
        )
        and (max_cost is None or total_cost <= max_cost)
    )
    metrics = {
        "passed": passed,
        "case_count": len(results),
        "overall_score": score,
        "min_overall_score": min_score,
        "p95_latency_ms": p95_latency,
        "max_p95_latency_ms": max_p95,
        "cost_usd_estimate": total_cost,
        "max_cost_usd_estimate": max_cost,
        "pii_leakage_rate": pii_leakage_rate,
        "max_pii_leakage_rate": max_pii,
        "unsupported_claim_rate": unsupported_claim_rate,
        "max_unsupported_claim_rate": max_unsupported,
        "local_scorer": True,
    }
    return {
        "run": {
            "eval_suite_id": suite.id,
            "workload_version_id": workload_version_id,
            "status": "passed" if passed else "failed",
            "score": score,
            "metrics": metrics,
        },
        "workload_version": {"id": workload_version_id, "spec_hash": workload_spec_hash},
        "suite": {
            "id": suite.id,
            "name": suite.name,
            "runner": suite.runner,
            "config_hash": _hash_json(suite.config),
        },
        "results": [asdict(result) for result in results],
        "honesty": "scored locally from recorded cases; no model or promptfoo process ran",
    }


MINIMUM_GATES = {"minOverallScore"}
MAXIMUM_GATES = {
    "maxP95LatencyMs",
    "maxPiiLeakageRate",
    "maxUnsupportedClaimRate",
    "maxCostUsdEstimate",
}
SUPPORTED_GATES = MINIMUM_GATES | MAXIMUM_GATES
SAFETY_GATE_METRICS = {
    "maxPiiLeakageRate": "pii_leakage_rate",
    "maxUnsupportedClaimRate": "unsupported_claim_rate",
}


def _score_case(
    case: Mapping[str, Any],
    index: int,
    required_safety_metrics: Optional[set[str]] = None,
) -> EvalCaseResult:
    case_id = str(case["id"])
    if "score" in case:
        try:
            score = finite_number(
                case.get("score"),
                field=f"eval case {index} score",
                minimum=0.0,
                maximum=1.0,
            )
        except NumericValidationError as exc:
            raise EvalError(str(exc)) from exc
        reason = "explicit score"
    else:
        actual = case.get("actual", case.get("actual_output"))
        expected = case.get("expected", case.get("expected_output"))
        if actual is None or expected is None:
            score = 0.0
            reason = "missing actual or expected value"
        elif _normalized(actual) == _normalized(expected):
            score = 1.0
            reason = "actual matched expected"
        elif isinstance(actual, Mapping) and isinstance(expected, Mapping):
            score = _mapping_overlap_score(actual, expected)
            reason = "partial object match"
        elif isinstance(actual, str) and isinstance(expected, str) and expected in actual:
            score = 1.0
            reason = "actual contained expected text"
        else:
            score = 0.0
            reason = "actual did not match expected"

    latency_ms = _non_negative_int_at(case, "latency_ms", 100 + index)
    cost = _float_at(case, "cost_usd_estimate", 0.001, minimum=0.0)
    required = required_safety_metrics or set()
    return EvalCaseResult(
        case_id=case_id,
        score=score,
        passed=score >= 0.5,
        latency_ms=latency_ms,
        cost_usd_estimate=cost,
        pii_leakage_rate=_safety_metric_at(
            case, "pii_leakage_rate", index, required="pii_leakage_rate" in required
        ),
        unsupported_claim_rate=_safety_metric_at(
            case,
            "unsupported_claim_rate",
            index,
            required="unsupported_claim_rate" in required,
        ),
        reason=reason,
    )


def _gates_for(suite_config: Mapping[str, Any], workload_spec: Mapping[str, Any]) -> Mapping[str, Any]:
    merged: dict[str, float] = {}
    spec = workload_spec.get("spec")
    if isinstance(spec, Mapping):
        evals = spec.get("evals")
        if isinstance(evals, Mapping):
            gates = evals.get("gates")
            if isinstance(gates, Mapping):
                _merge_gates(merged, gates)
    suite_gates = suite_config.get("gates")
    if isinstance(suite_gates, Mapping):
        _merge_gates(merged, suite_gates)
    return merged


def _merge_gates(target: dict[str, float], gates: Mapping[str, Any]) -> None:
    for key, raw_value in gates.items():
        if key not in SUPPORTED_GATES:
            raise EvalError(f"unsupported eval gate {key}")
        minimum = 0.0
        maximum = 1.0 if key == "minOverallScore" or key in SAFETY_GATE_METRICS else None
        try:
            value = finite_number(
                raw_value, field=f"eval gate {key}", minimum=minimum, maximum=maximum
            )
        except NumericValidationError as exc:
            raise EvalError(str(exc)) from exc
        if key in MINIMUM_GATES:
            target[key] = max(target.get(key, value), value)
        else:
            target[key] = min(target.get(key, value), value)


def _mapping_overlap_score(actual: Mapping[str, Any], expected: Mapping[str, Any]) -> float:
    if not expected:
        return 1.0 if not actual else 0.0
    matches = sum(
        1
        for key, expected_value in expected.items()
        if key in actual and _normalized(actual[key]) == _normalized(expected_value)
    )
    return round(matches / len(expected), 6)


def _safe_artifact_part(value: str) -> bool:
    return bool(value) and "/" not in value and "\\" not in value and value not in {".", ".."}


def _plain_dict(value: Mapping[str, Any]) -> dict[str, Any]:
    return json.loads(json.dumps(value, sort_keys=True))


def _hash_json(value: Mapping[str, Any]) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _normalized(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _average(values: list[float]) -> float:
    return round(sum(values) / len(values), 6) if values else 0.0


def _complete_max(values: list[Optional[float]]) -> Optional[float]:
    if not values or any(value is None for value in values):
        return None
    return round(max(value for value in values if value is not None), 6)


def _safety_metric_at(
    parent: Mapping[str, Any],
    key: str,
    case_index: int,
    *,
    required: bool,
) -> Optional[float]:
    if key not in parent:
        if required:
            raise EvalSafetyMeasurementError(key, case_index, "missing_required_safety_metric")
        return None
    try:
        return finite_number(parent[key], field=key, minimum=0.0, maximum=1.0)
    except NumericValidationError as exc:
        if exc.reason == "non_numeric":
            reason = "malformed_required_safety_metric" if required else "malformed_safety_metric"
        elif exc.reason == "numeric_overflow":
            reason = "numeric_overflow_safety_metric"
        elif exc.reason == "non_finite":
            reason = "non_finite_safety_metric"
        else:
            reason = "out_of_range_safety_metric"
        raise EvalSafetyMeasurementError(key, case_index, reason) from exc


def _p95(values: list[int]) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    index = max(0, int(len(ordered) * 0.95 + 0.999999) - 1)
    return ordered[index]


def _non_negative_int_at(parent: Mapping[str, Any], key: str, fallback: int) -> int:
    if key not in parent:
        return fallback
    try:
        value = finite_number(
            parent[key],
            field=key,
            minimum=0.0,
            maximum=float((1 << 53) - 1),
            require_safe_integer=True,
        )
    except NumericValidationError as exc:
        raise EvalError(str(exc)) from exc
    if not value.is_integer():
        raise EvalError(f"{key}: non_integer")
    return int(value)


def _float_at(
    parent: Mapping[str, Any],
    key: str,
    fallback: float,
    *,
    minimum: Optional[float] = None,
    maximum: Optional[float] = None,
) -> float:
    if key not in parent:
        return fallback
    try:
        return finite_number(parent[key], field=key, minimum=minimum, maximum=maximum)
    except NumericValidationError as exc:
        raise EvalError(str(exc)) from exc


def _optional_float_at(parent: Mapping[str, Any], key: str) -> Optional[float]:
    if key not in parent:
        return None
    try:
        return finite_number(parent[key], field=key)
    except NumericValidationError as exc:
        raise EvalError(str(exc)) from exc


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:16]}"
