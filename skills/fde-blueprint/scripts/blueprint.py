#!/usr/bin/env python3
"""Build deterministic FDE blueprint packets from an adaptive interview."""

from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any


OK = 0
INPUT_ERROR = 2
VALIDATION_ERROR = 3
IO_ERROR = 4
MISSING = object()
SKILL_DIR = Path(__file__).resolve().parents[1]
ASSETS_DIR = SKILL_DIR / "assets"
TEMPLATES_DIR = ASSETS_DIR / "templates"
PACKET_FILES = (
    "blueprint.json",
    "BLUEPRINT.md",
    "ARCHITECTURE.md",
    "SECURITY.md",
    "IMPLEMENTATION_PLAN.md",
    "ACCEPTANCE.md",
    "SOURCES.md",
    "SCAFFOLD_PLAN.json",
    "EVIDENCE_MANIFEST.json",
)


class BlueprintError(Exception):
    """An expected command failure with a stable process exit code."""

    def __init__(self, message: str, code: int, details: Sequence[str] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.details = list(details or [])


def load_json(path: Path) -> dict[str, Any]:
    """Load a JSON object or raise a stable input error."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise BlueprintError(f"file not found: {path}", INPUT_ERROR) from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise BlueprintError(f"cannot read JSON from {path}: {exc}", INPUT_ERROR) from exc
    if not isinstance(data, dict):
        raise BlueprintError(f"expected a JSON object in {path}", INPUT_ERROR)
    return data


def dump_json(data: Any) -> str:
    """Serialize JSON in the canonical packet format."""
    return json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def get_path(data: Mapping[str, Any], dotted_path: str) -> Any:
    """Return a nested value or the MISSING sentinel."""
    current: Any = data
    for part in dotted_path.split("."):
        if not isinstance(current, Mapping) or part not in current:
            return MISSING
        current = current[part]
    return current


def set_path(data: dict[str, Any], dotted_path: str, value: Any) -> None:
    """Set a dotted path in a nested dictionary."""
    parts = dotted_path.split(".")
    current = data
    for part in parts[:-1]:
        child = current.setdefault(part, {})
        if not isinstance(child, dict):
            raise BlueprintError(f"answer path collides with a value: {dotted_path}", INPUT_ERROR)
        current = child
    current[parts[-1]] = value


def is_answered(value: Any) -> bool:
    """Return whether a value is substantive enough to count as an answer."""
    if value is MISSING or value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return bool(value)
    return True


def load_assets() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Load the versioned question bank, capability packs, and product catalog."""
    questions = load_json(ASSETS_DIR / "questionnaire.json")
    packs = load_json(ASSETS_DIR / "capability-packs.json")
    catalog = load_json(ASSETS_DIR / "catalog.json")
    return questions, packs, catalog


def selected_capabilities(answers: Mapping[str, Any]) -> list[str]:
    """Read normalized capability IDs from interview answers."""
    value = get_path(answers, "capabilities")
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def condition_state(question: Mapping[str, Any], answers: Mapping[str, Any]) -> bool | None:
    """Evaluate a question condition; None means its dependency is unanswered."""
    condition = question.get("when")
    if not isinstance(condition, Mapping):
        return True
    actual = get_path(answers, str(condition["path"]))
    if actual is MISSING:
        return None
    if "equals" in condition:
        return actual == condition["equals"]
    if "one_of" in condition:
        return actual in condition["one_of"]
    if "contains" in condition:
        expected = condition["contains"]
        return expected in actual if isinstance(actual, (list, str)) else False
    return False


def applies_to_capabilities(question: Mapping[str, Any], capabilities: Sequence[str]) -> bool:
    """Return whether a question belongs to the selected capability packs."""
    applies_to = question.get("applies_to", ["*"])
    return "*" in applies_to or bool(set(applies_to).intersection(capabilities))


def active_questions(
    bank: Mapping[str, Any],
    capabilities: Sequence[str],
    answers: Mapping[str, Any],
    *,
    include_unresolved_conditions: bool,
) -> list[dict[str, Any]]:
    """Select questions for the current capability and answer state."""
    active = []
    for question in bank["questions"]:
        if not applies_to_capabilities(question, capabilities):
            continue
        state = condition_state(question, answers)
        if state is True or (state is None and include_unresolved_conditions):
            active.append(question)
    return active


def question_errors(question: Mapping[str, Any], value: Any) -> list[str]:
    """Validate one supplied answer against its declared question type."""
    kind = question["type"]
    question_id = question["id"]
    errors: list[str] = []
    if kind in {"text", "choice"} and not isinstance(value, str):
        errors.append(f"{question_id}: expected a string")
    valid_string_list = isinstance(value, list) and all(
        isinstance(item, str) for item in value
    )
    if kind in {"multi_choice", "multi_text"}:
        if not valid_string_list:
            errors.append(f"{question_id}: expected a list of strings")
    choices = question.get("choices")
    if choices and isinstance(value, str) and value not in choices:
        errors.append(f"{question_id}: unsupported choice {value!r}")
    if choices and valid_string_list:
        unknown = sorted(set(value).difference(choices))
        if unknown:
            errors.append(f"{question_id}: unsupported choices {', '.join(unknown)}")
    return errors


def validate_answers(
    answers: Mapping[str, Any], bank: Mapping[str, Any], packs: Mapping[str, Any]
) -> tuple[list[str], list[dict[str, Any]]]:
    """Validate minimum render inputs and return unresolved active questions."""
    errors: list[str] = []
    required_core = {
        "engagement.project_name": "project name",
        "engagement.mode": "engagement mode",
        "engagement.business_outcome": "business outcome",
        "capabilities": "at least one capability",
        "application.primary_language": "primary language",
        "application.framework": "framework",
    }
    for path, label in required_core.items():
        if not is_answered(get_path(answers, path)):
            errors.append(f"missing {label} at {path}")

    known_packs = {pack["id"] for pack in packs["packs"]}
    capabilities = selected_capabilities(answers)
    unknown_packs = sorted(set(capabilities).difference(known_packs))
    if unknown_packs:
        errors.append(f"unknown capabilities: {', '.join(unknown_packs)}")

    open_questions: list[dict[str, Any]] = []
    for question in active_questions(
        bank, capabilities, answers, include_unresolved_conditions=False
    ):
        value = get_path(answers, question["answer_path"])
        if is_answered(value):
            errors.extend(question_errors(question, value))
        elif question.get("required", False):
            open_questions.append(question)
    return errors, open_questions


def validate_project(project: Any) -> list[str]:
    """Validate the normalized project summary."""
    errors = []
    if not isinstance(project, Mapping):
        return ["blueprint project must be an object"]
    for field in (
        "name",
        "engagement_mode",
        "business_outcome",
        "primary_language",
        "framework",
    ):
        if not isinstance(project.get(field), str) or not project[field].strip():
            errors.append(f"blueprint project.{field} must be a non-empty string")
    return errors


def validate_capabilities(capabilities: Any, known_packs: set[str]) -> list[str]:
    """Validate normalized capability identifiers."""
    if not isinstance(capabilities, list) or not capabilities:
        return ["blueprint capabilities must be a non-empty list"]
    if any(not isinstance(item, str) for item in capabilities):
        return ["blueprint capabilities must contain only strings"]
    unknown = sorted(set(capabilities).difference(known_packs))
    return [f"unknown capabilities: {', '.join(unknown)}"] if unknown else []


def validate_evidence(evidence: Any) -> list[str]:
    """Validate the blueprint's pending-only evidence records."""
    if not isinstance(evidence, list):
        return ["blueprint evidence must be a list"]
    errors = []
    malformed = [
        str(index) for index, item in enumerate(evidence) if not isinstance(item, Mapping)
    ]
    if malformed:
        errors.append(f"evidence items must be objects at indexes: {', '.join(malformed)}")
    valid_evidence = [item for item in evidence if isinstance(item, Mapping)]
    bad_statuses = [
        str(item.get("id", "unknown"))
        for item in valid_evidence
        if item.get("status") != "pending"
    ]
    if bad_statuses:
        errors.append(f"evidence must start pending: {', '.join(bad_statuses)}")
    evidence_ids = [item.get("id") for item in valid_evidence]
    if any(not isinstance(item, str) for item in evidence_ids):
        errors.append("evidence IDs must be strings")
    elif len(evidence_ids) != len(set(evidence_ids)):
        errors.append("evidence IDs must be unique")
    return errors


def validate_blueprint(data: Mapping[str, Any], packs: Mapping[str, Any]) -> list[str]:
    """Validate packet-level invariants without a third-party schema runtime."""
    required = {
        "schema_version",
        "project",
        "capabilities",
        "answers",
        "selected_products",
        "scaffold_plan",
        "security_invariants",
        "acceptance_criteria",
        "evidence",
        "open_decisions",
        "provenance",
    }
    errors = [f"missing blueprint field: {key}" for key in sorted(required.difference(data))]
    if data.get("schema_version") != "1.0":
        errors.append("blueprint schema_version must be 1.0")
    known_packs = {pack["id"] for pack in packs["packs"]}
    errors.extend(validate_project(data.get("project")))
    errors.extend(validate_capabilities(data.get("capabilities"), known_packs))
    errors.extend(validate_evidence(data.get("evidence")))
    return errors


def normalized_question(question: Mapping[str, Any]) -> dict[str, Any]:
    """Return the stable public shape for a question."""
    keys = ("id", "section", "answer_path", "prompt", "type", "choices", "required", "when")
    return {key: question[key] for key in keys if key in question}


def markdown_questions(questions: Sequence[Mapping[str, Any]]) -> str:
    """Render a human-readable question list."""
    lines = ["# FDE blueprint interview", ""]
    current_section = None
    for question in questions:
        if question["section"] != current_section:
            current_section = question["section"]
            lines.extend([f"## {current_section.replace('-', ' ').title()}", ""])
        required = "required" if question.get("required") else "optional"
        lines.append(f"- **{question['id']}** ({required}): {question['prompt']}")
        if choices := question.get("choices"):
            lines.append(f"  Choices: {', '.join(choices)}")
        if condition := question.get("when"):
            lines.append(f"  Condition: {json.dumps(condition, sort_keys=True)}")
    return "\n".join(lines) + "\n"


def catalog_rows(products: Sequence[Mapping[str, Any]]) -> str:
    """Render compact catalog rows for terminal browsing."""
    headers = ("ID", "NAME", "DELIVERY", "LICENSE", "REUSE")
    values = [
        (
            product["id"],
            product["name"],
            product["delivery"],
            product["license_class"],
            product["reuse"],
        )
        for product in products
    ]
    if not values:
        return "No catalog entries matched.\n"
    widths = [
        max(len(headers[index]), *(len(str(row[index])) for row in values)) for index in range(5)
    ]
    lines = ["  ".join(value.ljust(widths[index]) for index, value in enumerate(headers))]
    lines.append("  ".join("-" * width for width in widths))
    lines.extend(
        "  ".join(str(value).ljust(widths[index]) for index, value in enumerate(row))
        for row in values
    )
    return "\n".join(lines) + "\n"


def parse_interview_value(question: Mapping[str, Any], raw: str) -> Any:
    """Parse one terminal answer according to its declared type."""
    raw = raw.strip()
    if question["type"] in {"multi_choice", "multi_text"}:
        value = [item.strip() for item in raw.split(",") if item.strip()]
    else:
        value = raw
    errors = question_errors(question, value)
    if errors:
        raise ValueError(errors[0])
    return value


def prompt_for_question(question: Mapping[str, Any]) -> Any:
    """Prompt repeatedly until a valid answer or an optional blank is supplied."""
    print(f"\n[{question['section']}] {question['prompt']}")
    if choices := question.get("choices"):
        print("Choices: " + ", ".join(choices))
    if question["type"] in {"multi_choice", "multi_text"}:
        print("Enter comma-separated values.")
    while True:
        try:
            raw = input("> ")
        except EOFError as exc:
            raise BlueprintError("interview input ended before completion", INPUT_ERROR) from exc
        if not raw.strip() and not question.get("required", False):
            return MISSING
        if not raw.strip():
            print("This answer is required.", file=sys.stderr)
            continue
        try:
            return parse_interview_value(question, raw)
        except ValueError as exc:
            print(str(exc), file=sys.stderr)


def atomic_write(path: Path, content: str) -> None:
    """Write a text file atomically in its destination directory."""
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=path.parent, delete=False
        ) as handle:
            handle.write(content)
            temp_path = Path(handle.name)
        temp_path.replace(path)
    except OSError as exc:
        raise BlueprintError(f"cannot write {path}: {exc}", IO_ERROR) from exc


