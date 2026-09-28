"""YAML loading that refuses alias bombs without banning ordinary anchors."""

from __future__ import annotations

import yaml

# Alias bombs stay small on disk and only become huge once each alias is
# counted again. A wide mimic spec has no aliases and is just large, so the
# cap applies to expansion past the composed graph, not to the graph itself.
_MAX_EXPANDED_NODES = 20_000
_EXPANSION_RATIO = 4


def reject_yaml_aliases(text: str) -> None:
    """Raise before ``safe_load`` can expand an alias bomb.

    Ordinary anchors and aliases are fine, including inside a large spec.
    A bomb is a small document whose aliases multiply (ten references to a
    node that itself has ten references).
    """

    try:
        loader = yaml.SafeLoader(text)
        try:
            node = loader.get_single_node()
        finally:
            loader.dispose()
    except yaml.YAMLError as exc:
        raise ValueError(f"invalid YAML: {exc}") from exc
    if node is None:
        return
    _reject_alias_bomb(node)


def _children(node: yaml.nodes.Node) -> list[yaml.nodes.Node]:
    if isinstance(node, yaml.SequenceNode):
        return list(node.value)
    if isinstance(node, yaml.MappingNode):
        kids: list[yaml.nodes.Node] = []
        for key, value in node.value:
            kids.append(key)
            kids.append(value)
        return kids
    return []


def _reject_alias_bomb(root: yaml.nodes.Node) -> None:
    children_of, unique, shared = _compose_graph(root)
    # No alias is reused. Depth and width here are the document the user wrote.
    if not shared:
        return
    expanded = _expanded_size(root, children_of)
    if expanded > _MAX_EXPANDED_NODES and expanded > unique * _EXPANSION_RATIO:
        raise ValueError(
            "YAML aliases expand too far — the document is larger than it looks"
        )


def _compose_graph(
    root: yaml.nodes.Node,
) -> tuple[dict[int, list[yaml.nodes.Node]], int, bool]:
    """Return child lists, the unique node count, and whether any node is reused."""

    children_of: dict[int, list[yaml.nodes.Node]] = {}
    refs: dict[int, int] = {}
    seen: set[int] = set()
    active: set[int] = set()
    stack: list[tuple[yaml.nodes.Node, bool]] = [(root, False)]
    while stack:
        node, finished = stack.pop()
        ident = id(node)
        if finished:
            active.discard(ident)
            continue
        if ident in seen:
            if ident in active:
                raise ValueError(
                    "YAML aliases expand too far — the document is larger than it looks"
                )
            continue
        seen.add(ident)
        active.add(ident)
        kids = _children(node)
        children_of[ident] = kids
        stack.append((node, True))
        for kid in kids:
            refs[id(kid)] = refs.get(id(kid), 0) + 1
            stack.append((kid, False))
    return children_of, len(seen), any(count > 1 for count in refs.values())


def _expanded_size(
    root: yaml.nodes.Node, children_of: dict[int, list[yaml.nodes.Node]]
) -> int:
    """Count nodes after aliases are copied out. Each composed node is visited once."""

    memo: dict[int, int] = {}
    visiting: set[int] = set()
    stack: list[tuple[yaml.nodes.Node, bool]] = [(root, False)]
    while stack:
        node, finished = stack.pop()
        ident = id(node)
        if finished:
            visiting.discard(ident)
            size = 1
            for kid in children_of.get(ident, ()):
                size += memo[id(kid)]
            memo[ident] = size
            continue
        if ident in memo:
            continue
        if ident in visiting:
            raise ValueError(
                "YAML aliases expand too far — the document is larger than it looks"
            )
        visiting.add(ident)
        stack.append((node, True))
        for kid in children_of.get(ident, ()):
            if id(kid) not in memo:
                stack.append((kid, False))
    return memo[id(root)]
