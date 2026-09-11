"""Bounded JSON Schema subset checker for WorkloadSpec input/output schemas."""

from __future__ import annotations

import math
from collections import deque

from typing import Any, List, Mapping

from fieldkit_awcp.tools import TOOL_IDENTIFIER_SCHEMA_PATTERN


MAX_SCHEMA_PATTERN_LENGTH = 128
MAX_SCHEMA_PROFILE_DEPTH = 64
_LITERAL_PATTERN_META = frozenset(".^$*+?{}[]\\|()")
_TOOL_IDENTIFIER_CHARS = frozenset(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._:/-"
)
_UNSUPPORTED_SCHEMA_CONTAINERS = frozenset(
    {
        "allOf",
        "anyOf",
        "contains",
        "dependentSchemas",
        "else",
        "if",
        "not",
        "oneOf",
        "patternProperties",
        "prefixItems",
        "propertyNames",
        "then",
        "unevaluatedItems",
        "unevaluatedProperties",
    }
)
_SUPPORTED_SCHEMA_KEYWORDS = (
    frozenset(
        {
            "$comment",
            "$defs",
            "$id",
            "$ref",
            "$schema",
            "additionalProperties",
            "const",
            "default",
            "deprecated",
            "description",
            "definitions",
            "enum",
            "examples",
            "items",
            "maximum",
            "maxItems",
            "maxLength",
            "minimum",
            "minItems",
            "minLength",
            "pattern",
            "properties",
            "readOnly",
            "required",
            "title",
            "type",
            "writeOnly",
        }
    )
    | _UNSUPPORTED_SCHEMA_CONTAINERS
)


def validate_json_schema_subset(instance: Any, schema: Mapping[str, Any]) -> List[str]:
    """Validate the JSON Schema features used by `workloadspec.schema.json`.

    Intentionally small and local. It is the same bounded checker the AWCP
    prototype used; Fieldkit does not pull in a full JSON Schema engine.
    """
    errors = validate_json_schema_profile(schema)
    if errors:
        return errors
    _validate(instance, schema, "$", schema, errors, 0)
    return errors


def validate_json_schema_profile(
    schema: Mapping[str, Any],
    *,
    path: str = "$",
) -> List[str]:
    """Reject schema patterns outside the bounded, non-executing profile."""
    errors: List[str] = []
    _validate_schema_graph_depth(schema, path, errors)
    if errors:
        return errors
    _validate_schema_profile(schema, path, errors, schema, (), set(), 0)
    return errors


def _validate(
    instance: Any,
    schema: Mapping[str, Any],
    path: str,
    root_schema: Mapping[str, Any],
    errors: List[str],
    depth: int,
) -> None:
    if depth > MAX_SCHEMA_PROFILE_DEPTH:
        errors.append(f"{path} exceeds maximum depth")
        return
    ref = schema.get("$ref")
    if isinstance(ref, str):
        _validate(instance, _resolve_ref(ref, root_schema), path, root_schema, errors, depth + 1)
        schema = {key: value for key, value in schema.items() if key != "$ref"}

    if "const" in schema and instance != schema["const"]:
        errors.append(f"{path} must equal {schema['const']!r}")
        return

    enum = schema.get("enum")
    if isinstance(enum, list) and instance not in enum:
        errors.append(f"{path} must be one of {enum!r}")

    expected_type = schema.get("type")
    if isinstance(expected_type, str) and not _matches_type(instance, expected_type):
        errors.append(f"{path} must be {expected_type}")
        return

    if isinstance(instance, Mapping):
        _validate_object(instance, schema, path, root_schema, errors, depth)
    elif isinstance(instance, list):
        _validate_array(instance, schema, path, root_schema, errors, depth)
    elif isinstance(instance, str):
        min_length = schema.get("minLength")
        if isinstance(min_length, int) and len(instance) < min_length:
            errors.append(f"{path} must be at least {min_length} characters")
        max_length = schema.get("maxLength")
        if isinstance(max_length, int) and len(instance) > max_length:
            errors.append(f"{path} must be at most {max_length} characters")
        pattern = schema.get("pattern")
        if pattern is not None:
            pattern_kind = _pattern_kind(pattern)
            if pattern_kind is None:
                errors.append(f"{path} pattern is unsupported")
            elif not _pattern_matches(instance, pattern, pattern_kind):
                errors.append(f"{path} must match pattern")
    elif isinstance(instance, (int, float)) and not isinstance(instance, bool):
        minimum = schema.get("minimum")
        if isinstance(minimum, (int, float)) and instance < minimum:
            errors.append(f"{path} must be >= {minimum}")
        maximum = schema.get("maximum")
        if isinstance(maximum, (int, float)) and instance > maximum:
            errors.append(f"{path} must be <= {maximum}")