def bullet_list(values: Iterable[Any], empty: str = "- None supplied.") -> str:
    """Render values as Markdown bullets without inventing content."""
    items = [str(value) for value in values if value not in (None, "", [])]
    return "\n".join(f"- {item}" for item in items) if items else empty


def flatten_strings(value: Any) -> Iterable[str]:
    """Yield every string contained in a nested answer object."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, Mapping):
        for child in value.values():
            yield from flatten_strings(child)
    elif isinstance(value, list):
        for child in value:
            yield from flatten_strings(child)


def products_from_answers(
    answers: Mapping[str, Any], catalog: Mapping[str, Any]
) -> list[dict[str, Any]]:
    """Resolve exact catalog IDs mentioned by the interview."""
    mentioned = set(flatten_strings(answers))
    selected = []
    for product in catalog["products"]:
        if product["id"] not in mentioned:
            continue
        selected.append(
            {
                "id": product["id"],
                "name": product["name"],
                "categories": product["categories"],
                "delivery": product["delivery"],
                "license_class": product["license_class"],
                "reuse": product["reuse"],
                "sources": [source["url"] for source in product["sources"]],
            }
        )
    return selected


def evidence_id(capability: str, index: int, artifact: str) -> str:
    """Create a deterministic evidence identifier."""
    slug = re.sub(r"[^a-z0-9]+", "-", artifact.lower()).strip("-")
    return f"{capability}-{index:02d}-{slug}"


def project_from_answers(answers: Mapping[str, Any]) -> dict[str, Any]:
    """Build the normalized project summary."""
    language = get_path(answers, "application.primary_language")
    if language == "other":
        custom_language = get_path(answers, "application.other_language")
        if is_answered(custom_language):
            language = custom_language
    repository_path = get_path(answers, "engagement.repository_path")
    if repository_path is MISSING:
        repository_path = None
    return {
        "name": get_path(answers, "engagement.project_name"),
        "engagement_mode": get_path(answers, "engagement.mode"),
        "business_outcome": get_path(answers, "engagement.business_outcome"),
        "repository_path": repository_path,
        "primary_language": language,
        "framework": get_path(answers, "application.framework"),
    }


def capability_contracts(chosen_packs: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Expand selected packs into plan, invariant, acceptance, and evidence records."""
    return {
        "scaffold_plan": [
            {
                "capability": pack["id"],
                "title": pack["title"],
                "outcome": pack["outcome"],
                "modules": pack["scaffold_modules"],
            }
            for pack in chosen_packs
        ],
        "security_invariants": [
            {"capability": pack["id"], "statement": statement}
            for pack in chosen_packs
            for statement in pack["invariants"]
        ],
        "acceptance_criteria": [
            {"capability": pack["id"], "criterion": criterion}
            for pack in chosen_packs
            for criterion in pack["acceptance"]
        ],
        "evidence": [
            {
                "id": evidence_id(pack["id"], index, artifact),
                "capability": pack["id"],
                "artifact": artifact,
                "status": "pending",
                "proof_command": None,
                "artifact_path": None,
            }
            for pack in chosen_packs
            for index, artifact in enumerate(pack["evidence"], start=1)
        ],
    }


