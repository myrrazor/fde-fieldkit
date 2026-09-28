"""YAML loading that refuses alias bombs without banning ordinary anchors."""

from __future__ import annotations

import yaml

# A normal spec is a few hundred nodes. Alias bombs stay small on disk and
# only become huge once each alias is counted again, so the expanded size is
# capped before safe_load walks the same graph.
_MAX_EXPANDED_NODES = 20_000
_MAX_DEPTH = 40


def reject_yaml_aliases(text: str) -> None:
    """Raise before ``safe_load`` can expand an alias bomb.

    Ordinary anchors and aliases are fine. A bomb is a small document whose
    aliases multiply (ten references to a node that itself has ten references).
    The composed graph is small; the expanded node count is not.
    """

    try:
        loader = yaml.SafeLoader(text)
        try:
            node = loader.get_single_node()
        finally:
            loader.dispose()
        if node is not None:
            _reject_oversized(node)
    except yaml.YAMLError as exc:
        raise ValueError(f"invalid YAML: {exc}") from exc


def _reject_oversized(node: yaml.nodes.Node) -> None:
    memo: dict[int, int] = {}
    visiting: set[int] = set()

    def walk(current: yaml.nodes.Node, depth: int) -> int:
        if depth > _MAX_DEPTH:
            raise yaml.YAMLError("YAML document is nested too deeply")
        key = id(current)
        if key in visiting:
            raise yaml.YAMLError("YAML document expands too far")
        cached = memo.get(key)
        if cached is not None:
            return cached
        visiting.add(key)
        size = 1
        if isinstance(current, yaml.SequenceNode):
            for child in current.value:
                size += walk(child, depth + 1)
                if size > _MAX_EXPANDED_NODES:
                    break
        elif isinstance(current, yaml.MappingNode):
            for key_node, value_node in current.value:
                size += walk(key_node, depth + 1) + walk(value_node, depth + 1)
                if size > _MAX_EXPANDED_NODES:
                    break
        visiting.remove(key)
        memo[key] = size
        return size

    if walk(node, 1) > _MAX_EXPANDED_NODES:
        raise ValueError("YAML aliases expand too far — the document is larger than it looks")
