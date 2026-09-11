"""Canonical parsing and risk classification for governed tool declarations."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from bisect import bisect_right
from dataclasses import dataclass
from typing import Any, List, Mapping, Optional, Sequence, Tuple


MAX_TOOL_IDENTIFIER_LENGTH = 128
TOOL_IDENTIFIER_API_PATTERN = r"^[A-Za-z0-9._:/-]+$"
TOOL_IDENTIFIER_SCHEMA_PATTERN = r"^(?!.*[\r\n])[A-Za-z0-9._:/-]+$"
HIGH_RISK_TOOL_VERBS = frozenset(
    {
        "admin",
        "charge",
        "create",
        "delete",
        "destructive",
        "destroy",
        "drop",
        "exec",
        "execute",
        "grant",
        "modify",
        "patch",
        "pay",
        "publish",
        "purge",
        "refund",
        "remove",
        "revoke",
        "run",
        "send",
        "sent",
        "submit",
        "transfer",
        "update",
        "wipe",
        "write",
    }
)

_IDENTIFIER_RE = re.compile(TOOL_IDENTIFIER_API_PATTERN)
_SAFE_SCOPE_RE = re.compile(
    r"^(?P<resource>[A-Za-z0-9_-]+)(?P<separator>[:.])(?P<action>write_internal|draft)$"
)
_SAFE_EMBEDDED_VERB_SEGMENTS = frozenset(
    {
        "absence",
        "absences",
        "absent",
        "absentee",
        "absentees",
        "administration",
        "administrative",
        "administrator",
        "administrators",
        "chargebee",
        "consent",
        "deleterious",
        "dissent",
        "dispatch",
        "dropbox",
        "dropdown",
        "endpoint",
        "endpoints",
        "execution",
        "executions",
        "executor",
        "executors",
        "executive",
        "essential",
        "essentials",
        "payroll",
        "payload",
        "payloads",
        "payment",
        "payments",
        "patchwork",
        "payable",
        "paypal",
        "representation",
        "representations",
        "present",
        "presentation",
        "presentations",
        "sentence",
        "sentences",
        "resentment",
        "resentments",
        "sentiment",
        "sentiments",
        "sentry",
        "sendgrid",
        "minimum",
        "runner",
        "runbook",
        "runbooks",
        "runtime",
        "runway",
        "trunk",
        "trunks",
        "vagrant",
        "vagrants",
        "writeup",
    }
)
_CONTEXTUAL_MUTATION_NOUNS = {
    "charges": "charge",
    "paid": "pay",
    "patches": "patch",
    "refunds": "refund",
    "resent": "send",
    "runs": "run",
}
_SAFE_INFLECTED_SEGMENT_STEMS = frozenset({"consent", "present", "represent"})
_READ_ONLY_ACTOR_ACTIONS = frozenset({"get", "list", "lookup", "read", "status"})
_SAFE_READONLY_WRITER_ACTORS = frozenset(
    {
        "copywriter",
        "ghostwriter",
        "screenwriter",
        "scriptwriter",
        "songwriter",
        "speechwriter",
        "underwriter",
        "writer",
    }
)
_IRREGULAR_ACTION_FORMS = {
    "pay": frozenset({"paid"}),
    "write": frozenset({"written", "wrote"}),
}


@dataclass(frozen=True)
class ToolRiskReason:
    """Stable, bounded explanation for a tool risk decision."""

    code: str
    source: str
    token: Optional[str] = None
    path: Optional[str] = None
    original: Optional[str] = None
    identifier_hash: Optional[str] = None


@dataclass(frozen=True)
class ToolDeclarationIssue:
    """Sanitized parser issue for one governed tool field."""

    code: str
    path: str
    message: str
    identifier_hash: Optional[str] = None


@dataclass(frozen=True)
class ToolDeclaration:
    """Validated governed tool declaration."""

    name: str
    scopes: Tuple[str, ...]
    requires_approval: bool
    path: str


@dataclass(frozen=True)
class ToolDeclarationResult:
    """Validated declarations plus terminal issues."""

    declarations: Tuple[ToolDeclaration, ...] = ()
    issues: Tuple[ToolDeclarationIssue, ...] = ()


def parse_tool_declarations(body: Mapping[str, Any]) -> ToolDeclarationResult:
    """Parse ``spec.tools.allowed`` without silently dropping malformed entries."""
    if "tools" not in body:
        return ToolDeclarationResult()
    tools = body.get("tools")
    if not isinstance(tools, Mapping):
        return ToolDeclarationResult(
            issues=(_issue("malformed_tools_section", "spec.tools", "must be an object"),)
        )
    if "allowed" not in tools:
        return ToolDeclarationResult()
    allowed = tools.get("allowed")
    if not isinstance(allowed, list):
        return ToolDeclarationResult(
            issues=(_issue("malformed_tools_allowed", "spec.tools.allowed", "must be a list"),)
        )

    declarations: List[ToolDeclaration] = []
    issues: List[ToolDeclarationIssue] = []
    seen_names: set[str] = set()
    for index, entry in enumerate(allowed):
        path = f"spec.tools.allowed[{index}]"
        declaration, entry_issues = parse_tool_entry(entry, path=path)
        issues.extend(entry_issues)
        if declaration is None:
            continue
        if declaration.name in seen_names:
            issues.append(_issue("duplicate_tool_name", f"{path}.name", "must be unique"))
            continue
        seen_names.add(declaration.name)
        declarations.append(declaration)
    return ToolDeclarationResult(tuple(declarations), tuple(issues))


def parse_tool_entry(
    entry: Any,
    *,
    path: str,
) -> tuple[Optional[ToolDeclaration], Tuple[ToolDeclarationIssue, ...]]:
    """Parse one declared or requested tool entry."""
    if not isinstance(entry, Mapping):
        return None, (_issue("malformed_tools_allowed_entry", path, "must be an object", entry),)

    issues: List[ToolDeclarationIssue] = []
    raw_name = entry.get("name")
    if not isinstance(raw_name, str) or not raw_name:
        issues.append(_issue("malformed_tool_identifier", f"{path}.name", "is required", raw_name))
        name = None
    else:
        name = _validated_identifier(raw_name, f"{path}.name", issues)

    raw_scopes = entry.get("scopes", [])
    scopes: List[str] = []
    if not isinstance(raw_scopes, list):
        issues.append(
            _issue("malformed_tool_scopes", f"{path}.scopes", "must be a list", raw_scopes)
        )
    else:
        for index, raw_scope in enumerate(raw_scopes):
            scope_path = f"{path}.scopes[{index}]"
            if not isinstance(raw_scope, str) or not raw_scope:
                issues.append(
                    _issue("malformed_tool_identifier", scope_path, "must be a string", raw_scope)
                )
                continue
            if re.fullmatch(r"[A-Za-z0-9._:/-]+:\*", raw_scope):
                issues.append(
                    _issue(
                        "wildcard_tool_scope",
                        f"{path}.scopes",
                        "contains wildcard scope",
                        raw_scope,
                    )
                )
                continue
            scope = _validated_identifier(raw_scope, scope_path, issues)
            if scope is not None:
                scopes.append(scope)

    raw_approval = entry.get("requiresApproval", False)
    if not isinstance(raw_approval, bool):
        issues.append(
            _issue(
                "malformed_tool_requires_approval",
                f"{path}.requiresApproval",
                "must be a boolean",
                raw_approval,
            )
        )

    if issues or name is None:
        return None, tuple(issues)
    return ToolDeclaration(name, tuple(scopes), raw_approval, path), ()


def tool_risk_reasons(tool: ToolDeclaration | Mapping[str, Any]) -> List[ToolRiskReason]:
    """Return deterministic risk reasons for a validated or raw tool mapping."""
    if isinstance(tool, ToolDeclaration):
        declaration = tool
    else:
        parsed_declaration, issues = parse_tool_entry(tool, path="tool")
        if issues:
            return [_reason_from_issue(issue) for issue in issues]
        if parsed_declaration is None:  # pragma: no cover - parse errors always include an issue
            return [ToolRiskReason("malformed_tool", "tool", path="tool")]
        declaration = parsed_declaration

    reasons: List[ToolRiskReason] = []
    scope_reasons = [
        reason
        for index, scope in enumerate(declaration.scopes)
        for reason in _scope_risk_reasons(scope, f"{declaration.path}.scopes[{index}]")
    ]
    safe_internal_note = _is_exact_internal_note_tool(declaration, scope_reasons)
    safe_resend_invite = _is_exact_readonly_resend_invite_tool(declaration, scope_reasons)
    for token in tokenize_tool_identifier(declaration.name):
        if token not in HIGH_RISK_TOOL_VERBS:
            continue
        if safe_internal_note and token in {"create", "write"}:
            continue
        if safe_resend_invite and token == "send":
            continue
        reasons.append(
            ToolRiskReason(
                "dangerous_tool_name_token",
                "tool_name",
                token=token,
                path=f"{declaration.path}.name",
                identifier_hash=_identifier_hash(declaration.name),
            )
        )
    reasons.extend(scope_reasons)
    return _dedupe_reasons(reasons)


def tokenize_tool_identifier(value: str) -> List[str]:
    """Extract risk tokens before applying lowercase normalization."""
    segments = [segment for segment in re.split(r"[._:/-]+", value) if segment]
    tokens: List[str] = []
    for index, segment in enumerate(segments):
        contextual_action = _contextual_mutation_action(segment)
        if contextual_action is not None:
            if _is_readonly_resource_segment(segments, index):
                continue
            tokens.append(contextual_action)
            continue
        if _is_safe_segment(segment.lower()) and not _case_boundaries(segment):
            continue
        if _is_safe_readonly_actor_segment(segments, index):
            continue
        if segment.lower() == "writer":
            tokens.append("write")
            continue
        tokens.extend(_embedded_dangerous_verbs(segment))
        spaced = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", segment)
        spaced = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", spaced)
        for part in spaced.split():
            tokens.extend(_split_uppercase_dangerous_suffix(part))

    tokens.extend(_delimiter_joined_dangerous_verbs(segments))

    expanded = list(tokens)
    run: List[str] = []
    for token in tokens + ["end-of-run"]:
        if len(token) == 1 and token.isalpha():
            run.append(token)
            continue
        if len(run) > 1:
            combined = "".join(run)
            if combined in HIGH_RISK_TOOL_VERBS:
                expanded.append(combined)
        run = []
    return expanded


def _delimiter_joined_dangerous_verbs(segments: Sequence[str]) -> List[str]:
    """Catch dangerous verbs split across one or more identifier delimiters."""
    matches: List[str] = []
    lowered = [segment.lower() for segment in segments]
    combined = "".join(lowered)
    boundaries: List[int] = []
    position = 0
    for segment in lowered[:-1]:
        position += len(segment)
        boundaries.append(position)
    for verb in sorted(HIGH_RISK_TOOL_VERBS):
        for form in sorted({verb, *_inflected_forms(verb)}, key=len, reverse=True):
            offset = combined.find(form)
            while offset >= 0:
                boundary_index = bisect_right(boundaries, offset)
                crosses_boundary = boundary_index < len(boundaries) and boundaries[
                    boundary_index
                ] < offset + len(form)
                if crosses_boundary and not _delimiter_match_overlaps_safe_segment(
                    lowered,
                    boundaries,
                    offset,
                    offset + len(form),
                ):
                    matches.append(verb)
                    break
                offset = combined.find(form, offset + 1)
            if matches and matches[-1] == verb:
                break
    matches.extend(_short_fragment_dangerous_verbs(lowered))
    return _dedupe_strings(matches)


def _short_fragment_dangerous_verbs(segments: Sequence[str]) -> List[str]:
    """Catch short action fragments abutting a benign-looking segment."""
    matches: List[str] = []
    for index, fragment in enumerate(segments[:-1]):
        following = segments[index + 1]
        if len(fragment) > 2 or not _is_safe_segment(following):
            continue
        for verb in sorted(HIGH_RISK_TOOL_VERBS):
            if not verb.startswith(fragment):
                continue
            remainder = verb[len(fragment) :]
            overlap = fragment[-1:] + remainder
            if following.startswith(remainder) or following.startswith(overlap):
                matches.append(verb)
    return matches


def _embedded_dangerous_verbs(segment: str) -> List[str]:
    lowered = segment.lower()
    case_boundaries = _case_boundaries(segment)
    if _is_safe_segment(lowered) and not case_boundaries:
        return []
    if lowered in HIGH_RISK_TOOL_VERBS:
        return [] if segment.islower() or segment.isupper() or segment.istitle() else [lowered]
    inflected = _inflected_dangerous_verbs(segment)
    if inflected:
        return inflected
    matches: List[str] = []
    for verb in sorted(HIGH_RISK_TOOL_VERBS, key=len, reverse=True):
        offset = lowered.find(verb)
        while offset >= 0:
            if not _is_safe_case_part(
                segment, offset, offset + len(verb)
            ) and not _is_benign_verb_occurrence(
                lowered, offset, verb, boundaries=sorted(case_boundaries)
            ):
                matches.append(verb)
                break
            offset = lowered.find(verb, offset + 1)
    return matches


def _inflected_dangerous_verbs(segment: str) -> List[str]:
    lowered = segment.lower()
    boundaries = _case_boundaries(segment)
    matches: List[str] = []
    for verb in sorted(HIGH_RISK_TOOL_VERBS, key=len, reverse=True):
        for form in _inflected_forms(verb):
            offset = lowered.find(form)
            while offset >= 0:
                crosses_boundary = any(
                    offset < boundary < offset + len(form) for boundary in boundaries
                )
                if not crosses_boundary and not _is_benign_verb_occurrence(
                    lowered, offset, verb, boundaries=sorted(boundaries)
                ):
                    matches.append(verb)
                    break
                offset = lowered.find(form, offset + 1)
            if matches and matches[-1] == verb:
                break
    return matches


def _inflected_forms(verb: str) -> set[str]:
    forms = {f"{verb}ed", f"{verb}ing"}
    if verb.endswith(("s", "x", "z", "ch", "sh", "o")):
        forms.add(f"{verb}es")
    else:
        forms.add(f"{verb}s")
    if verb.endswith("e"):
        forms.update({f"{verb}d", f"{verb[:-1]}ing"})
    if verb.endswith("y") and len(verb) > 1 and verb[-2] not in "aeiou":
        forms.update({f"{verb[:-1]}ied", f"{verb[:-1]}ies"})
    if verb[-1:] in {"n", "p", "t"}:
        forms.add(f"{verb}{verb[-1]}ing")
    forms.update(_IRREGULAR_ACTION_FORMS.get(verb, ()))
    return forms


def _is_safe_inflected_segment(segment: str) -> bool:
    return any(segment in {f"{stem}ed", f"{stem}ing"} for stem in _SAFE_INFLECTED_SEGMENT_STEMS)


def _is_safe_segment(segment: str) -> bool:
    return segment in _SAFE_EMBEDDED_VERB_SEGMENTS or _is_safe_inflected_segment(segment)


def _contextual_mutation_action(segment: str) -> Optional[str]:
    parts = _case_parts(segment)
    if len(parts) != 1:
        return None
    return _CONTEXTUAL_MUTATION_NOUNS.get(parts[0])


def _is_readonly_resource_segment(segments: Sequence[str], index: int) -> bool:
    """Recognize mutation-shaped nouns only when a read action establishes context."""
    if _contextual_mutation_action(segments[index]) is None:
        return False
    neighbors: List[str] = []
    if index > 0:
        neighbors.extend(_case_parts(segments[index - 1]))
    if index + 1 < len(segments):
        neighbors.extend(_case_parts(segments[index + 1]))
    return any(part in _READ_ONLY_ACTOR_ACTIONS for part in neighbors)


def _is_safe_readonly_actor_segment(segments: Sequence[str], index: int) -> bool:
    if index != 0:
        return False
    segment_parts = _case_parts(segments[index])
    if not segment_parts:
        return False
    actor = segment_parts[0]
    if actor not in _SAFE_READONLY_WRITER_ACTORS:
        return False
    if len(segment_parts) > 1:
        action = segment_parts[1]
        trailing = segment_parts[2:]
    elif len(segments) > 1:
        action_parts = _case_parts(segments[1])
        if not action_parts:
            return False
        action = action_parts[0]
        trailing = action_parts[1:]
    else:
        return False
    trailing_candidates = [*trailing, "".join(trailing)] if trailing else []
    return action in _READ_ONLY_ACTOR_ACTIONS and not any(
        part in HIGH_RISK_TOOL_VERBS or _embedded_dangerous_verbs(part)
        for part in trailing_candidates
    )


def _case_parts(segment: str) -> List[str]:
    spaced = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", segment)
    spaced = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", spaced)
    return [part.lower() for part in spaced.split()]


def _case_boundaries(segment: str) -> set[int]:
    """Return camel/Pascal/acronym transition offsets in one identifier segment."""
    boundaries = {match.start(2) for match in re.finditer(r"([A-Z]+)([A-Z][a-z])", segment)}
    boundaries.update(match.start(2) for match in re.finditer(r"([a-z0-9])([A-Z])", segment))
    return boundaries


def _is_safe_case_part(segment: str, start: int, end: int) -> bool:
    boundaries = sorted({0, len(segment), *_case_boundaries(segment)})
    return any(
        part_start <= start
        and end <= part_end
        and _is_safe_segment(segment[part_start:part_end].lower())
        for part_start, part_end in zip(boundaries, boundaries[1:])
    )


def _delimiter_match_overlaps_safe_segment(
    segments: Sequence[str],
    boundaries: Sequence[int],
    start: int,
    end: int,
) -> bool:
    first = bisect_right(boundaries, start)
    last = bisect_right(boundaries, end - 1)
    if not any(_is_safe_segment(segments[index]) for index in range(first, last + 1)):
        return False

    segment_starts = [0, *boundaries]
    segment_ends = [*boundaries, sum(len(segment) for segment in segments)]
    return any(
        not _is_safe_segment(segments[index])
        and (start > segment_starts[index] or end < segment_ends[index])
        for index in range(first, last + 1)
    )


def _is_benign_verb_occurrence(
    segment: str,
    offset: int,
    verb: str,
    *,
    boundaries: Optional[Sequence[int]] = None,
) -> bool:
    tail = segment[offset:]
    forms = {safe for safe in _SAFE_EMBEDDED_VERB_SEGMENTS if safe.startswith(verb)}
    if verb != "write":
        forms.update({f"{verb}er", f"{verb}ers"})
    if verb.endswith("e") and verb != "write":
        forms.update({f"{verb[:-1]}er", f"{verb[:-1]}ers", f"{verb[:-1]}or", f"{verb[:-1]}ors"})
    if verb.endswith("y"):
        forms.update({f"{verb[:-1]}ier", f"{verb[:-1]}iers"})
    boundary_set = set(boundaries or ())
    return any(
        tail.startswith(form)
        and (offset + len(form) == len(segment) or offset + len(form) in boundary_set)
        and not any(offset < boundary < offset + len(form) for boundary in boundary_set)
        for form in forms
    )


def is_exact_safe_scope(scope: str) -> bool:
    """Return whether the scope uses one exact documented safe action form."""
    match = _SAFE_SCOPE_RE.fullmatch(scope)
    if match is None:
        return False
    return not _dangerous_tokens(match.group("resource"))


def _scope_risk_reasons(scope: str, path: str) -> List[ToolRiskReason]:
    safe_match = _SAFE_SCOPE_RE.fullmatch(scope)
    inspected = (
        safe_match.group("resource")
        if safe_match
        else re.sub(r"(?<=[:.])write_internal(?=[:./-]|$)", "internal", scope)
    )
    inspected_tokens = tokenize_tool_identifier(inspected)
    dangerous_tokens = _dedupe_strings(
        [token for token in inspected_tokens if token in HIGH_RISK_TOOL_VERBS]
        + _dangerous_scope_prefixes(inspected)
    )
    reasons = [
        ToolRiskReason(
            "dangerous_tool_scope_token",
            "tool_scope",
            token=token,
            path=path,
            identifier_hash=_identifier_hash(scope),
        )
        for token in dangerous_tokens
    ]
    if safe_match:
        return reasons
    tokens = tokenize_tool_identifier(scope)
    if not reasons and (
        len(re.findall(r"[:./]", scope)) > 1
        or "draft" in tokens
        or ("write" in tokens and "internal" in tokens)
    ):
        reasons.append(
            ToolRiskReason(
                "ambiguous_tool_scope",
                "tool_scope",
                path=path,
                identifier_hash=_identifier_hash(scope),
            )
        )
    return reasons


def _dangerous_scope_prefixes(scope: str) -> List[str]:
    matches: List[str] = []
    segments = [segment for segment in re.split(r"[._:/-]+", scope) if segment]
    for index, segment in enumerate(segments):
        if _is_readonly_resource_segment(segments, index):
            continue
        if _is_safe_readonly_actor_segment(segments, index):
            continue
        lowered = segment.lower()
        for verb in sorted(HIGH_RISK_TOOL_VERBS):
            if lowered.startswith(verb) and not _is_benign_verb_occurrence(lowered, 0, verb):
                matches.append(verb)
    return matches


def _dangerous_tokens(value: str) -> List[str]:
    return [token for token in tokenize_tool_identifier(value) if token in HIGH_RISK_TOOL_VERBS]


def _split_uppercase_dangerous_suffix(part: str) -> List[str]:
    lowered = part.lower()
    if part.isupper() and lowered not in HIGH_RISK_TOOL_VERBS:
        for verb in sorted(HIGH_RISK_TOOL_VERBS, key=len, reverse=True):
            if lowered.endswith(verb) and lowered != verb:
                prefix = lowered[: -len(verb)]
                return [prefix, verb] if prefix else [verb]
    return [lowered]


def _is_exact_internal_note_tool(
    declaration: ToolDeclaration,
    scope_reasons: Sequence[ToolRiskReason],
) -> bool:
    if scope_reasons or not declaration.scopes:
        return False
    if declaration.name != "jira.create_internal_note":
        return False
    if not all(
        re.fullmatch(r"[A-Za-z0-9_-]+[:.]write_internal", scope) for scope in declaration.scopes
    ):
        return False
    tokens = tokenize_tool_identifier(declaration.name)
    return tokens == ["jira", "create", "internal", "note"]


def _is_exact_readonly_resend_invite_tool(
    declaration: ToolDeclaration,
    scope_reasons: Sequence[ToolRiskReason],
) -> bool:
    if scope_reasons or declaration.name not in {"okta.resend_invite", "okta.resendInvite"}:
        return False
    return bool(declaration.scopes) and all(
        re.fullmatch(r"[A-Za-z0-9_-]+[:.]read", scope) for scope in declaration.scopes
    )


def _validated_identifier(
    value: Any,
    path: str,
    issues: List[ToolDeclarationIssue],
) -> Optional[str]:
    if not isinstance(value, str) or not value:
        issues.append(
            _issue("malformed_tool_identifier", path, "must be a non-empty string", value)
        )
        return None
    normalized = unicodedata.normalize("NFKC", value)
    if normalized != value:
        issues.append(
            _issue("ambiguous_tool_identifier", path, "has ambiguous normalization", value)
        )
        return None
    if len(value) > MAX_TOOL_IDENTIFIER_LENGTH:
        issues.append(_issue("tool_identifier_too_long", path, "is too long", value))
        return None
    if not value.isascii() or not value.isprintable() or any(char.isspace() for char in value):
        issues.append(_issue("malformed_tool_identifier", path, "has invalid characters", value))
        return None
    if _IDENTIFIER_RE.fullmatch(value) is None:
        issues.append(
            _issue("malformed_tool_identifier", path, "has unsupported punctuation", value)
        )
        return None
    return value


def _issue(
    code: str,
    path: str,
    problem: str,
    raw_value: Any = None,
) -> ToolDeclarationIssue:
    return ToolDeclarationIssue(
        code=code,
        path=path,
        message=f"{path} {problem}",
        identifier_hash=_identifier_hash(raw_value) if raw_value is not None else None,
    )


def _reason_from_issue(issue: ToolDeclarationIssue) -> ToolRiskReason:
    source = "tool_scope" if ".scopes" in issue.path else "tool_name"
    return ToolRiskReason(
        issue.code,
        source,
        path=issue.path,
        identifier_hash=issue.identifier_hash,
    )


def _identifier_hash(value: Any) -> str:
    encoded = str(type(value).__name__ if not isinstance(value, str) else value).encode(
        "utf-8", errors="replace"
    )
    return "sha256:" + hashlib.sha256(encoded).hexdigest()[:16]


def _dedupe_reasons(reasons: Sequence[ToolRiskReason]) -> List[ToolRiskReason]:
    unique: List[ToolRiskReason] = []
    seen = set()
    for reason in reasons:
        key = (
            reason.code,
            reason.source,
            reason.token,
            reason.path,
            reason.original,
            reason.identifier_hash,
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(reason)
    return unique


def _dedupe_strings(values: Sequence[str]) -> List[str]:
    return list(dict.fromkeys(values))
