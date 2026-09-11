"""Hash helpers for workload config and prompt references."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, Mapping, Optional


@dataclass(frozen=True)
class PromptFingerprint:
    """Hash plus source mode for a prompt reference."""

    mode: str
    hash: str


@dataclass(frozen=True)
class WorkloadFingerprint:
    """Hashes used to track config and prompt changes."""

    config_hash: str
    prompt_hashes: Dict[str, PromptFingerprint]

    def to_dict(self) -> Dict[str, Any]:
        """Return a JSON-serializable representation."""
        return asdict(self)


def fingerprint_workload_spec(
    spec: Mapping[str, Any], *, base_dir: Optional[Path] = None
) -> WorkloadFingerprint:
    """Return a config hash plus prompt content/reference hashes."""
    prompt_hashes = _prompt_hashes(spec, base_dir)
    return WorkloadFingerprint(
        config_hash=_hash_json(spec),
        prompt_hashes=prompt_hashes,
    )


def _prompt_hashes(
    spec: Mapping[str, Any], base_dir: Optional[Path]
) -> Dict[str, PromptFingerprint]:
    prompts = spec.get("spec", {}).get("prompts", {})
    if not isinstance(prompts, Mapping):
        return {}

    hashes: Dict[str, PromptFingerprint] = {}
    for name, prompt in prompts.items():
        if not isinstance(name, str) or not isinstance(prompt, Mapping):
            continue

        ref = prompt.get("ref")
        version = prompt.get("version")
        prompt_path = _safe_prompt_path(base_dir, ref)
        if prompt_path is not None:
            hashes[name] = PromptFingerprint(
                mode="content", hash=_hash_bytes(prompt_path.read_bytes())
            )
        else:
            hashes[name] = PromptFingerprint(
                mode="ref",
                hash=_hash_json({"ref": ref, "version": version}),
            )

    return hashes


def _safe_prompt_path(base_dir: Optional[Path], ref: Any) -> Optional[Path]:
    if base_dir is None or not isinstance(ref, str) or Path(ref).is_absolute():
        return None

    root = base_dir.resolve()
    candidate = (root / ref).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return None

    return candidate if candidate.is_file() else None


def _hash_json(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return _hash_bytes(payload.encode("utf-8"))


def _hash_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()