def unresolved_decisions(
    open_questions: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Normalize unanswered active questions for packet consumers."""
    return [
        {
            "question_id": question["id"],
            "answer_path": question["answer_path"],
            "prompt": question["prompt"],
            "required": bool(question.get("required")),
        }
        for question in open_questions
    ]


def build_blueprint(
    answers: dict[str, Any],
    packs: Mapping[str, Any],
    catalog: Mapping[str, Any],
    open_questions: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Normalize interview answers into the versioned blueprint contract."""
    pack_by_id = {pack["id"]: pack for pack in packs["packs"]}
    chosen_packs = [pack_by_id[pack_id] for pack_id in selected_capabilities(answers)]
    contracts = capability_contracts(chosen_packs)
    reuse_answer = get_path(answers, "provenance.reuse_policy")
    if is_answered(reuse_answer):
        reuse_policy = f"Owner selection: {reuse_answer}. {catalog['purpose']}"
    else:
        reuse_policy = catalog["purpose"]
    return {
        "schema_version": "1.0",
        "project": project_from_answers(answers),
        "capabilities": selected_capabilities(answers),
        "answers": answers,
        "selected_products": products_from_answers(answers, catalog),
        **contracts,
        "open_decisions": unresolved_decisions(open_questions),
        "provenance": {
            "catalog_version": catalog["catalog_version"],
            "catalog_researched_on": catalog["researched_on"],
            "generator": "fde-blueprint/scripts/blueprint.py",
            "source_reuse_policy": reuse_policy,
        },
    }


def render_template(name: str, values: Mapping[str, str]) -> str:
    """Render a bundled template and reject unresolved placeholders."""
    template = (TEMPLATES_DIR / name).read_text(encoding="utf-8")
    for key, value in values.items():
        template = template.replace("{{" + key + "}}", value)
    leftovers = sorted(set(re.findall(r"{{([a-z_]+)}}", template)))
    if leftovers:
        raise BlueprintError(
            f"template {name} has unresolved values: {', '.join(leftovers)}",
            VALIDATION_ERROR,
        )
    return template


def mapping_bullets(value: Any) -> str:
    """Render a nested answer section as readable Markdown."""
    if not isinstance(value, Mapping) or not value:
        return "- Not supplied."
    lines = []
    for key, child in value.items():
        label = key.replace("_", " ").title()
        if isinstance(child, list):
            rendered = ", ".join(str(item) for item in child) or "Not supplied"
        elif isinstance(child, Mapping):
            rendered = json.dumps(child, sort_keys=True)
        else:
            rendered = str(child)
        lines.append(f"- **{label}:** {rendered}")
    return "\n".join(lines)


def module_sections(blueprint: Mapping[str, Any]) -> str:
    """Render capability modules grouped by pack."""
    sections = []
    for package in blueprint["scaffold_plan"]:
        sections.append(f"### {package['title']}\n\n{bullet_list(package['modules'])}")
    return "\n\n".join(sections)


def scope_sections(blueprint: Mapping[str, Any]) -> str:
    """Render capability outcomes for the blueprint overview."""
    return "\n\n".join(
        f"### {package['title']}\n\n{package['outcome']}"
        for package in blueprint["scaffold_plan"]
    )


def product_summary(blueprint: Mapping[str, Any]) -> str:
    """Render selected product decisions with licensing boundaries."""
    if not blueprint["selected_products"]:
        return (
            "No exact catalog product has been selected yet. "
            "Candidate selection remains an owner decision."
        )
    lines = []
    for product in blueprint["selected_products"]:
        lines.append(
            f"- **{product['name']}** ({product['id']}): {product['delivery']}; "
            f"{product['license_class']}; reuse mode {product['reuse']}."
        )
    return "\n".join(lines)


def open_decision_list(blueprint: Mapping[str, Any]) -> str:
    """Render unresolved interview decisions."""
    decisions = blueprint["open_decisions"]
    if not decisions:
        return "- None. The decisions are complete; implementation evidence is still pending."
    return "\n".join(
        f"- {item['question_id']} -> {item['answer_path']}: {item['prompt']}"
        for item in decisions
    )


def mermaid_nodes(blueprint: Mapping[str, Any]) -> str:
    """Build a small deterministic trust-flow diagram."""
    lines = [
        "    User[User or operator] --> App[Application boundary]",
        "    App --> Data[(Primary data store)]",
    ]
    for index, package in enumerate(blueprint["scaffold_plan"], start=1):
        label = package["title"].replace('"', "'")
        lines.append(f'    App --> C{index}["{label}"]')
    if blueprint["selected_products"]:
        lines.append("    App --> Provider[Approved external provider boundary]")
    return "\n".join(lines)


def security_threats(blueprint: Mapping[str, Any]) -> str:
    """Derive threat exercises from selected capabilities."""
    shared = [
        "Untrusted input reaches a privileged operation or rendered output.",
        "A secret, token, customer payload, or sensitive identifier appears in logs or artifacts.",
        "A retry or replay duplicates a non-idempotent external effect.",
    ]
    capability_threats = {
        "multi-tenant-saas": (
            "A tenant attempts object, property, function, cache, job, file, "
            "and inference access across the tenant boundary."
        ),
        "enterprise-sso": (
            "An identity response is replayed, redirected, or bound to the wrong organization."
        ),
        "connector-pack": (
            "A compromised or revoked provider credential is reused across tenant "
            "or connection boundaries."
        ),
        "secure-rag": (
            "Retrieved content carries unauthorized context or prompt instructions "
            "into generation."
        ),
        "webhook-engine": (
            "A forged, stale, duplicated, oversized, or reordered event reaches a handler."
        ),
        "pii-redaction": (
            "A detector miss, false positive, encoded value, or nested structure "
            "defeats the selected policy."
        ),
        "usage-metering": (
            "Duplicate, late, corrected, or tenant-misattributed events change "
            "a billable total."
        ),
    }
    selected = [
        capability_threats[item]
        for item in blueprint["capabilities"]
        if item in capability_threats
    ]
    return bullet_list([*shared, *selected])


def implementation_packages(blueprint: Mapping[str, Any]) -> str:
    """Render dependency-conscious implementation packages."""
    sections = []
    criteria_by_capability: dict[str, list[str]] = {}
    for item in blueprint["acceptance_criteria"]:
        criteria_by_capability.setdefault(item["capability"], []).append(item["criterion"])
    for index, package in enumerate(blueprint["scaffold_plan"], start=1):
        sections.append(
            f"## {index}. {package['title']}\n\n"
            f"Outcome: {package['outcome']}\n\n"
            f"Modules:\n\n{bullet_list(package['modules'])}\n\n"
            f"Exit evidence:\n\n"
            f"{bullet_list(criteria_by_capability[package['capability']])}"
        )
    return "\n\n".join(sections)


def source_sections(blueprint: Mapping[str, Any], catalog: Mapping[str, Any]) -> str:
    """Render primary-source provenance for exact selected products."""
    selected_ids = {product["id"] for product in blueprint["selected_products"]}
    catalog_entries = [
        product for product in catalog["products"] if product["id"] in selected_ids
    ]
    if not catalog_entries:
        return "No exact catalog product is selected. Review candidates in assets/catalog.json."
    sections = []
    for product in catalog_entries:
        sources = "\n".join(
            f"- [{source['kind']}]({source['url']}) - "
            f"{source['status']}; checked {source['checked']}"
            for source in product["sources"]
        )
        sections.append(
            f"## {product['name']}\n\n"
            f"- Delivery: {product['delivery']}\n"
            f"- License: {product['license_class']} / {product['license_id']}\n"
            f"- Reuse mode: {product['reuse']}\n"
            f"- Fit: {product['fit']}\n\n{sources}"
        )
    return "\n\n".join(sections)


def render_overview_doc(blueprint: Mapping[str, Any]) -> str:
    """Render the blueprint overview document."""
    answers = blueprint["answers"]
    project = blueprint["project"]
    non_goals = get_path(answers, "engagement.non_goals")
    if non_goals is MISSING:
        non_goals = []
    return render_template(
        "BLUEPRINT.md.tmpl",
        {
            "project_name": project["name"],
            "business_outcome": project["business_outcome"],
            "engagement_mode": project["engagement_mode"],
            "repository_path": project["repository_path"] or "Not supplied for this mode",
            "primary_stack": f"{project['primary_language']} / {project['framework']}",
            "capability_names": ", ".join(
                item["title"] for item in blueprint["scaffold_plan"]
            ),
            "scope_sections": scope_sections(blueprint),
            "non_goals": bullet_list(non_goals),
            "selected_product_summary": product_summary(blueprint),
            "open_decisions": open_decision_list(blueprint),
        },
    )


def render_architecture_doc(blueprint: Mapping[str, Any]) -> str:
    """Render the architecture and trust-flow document."""
    answers = blueprint["answers"]
    invariants = [
        f"**{item['capability']}** - {item['statement']}"
        for item in blueprint["security_invariants"]
    ]
    return render_template(
        "ARCHITECTURE.md.tmpl",
        {
            "architecture_context": mapping_bullets(get_path(answers, "application")),
            "module_sections": module_sections(blueprint),
            "mermaid_nodes": mermaid_nodes(blueprint),
            "cross_cutting_contracts": bullet_list(invariants),
            "deployment_context": mapping_bullets(get_path(answers, "deployment")),
        },
    )


def render_security_doc(blueprint: Mapping[str, Any]) -> str:
    """Render the security and privacy contract."""
    answers = blueprint["answers"]
    invariants = [
        f"**{item['capability']}** - {item['statement']}"
        for item in blueprint["security_invariants"]
    ]
    context = "\n".join(
        [
            "### Data\n\n" + mapping_bullets(get_path(answers, "data")),
            "### Security\n\n" + mapping_bullets(get_path(answers, "security")),
        ]
    )
    return render_template(
        "SECURITY.md.tmpl",
        {
            "security_context": context,
            "security_invariants": bullet_list(invariants),
            "threat_scenarios": security_threats(blueprint),
        },
    )


def render_acceptance_doc(blueprint: Mapping[str, Any]) -> str:
    """Render behavioral acceptance and pending evidence."""
    acceptance = [
        f"**{item['capability']}** - {item['criterion']}"
        for item in blueprint["acceptance_criteria"]
    ]
    evidence = [
        f"{item['id']} - {item['artifact']} ({item['status']})"
        for item in blueprint["evidence"]
    ]
    return render_template(
        "ACCEPTANCE.md.tmpl",
        {
            "acceptance_criteria": bullet_list(acceptance),
            "evidence_items": bullet_list(evidence),
        },
    )


def language_profile_for(
    blueprint: Mapping[str, Any], catalog: Mapping[str, Any]
) -> Mapping[str, Any] | None:
    """Resolve the catalog language profile for a normalized project."""
    language = blueprint["project"]["primary_language"]
    return next(
        (profile for profile in catalog["language_profiles"] if profile["id"] == language),
        None,
    )


def build_machine_packet(
    blueprint: Mapping[str, Any], catalog: Mapping[str, Any]
) -> dict[str, str]:
    """Render the JSON files consumed by later generators and evidence tools."""
    return {
        "blueprint.json": dump_json(blueprint),
        "SCAFFOLD_PLAN.json": dump_json(
            {
                "schema_version": "1.0",
                "project": blueprint["project"],
                "language_profile": language_profile_for(blueprint, catalog),
                "packages": blueprint["scaffold_plan"],
                "generator_boundary": "plan-only; no application source emitted",
            }
        ),
        "EVIDENCE_MANIFEST.json": dump_json(
            {
                "schema_version": "1.0",
                "claim_boundary": "All evidence starts pending and requires retained proof.",
                "items": blueprint["evidence"],
            }
        ),
    }


def build_packet(blueprint: dict[str, Any], catalog: Mapping[str, Any]) -> dict[str, str]:
    """Render every deterministic file in an FDE blueprint packet."""
    packet = build_machine_packet(blueprint, catalog)
    packet.update(
        {
            "BLUEPRINT.md": render_overview_doc(blueprint),
            "ARCHITECTURE.md": render_architecture_doc(blueprint),
            "SECURITY.md": render_security_doc(blueprint),
            "IMPLEMENTATION_PLAN.md": render_template(
                "IMPLEMENTATION_PLAN.md.tmpl",
                {"implementation_packages": implementation_packages(blueprint)},
            ),
            "ACCEPTANCE.md": render_acceptance_doc(blueprint),
            "SOURCES.md": render_template(
                "SOURCES.md.tmpl",
                {
                    "catalog_date": catalog["researched_on"],
                    "source_sections": source_sections(blueprint, catalog),
                    "reuse_policy": blueprint["provenance"]["source_reuse_policy"],
                },
            ),
        }
    )
    return packet


def write_packet(packet: Mapping[str, str], output_dir: Path, force: bool) -> None:
    """Write a packet while refusing to replace files unless explicitly allowed."""
    conflicts = [str(output_dir / name) for name in packet if (output_dir / name).exists()]
    if conflicts and not force:
        raise BlueprintError("refusing to overwrite generated files", IO_ERROR, conflicts)
    for name, content in packet.items():
        atomic_write(output_dir / name, content)


def command_catalog(args: argparse.Namespace) -> int:
    """List researched products and standards."""
    _, _, catalog = load_assets()
    products = catalog["products"]
    if args.category:
        products = [
            product for product in products if args.category in product["categories"]
        ]
    if args.format == "json":
        print(
            dump_json(
                {
                    "catalog_version": catalog["catalog_version"],
                    "researched_on": catalog["researched_on"],
                    "products": products,
                }
            ),
            end="",
        )
    else:
        print(catalog_rows(products), end="")
    return OK


def command_questions(args: argparse.Namespace) -> int:
    """List adaptive questions for selected capabilities."""
    bank, packs, _ = load_assets()
    answers = load_json(Path(args.answers)) if args.answers else {}
    known = {pack["id"] for pack in packs["packs"]}
    capabilities = args.capability or selected_capabilities(answers)
    if not capabilities and not args.answers:
        capabilities = [pack["id"] for pack in packs["packs"]]
    if unknown := sorted(set(capabilities).difference(known)):
        raise BlueprintError(f"unknown capabilities: {', '.join(unknown)}", INPUT_ERROR)
    questions = active_questions(
        bank,
        capabilities,
        answers,
        include_unresolved_conditions=not bool(args.answers),
    )
    normalized = [normalized_question(question) for question in questions]
    if args.format == "json":
        print(dump_json({"capabilities": capabilities, "questions": normalized}), end="")
    else:
        print(markdown_questions(normalized), end="")
    return OK


def command_interview(args: argparse.Namespace) -> int:
    """Run the terminal interview and save normalized answers."""
    bank, packs, _ = load_assets()
    output = Path(args.output)
    if output.exists() and not args.force:
        raise BlueprintError(f"refusing to overwrite {output}", IO_ERROR)
    answers: dict[str, Any] = {}
    if args.capability:
        known = {pack["id"] for pack in packs["packs"]}
        if unknown := sorted(set(args.capability).difference(known)):
            raise BlueprintError(f"unknown capabilities: {', '.join(unknown)}", INPUT_ERROR)
        set_path(answers, "capabilities", args.capability)

    skipped: set[str] = set()
    while True:
        capabilities = selected_capabilities(answers)
        pending = [
            question
            for question in active_questions(
                bank, capabilities, answers, include_unresolved_conditions=False
            )
            if not is_answered(get_path(answers, question["answer_path"]))
            and question["answer_path"] not in skipped
        ]
        if not pending:
            break
        changed = False
        for question in pending:
            value = prompt_for_question(question)
            if value is not MISSING:
                set_path(answers, question["answer_path"], value)
                changed = True
            else:
                skipped.add(question["answer_path"])
        if not changed:
            break
    errors, open_questions = validate_answers(answers, bank, packs)
    if errors:
        raise BlueprintError("interview answers are invalid", VALIDATION_ERROR, errors)
    atomic_write(output, dump_json(answers))
    print(
        dump_json(
            {
                "status": "saved",
                "output": str(output),
                "open_required_questions": len(open_questions),
            }
        ),
        end="",
    )
    return OK


def command_render(args: argparse.Namespace) -> int:
    """Validate answers and render the full blueprint packet."""
    bank, packs, catalog = load_assets()
    answers = load_json(Path(args.answers))
    errors, open_questions = validate_answers(answers, bank, packs)
    if errors:
        raise BlueprintError("answers failed validation", VALIDATION_ERROR, errors)
    blueprint = build_blueprint(answers, packs, catalog, open_questions)
    blueprint_errors = validate_blueprint(blueprint, packs)
    if blueprint_errors:
        raise BlueprintError(
            "generated blueprint failed validation",
            VALIDATION_ERROR,
            blueprint_errors,
        )
    packet = build_packet(blueprint, catalog)
    output_dir = Path(args.output)
    result = {
        "status": "dry-run" if args.dry_run else "rendered",
        "output": str(output_dir),
        "files": [str(output_dir / name) for name in PACKET_FILES],
        "open_decisions": len(blueprint["open_decisions"]),
        "evidence_status": "pending",
    }
    if not args.dry_run:
        write_packet(packet, output_dir, args.force)
    print(dump_json(result), end="")
    return OK


def command_validate(args: argparse.Namespace) -> int:
    """Validate an answers file or rendered blueprint."""
    bank, packs, _ = load_assets()
    data = load_json(Path(args.path))
    blueprint_markers = {"project", "provenance", "evidence", "scaffold_plan"}
    if "schema_version" in data and blueprint_markers.intersection(data):
        errors = validate_blueprint(data, packs)
        open_questions: list[dict[str, Any]] = data.get("open_decisions", [])
        kind = "blueprint"
    else:
        errors, open_questions = validate_answers(data, bank, packs)
        kind = "answers"
    if errors:
        raise BlueprintError(f"{kind} failed validation", VALIDATION_ERROR, errors)
    print(
        dump_json(
            {
                "status": "valid",
                "kind": kind,
                "open_required_questions": len(open_questions),
            }
        ),
        end="",
    )
    return OK


def build_parser() -> argparse.ArgumentParser:
    """Create the command-line parser."""
    parser = argparse.ArgumentParser(
        prog="blueprint.py",
        description="Interview, validate, and render cross-agent FDE blueprint packets.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    catalog_parser = subparsers.add_parser("catalog", help="list researched products")
    catalog_parser.add_argument("--category", help="filter by one exact category")
    catalog_parser.add_argument("--format", choices=("table", "json"), default="table")
    catalog_parser.set_defaults(handler=command_catalog)

    questions_parser = subparsers.add_parser(
        "questions", help="list routed interview questions"
    )
    questions_parser.add_argument("--capability", action="append", help="capability pack ID")
    questions_parser.add_argument("--answers", help="route using an existing answers JSON file")
    questions_parser.add_argument(
        "--format", choices=("markdown", "json"), default="markdown"
    )
    questions_parser.set_defaults(handler=command_questions)

    interview_parser = subparsers.add_parser(
        "interview", help="run the adaptive terminal interview"
    )
    interview_parser.add_argument("--output", required=True, help="answers JSON destination")
    interview_parser.add_argument(
        "--capability", action="append", help="preselect a capability"
    )
    interview_parser.add_argument(
        "--force", action="store_true", help="replace the answer file"
    )
    interview_parser.set_defaults(handler=command_interview)

    render_parser = subparsers.add_parser(
        "render", help="render an implementation packet"
    )
    render_parser.add_argument("--answers", required=True, help="answers JSON file")
    render_parser.add_argument("--output", required=True, help="packet directory")
    render_parser.add_argument(
        "--dry-run", action="store_true", help="report without writing"
    )
    render_parser.add_argument(
        "--force", action="store_true", help="replace generated files"
    )
    render_parser.set_defaults(handler=command_render)

    validate_parser = subparsers.add_parser(
        "validate", help="validate answers or a blueprint"
    )
    validate_parser.add_argument("path", help="JSON file to validate")
    validate_parser.set_defaults(handler=command_validate)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command line interface and emit structured expected errors."""
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.handler(args))
    except BlueprintError as exc:
        print(
            dump_json(
                {
                    "status": "error",
                    "code": exc.code,
                    "message": str(exc),
                    "details": exc.details,
                }
            ),
            end="",
            file=sys.stderr,
        )
        return exc.code
    except OSError as exc:
        print(
            dump_json(
                {
                    "status": "error",
                    "code": IO_ERROR,
                    "message": str(exc),
                    "details": [],
                }
            ),
            end="",
            file=sys.stderr,
        )
        return IO_ERROR


if __name__ == "__main__":
    raise SystemExit(main())
