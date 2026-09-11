"""Load and structurally validate a local WorkloadSpec."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

from fieldkit_awcp.schema import validate_json_schema_profile
from fieldkit_awcp.tools import parse_tool_declarations


class WorkloadSpecError(ValueError):
    """Raised when a workload spec cannot be loaded."""


@dataclass(frozen=True)
class ValidationResult:
    """Validation result returned by the local WorkloadSpec validator."""

    ok: bool
    errors: List[str]
    workload_name: Optional[str] = None
    project: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Return a JSON-serializable representation."""
        return asdict(self)


def load_mapping(raw: str, *, source: str) -> Dict[str, Any]:
    """Load a top-level YAML or JSON object from text."""
    try:
        loaded: Any = json.loads(raw)
    except json.JSONDecodeError:
        import yaml

        try:
            loaded = yaml.safe_load(raw)
        except yaml.YAMLError as exc:
            raise WorkloadSpecError(f"could not parse {source}: {exc}") from exc

    if not isinstance(loaded, dict):
        raise WorkloadSpecError(f"{source} must contain a mapping at the top level")
    return loaded


def load_workload_spec(path: str | Path) -> Dict[str, Any]:
    """Load a WorkloadSpec from a YAML or JSON file."""
    spec_path = Path(path)
    try:
        raw = spec_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise WorkloadSpecError(f"could not read {spec_path}: {exc}") from exc
    return load_mapping(raw, source=str(spec_path))


def validate_workload_spec(spec: Mapping[str, Any]) -> ValidationResult:
    """Validate the WorkloadSpec shape Fieldkit ships for local checks."""
    errors: List[str] = []

    if spec.get("apiVersion") != "aiworkloads.dev/v1alpha1":
        errors.append("apiVersion must be aiworkloads.dev/v1alpha1")
    if spec.get("kind") != "AIWorkload":
        errors.append("kind must be AIWorkload")

    metadata = _mapping_at(spec, "metadata", errors)
    workload_name = _required_string(metadata, "name", "metadata.name", errors)
    project = _required_string(metadata, "project", "metadata.project", errors)
    _required_string(metadata, "owner", "metadata.owner", errors)

    body = _mapping_at(spec, "spec", errors)
    _required_string(body, "description", "spec.description", errors)

    _schema_at(body, "inputs", errors)
    _schema_at(body, "outputs", errors)
    _model_route(body, errors)
    _evals(body, errors)
    _policies(body, errors)
    _tools(body, errors)
    _retrieval(body, errors)
    _privacy(body, errors)

    return ValidationResult(
        ok=not errors,
        errors=errors,
        workload_name=workload_name,
        project=project,
    )


def _mapping_at(parent: Mapping[str, Any], key: str, errors: List[str]) -> Mapping[str, Any]:
    value = parent.get(key)
    if isinstance(value, Mapping):
        return value
    errors.append(f"{key} must be an object")
    return {}


def _required_string(
    parent: Mapping[str, Any], key: str, label: str, errors: List[str]
) -> Optional[str]:
    value = parent.get(key)
    if isinstance(value, str) and value.strip():
        return value
    errors.append(f"{label} is required")
    return None


def _schema_at(body: Mapping[str, Any], key: str, errors: List[str]) -> None:
    section = body.get(key)
    if not isinstance(section, Mapping):
        errors.append(f"spec.{key} must be an object")
        return

    schema = section.get("schema")
    if not isinstance(schema, Mapping):
        errors.append(f"spec.{key}.schema is required")
        return

    if schema.get("type") != "object":
        errors.append(f"spec.{key}.schema.type must be object")
    errors.extend(validate_json_schema_profile(schema, path=f"spec.{key}.schema"))


def _model_route(body: Mapping[str, Any], errors: List[str]) -> None:
    route = body.get("modelRoute")
    if not isinstance(route, Mapping):
        errors.append("spec.modelRoute is required")
        return

    _required_string(route, "gateway", "spec.modelRoute.gateway", errors)
    _required_string(route, "primary", "spec.modelRoute.primary", errors)


def _evals(body: Mapping[str, Any], errors: List[str]) -> None:
    evals = body.get("evals")
    if not isinstance(evals, Mapping):
        errors.append("spec.evals is required")
        return

    suites = evals.get("requiredSuites")
    if not _non_empty_string_list(suites):
        errors.append("spec.evals.requiredSuites must contain at least one suite")

    gates = evals.get("gates")
    if not isinstance(gates, Mapping):
        errors.append("spec.evals.gates is required")
    elif "minOverallScore" not in gates:
        errors.append("spec.evals.gates.minOverallScore is required")


def _policies(body: Mapping[str, Any], errors: List[str]) -> None:
    policies = body.get("policies")
    if not isinstance(policies, Mapping):
        errors.append("spec.policies is required")
        return

    packs = policies.get("requiredPacks")
    if not _non_empty_string_list(packs):
        errors.append("spec.policies.requiredPacks must contain at least one pack")

    mode = policies.get("enforcementMode")
    if mode not in {"block", "warn", "monitor"}:
        errors.append("spec.policies.enforcementMode must be block, warn, or monitor")


def _tools(body: Mapping[str, Any], errors: List[str]) -> None:
    parsed = parse_tool_declarations(body)
    errors.extend(issue.message.removeprefix("spec.") for issue in parsed.issues)


def _retrieval(body: Mapping[str, Any], errors: List[str]) -> None:
    retrieval = body.get("retrieval")
    if not isinstance(retrieval, Mapping):
        return

    sources = retrieval.get("sources", [])
    if sources and "freshnessDays" not in retrieval:
        errors.append(
            "spec.retrieval.freshnessDays is required when retrieval sources are configured"
        )


def _privacy(body: Mapping[str, Any], errors: List[str]) -> None:
    privacy = body.get("privacy")
    if not isinstance(privacy, Mapping):
        errors.append("spec.privacy is required")
        return

    if not isinstance(privacy.get("storeInputs"), bool):
        errors.append("spec.privacy.storeInputs must be a boolean")
    if not isinstance(privacy.get("storeOutputs"), bool):
        errors.append("spec.privacy.storeOutputs must be a boolean")


def _non_empty_string_list(value: Any) -> bool:
    return isinstance(value, list) and any(isinstance(item, str) and item.strip() for item in value)
