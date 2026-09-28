"""YAML loading that refuses alias bombs without banning ordinary anchors."""

from __future__ import annotations

from typing import Any

import yaml

# Alias bombs stay small on disk and only become huge once each alias is
# counted again. A wide mimic spec has no aliases and is just large, so the
# cap applies to expansion past the composed graph, not to the graph itself.
_MAX_EXPANDED_NODES = 20_000
_EXPANSION_RATIO = 4
_CIRCULAR = "Circular reference detected"


class _AnchorLoader(yaml.SafeLoader):
    """SafeLoader that counts alias events while it composes."""

    def __init__(self, stream: str) -> None:
        super().__init__(stream)
        self.alias_events = 0

    def compose_node(self, parent: yaml.nodes.Node | None, index: Any) -> yaml.nodes.Node:
        if self.check_event(yaml.events.AliasEvent):
            self.alias_events += 1
        return super().compose_node(parent, index)


def _compose(text: str) -> tuple[yaml.nodes.Node | None, _AnchorLoader]:
    loader = _AnchorLoader(text)
    try:
        node = loader.get_single_node()
    except RecursionError as exc:
        loader.dispose()
        raise ValueError("nesting too deep") from exc
    except yaml.YAMLError as exc:
        loader.dispose()
        raise ValueError(f"invalid YAML: {exc}") from exc
    except BaseException:
        loader.dispose()
        raise
    return node, loader


def load_yaml(text: str) -> Any:
    """Parse one document, rejecting bombs and runaway nesting."""

    node, loader = _compose(text)
    try:
        if node is not None and loader.alias_events:
            _reject_alias_bomb(node)
        if node is None:
            return None
        try:
            return loader.construct_document(node)
        except RecursionError as exc:
            raise ValueError("nesting too deep") from exc
        except yaml.YAMLError as exc:
            raise ValueError(f"invalid YAML: {exc}") from exc
    finally:
        loader.dispose()


def reject_yaml_aliases(text: str) -> None:
    """Raise when aliases multiply a small document into a huge one.

    The check uses alias events from the parse, so a ``&`` or ``*`` inside
    a plain value does not force a second walk.
    """

    node, loader = _compose(text)
    try:
        if node is not None and loader.alias_events:
            _reject_alias_bomb(node)
    finally:
        loader.dispose()


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
                raise ValueError(_CIRCULAR)
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
            raise ValueError(_CIRCULAR)
        visiting.add(ident)
        stack.append((node, True))
        for kid in children_of.get(ident, ()):
            if id(kid) not in memo:
                stack.append((kid, False))
    return memo[id(root)]
