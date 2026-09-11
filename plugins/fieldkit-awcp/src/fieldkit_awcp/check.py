"""Combine validation, fingerprints, and tool-risk into one local check."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from fieldkit_awcp.fingerprint import WorkloadFingerprint, fingerprint_workload_spec
from fieldkit_awcp.spec import ValidationResult, validate_workload_spec
from fieldkit_awcp.tools import ToolDeclaration, parse_tool_declarations, tool_risk_reasons


@dataclass(frozen=True)
class ToolSummary:
    name: str
    scopes: tuple[str, ...]
    requires_approval: bool
    risk_tokens: tuple[str, ...]


@dataclass(frozen=True)
class SpecCheck:
    source: str
    spec: dict[str, Any]
    validation: ValidationResult
    fingerprint: WorkloadFingerprint
    tools: tuple[ToolSummary, ...]
    denied_tools: tuple[str, ...]
    warnings: tuple[str, ...] = field(default_factory=tuple)

    @property
    def ok(self) -> bool:
        return self.validation.ok


def check_spec(
    spec: Mapping[str, Any],
    *,
    source: str,
    base_dir: Path | None = None,
) -> SpecCheck:
    """Run the local, no-network WorkloadSpec checks."""

    validation = validate_workload_spec(spec)
    fingerprint = fingerprint_workload_spec(spec, base_dir=base_dir)
    body = spec.get("spec") if isinstance(spec.get("spec"), Mapping) else {}
    parsed = parse_tool_declarations(body if isinstance(body, Mapping) else {})
    tools = tuple(
        ToolSummary(
            name=declaration.name,
            scopes=declaration.scopes,
            requires_approval=declaration.requires_approval,
            risk_tokens=_risk_tokens(declaration),
        )
        for declaration in parsed.declarations
    )
    denied = _string_tuple(body.get("denied") if isinstance(body, Mapping) else None)
    if isinstance(body, Mapping) and isinstance(body.get("tools"), Mapping):
        denied = _string_tuple(body["tools"].get("denied"))

    warnings: list[str] = []
    for tool in tools:
        if tool.risk_tokens and not tool.requires_approval:
            warnings.append(
                f"{tool.name} looks high-risk ({', '.join(tool.risk_tokens)}) "
                "and does not require approval"
            )
    return SpecCheck(
        source=source,
        spec=dict(spec),
        validation=validation,
        fingerprint=fingerprint,
        tools=tools,
        denied_tools=denied,
        warnings=tuple(warnings),
    )


def _risk_tokens(declaration: ToolDeclaration) -> tuple[str, ...]:
    tokens: list[str] = []
    seen: set[str] = set()
    for reason in tool_risk_reasons(declaration):
        token = reason.token or reason.code
        if token in seen:
            continue
        seen.add(token)
        tokens.append(token)
    return tuple(tokens)


def _string_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(item for item in value if isinstance(item, str) and item.strip())