def _validate_object(
    instance: Mapping[str, Any],
    schema: Mapping[str, Any],
    path: str,
    root_schema: Mapping[str, Any],
    errors: List[str],
    depth: int,
) -> None:
    required = schema.get("required", [])
    if isinstance(required, list):
        for key in required:
            if isinstance(key, str) and key not in instance:
                errors.append(f"{path}.{key} is required")

    properties = schema.get("properties", {})
    if not isinstance(properties, Mapping):
        properties = {}

    for key, child_schema in properties.items():
        if key not in instance or not isinstance(child_schema, Mapping):
            continue
        _validate(instance[key], child_schema, f"{path}.{key}", root_schema, errors, depth + 1)

    additional = schema.get("additionalProperties", True)
    for key, value in instance.items():
        if key in properties:
            continue
        if additional is False:
            errors.append(f"{path} contains an unsupported property")
        elif isinstance(additional, Mapping):
            _validate(value, additional, f"{path}[*]", root_schema, errors, depth + 1)


def _validate_array(
    instance: List[Any],
    schema: Mapping[str, Any],
    path: str,
    root_schema: Mapping[str, Any],
    errors: List[str],
    depth: int,
) -> None:
    min_items = schema.get("minItems")
    if isinstance(min_items, int) and len(instance) < min_items:
        errors.append(f"{path} must have at least {min_items} items")
    max_items = schema.get("maxItems")
    if isinstance(max_items, int) and len(instance) > max_items:
        errors.append(f"{path} must have at most {max_items} items")

    item_schema = schema.get("items")
    if not isinstance(item_schema, Mapping):
        return

    for index, item in enumerate(instance):
        _validate(item, item_schema, f"{path}[{index}]", root_schema, errors, depth + 1)


def _validate_schema_graph_depth(
    root_schema: Mapping[str, Any],
    path: str,
    errors: List[str],
) -> None:
    queue: deque[tuple[Mapping[str, Any], int, frozenset[int]]] = deque(
        [(root_schema, 0, frozenset())]
    )
    deepest_seen: dict[int, int] = {}
    while queue:
        schema, depth, ancestors = queue.popleft()
        if depth > MAX_SCHEMA_PROFILE_DEPTH:
            errors.append(f"{path} exceeds maximum depth")
            return
        schema_id = id(schema)
        previous_depth = deepest_seen.get(schema_id, -1)
        if depth <= previous_depth:
            continue
        deepest_seen[schema_id] = depth
        next_ancestors = ancestors | {schema_id}
        for child in _schema_graph_children(schema, root_schema):
            if id(child) not in next_ancestors:
                queue.append((child, depth + 1, next_ancestors))


def _schema_graph_children(
    schema: Mapping[str, Any],
    root_schema: Mapping[str, Any],
) -> List[Mapping[str, Any]]:
    children: List[Mapping[str, Any]] = []
    ref = schema.get("$ref")
    if isinstance(ref, str):
        try:
            children.append(_resolve_ref(ref, root_schema))
        except ValueError:
            pass
    for keyword in ("properties", "$defs", "definitions"):
        values = schema.get(keyword)
        if isinstance(values, Mapping):
            children.extend(child for child in values.values() if isinstance(child, Mapping))
    for keyword in ("items", "additionalProperties"):
        child = schema.get(keyword)
        if isinstance(child, Mapping):
            children.append(child)
    return children


