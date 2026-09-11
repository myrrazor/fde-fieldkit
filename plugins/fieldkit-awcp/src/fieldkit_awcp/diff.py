"""Diff helpers for WorkloadSpec changes."""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, List, Mapping


@dataclass(frozen=True)
class WorkloadChange:
    """A single meaningful WorkloadSpec change."""

    category: str
    path: str
    before: Any
    after: Any

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""
        return asdict(self)


def diff_workload_specs(
    before: Mapping[str, Any], after: Mapping[str, Any]
) -> List[WorkloadChange]:
    """Return categorized changes between two WorkloadSpecs."""
    changes: List[WorkloadChange] = []
    _walk("", before, after, changes)
    return changes


def _walk(path: str, before: Any, after: Any, changes: List[WorkloadChange]) -> None:
    if isinstance(before, Mapping) and isinstance(after, Mapping):
        for key in sorted(set(before) | set(after)):
            child_path = f"{path}.{key}" if path else str(key)
            _walk(child_path, before.get(key), after.get(key), changes)
        return

    if before != after:
        changes.append(
            WorkloadChange(
                category=_category_for(path),
                path=path,
                before=before,
                after=after,
            )
        )


def _category_for(path: str) -> str:
    if path.startswith("spec.modelRoute"):
        return "model"
    if path.startswith("spec.prompts"):
        return "prompt"
    if path.startswith("spec.tools"):
        return "tool"
    if path.startswith("spec.policies"):
        return "policy"
    if path.startswith("spec.retrieval"):
        return "retrieval"
    return "config"
