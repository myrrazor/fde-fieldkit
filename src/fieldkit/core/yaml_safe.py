"""YAML loading that refuses to expand aliases."""

from __future__ import annotations

import yaml


def reject_yaml_aliases(text: str) -> None:
    """Raise before ``safe_load`` can expand anchors or aliases.

    Alias nodes are expanded while the document is composed. A few hundred
    bytes of aliases can become gigabytes, so the event stream is checked
    first and never composed when an anchor is present.
    """

    try:
        for event in yaml.parse(text):
            if getattr(event, "anchor", None):
                raise ValueError(
                    "YAML aliases and anchors are not allowed — "
                    "they can expand far beyond the file size"
                )
    except yaml.YAMLError as exc:
        raise ValueError(f"invalid YAML: {exc}") from exc