def _validate_schema_profile(
    schema: Mapping[str, Any],
    path: str,
    errors: List[str],
    root_schema: Mapping[str, Any],
    active_refs: tuple[str, ...],
    validated_refs: set[str],
    depth: int,
) -> None:
    if depth > MAX_SCHEMA_PROFILE_DEPTH:
        errors.append(f"{path} exceeds maximum depth")
        return
    _validate_supported_keyword_shapes(schema, path, errors)

    for keyword in schema:
        if not isinstance(keyword, str) or (
            keyword not in _SUPPORTED_SCHEMA_KEYWORDS and not keyword.startswith("x-")
        ):
            errors.append(f"{path} contains an unsupported schema keyword")

    ref = schema.get("$ref")
    if ref is not None:
        if not isinstance(ref, str) or not ref.startswith("#/"):
            errors.append(f"{path}.$ref is unsupported")
        elif ref in active_refs:
            errors.append(f"{path}.$ref is cyclic")
        elif ref not in validated_refs:
            try:
                target = _resolve_ref(ref, root_schema)
            except ValueError:
                errors.append(f"{path}.$ref is unsupported")
            else:
                _validate_schema_profile(
                    target,
                    path,
                    errors,
                    root_schema,
                    (*active_refs, ref),
                    validated_refs,
                    depth + 1,
                )
                validated_refs.add(ref)

    for keyword in sorted(_UNSUPPORTED_SCHEMA_CONTAINERS):
        if keyword in schema:
            errors.append(f"{path}.{keyword} is unsupported")

    if "pattern" in schema and _pattern_kind(schema.get("pattern")) is None:
        errors.append(f"{path} pattern is unsupported")

    for keyword in ("properties", "$defs", "definitions"):
        children = schema.get(keyword)
        if children is None or not isinstance(children, Mapping):
            continue
        for child in children.values():
            child_path = f"{path}.{keyword}._member_"
            if isinstance(child, Mapping):
                _validate_schema_profile(
                    child,
                    child_path,
                    errors,
                    root_schema,
                    active_refs,
                    validated_refs,
                    depth + 1,
                )
            elif isinstance(child, bool):
                errors.append(f"{child_path} is unsupported")
            else:
                errors.append(f"{child_path} is unsupported")

    items = schema.get("items")
    if isinstance(items, Mapping):
        _validate_schema_profile(
            items,
            f"{path}.items",
            errors,
            root_schema,
            active_refs,
            validated_refs,
            depth + 1,
        )
    elif "items" in schema:
        errors.append(f"{path}.items is unsupported")

    if "additionalProperties" in schema:
        additional = schema["additionalProperties"]
        if isinstance(additional, Mapping):
            _validate_schema_profile(
                additional,
                f"{path}.additionalProperties",
                errors,
                root_schema,
                active_refs,
                validated_refs,
                depth + 1,
            )
        elif not isinstance(additional, bool):
            errors.append(f"{path}.additionalProperties is unsupported")


def _validate_supported_keyword_shapes(
    schema: Mapping[str, Any],
    path: str,
    errors: List[str],
) -> None:
    expected_type = schema.get("type")
    if "type" in schema and (
        not isinstance(expected_type, str)
        or expected_type not in {"object", "array", "string", "boolean", "integer", "number"}
    ):
        errors.append(f"{path}.type is unsupported")

    required = schema.get("required")
    if "required" in schema and (
        not isinstance(required, list) or any(not isinstance(name, str) for name in required)
    ):
        errors.append(f"{path}.required is unsupported")

    enum = schema.get("enum")
    if "enum" in schema and not isinstance(enum, list):
        errors.append(f"{path}.enum is unsupported")

    for keyword in ("properties", "$defs", "definitions"):
        if keyword in schema and not isinstance(schema[keyword], Mapping):
            errors.append(f"{path}.{keyword} is unsupported")

    for keyword in ("minLength", "maxLength", "minItems", "maxItems"):
        value = schema.get(keyword)
        if keyword in schema and (
            not isinstance(value, int) or isinstance(value, bool) or value < 0
        ):
            errors.append(f"{path}.{keyword} is unsupported")

    for keyword in ("minimum", "maximum"):
        value = schema.get(keyword)
        if keyword not in schema:
            continue
        try:
            valid_number = (
                isinstance(value, (int, float))
                and not isinstance(value, bool)
                and math.isfinite(float(value))
            )
        except (OverflowError, TypeError, ValueError):
            valid_number = False
        if not valid_number:
            errors.append(f"{path}.{keyword} is unsupported")


def _pattern_kind(pattern: Any) -> str | None:
    if not isinstance(pattern, str) or len(pattern) > MAX_SCHEMA_PATTERN_LENGTH:
        return None
    if pattern == TOOL_IDENTIFIER_SCHEMA_PATTERN:
        return "tool_identifier"
    if pattern == "":
        return "literal"
    if not pattern.isprintable() or any(char in _LITERAL_PATTERN_META for char in pattern):
        return None
    return "literal"


def _pattern_matches(instance: str, pattern: str, pattern_kind: str) -> bool:
    if pattern_kind == "tool_identifier":
        return bool(instance) and all(char in _TOOL_IDENTIFIER_CHARS for char in instance)
    return pattern in instance


def _resolve_ref(ref: str, root_schema: Mapping[str, Any]) -> Mapping[str, Any]:
    if not ref.startswith("#/"):
        raise ValueError(f"unsupported local schema ref: {ref}")

    current: Any = root_schema
    for part in ref.removeprefix("#/").split("/"):
        if not isinstance(current, Mapping):
            raise ValueError(f"schema ref {ref} points through a non-object")
        try:
            current = current[part]
        except KeyError as exc:
            raise ValueError(f"schema ref {ref} does not exist") from exc

    if not isinstance(current, Mapping):
        raise ValueError(f"schema ref {ref} does not point to an object")

    return current


def _matches_type(value: Any, expected_type: str) -> bool:
    if expected_type == "object":
        return isinstance(value, Mapping)
    if expected_type == "array":
        return isinstance(value, list)
    if expected_type == "string":
        return isinstance(value, str)
    if expected_type == "boolean":
        return isinstance(value, bool)
    if expected_type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected_type == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    return True
