from __future__ import annotations

import ast
import json
import subprocess
import sys
from copy import deepcopy
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "fde-blueprint"
SCRIPT = SKILL / "scripts" / "blueprint.py"
ASSETS = SKILL / "assets"
EXPECTED_PACKS = {
    "multi-tenant-saas",
    "enterprise-sso",
    "connector-pack",
    "secure-rag",
    "customer-health",
    "webhook-engine",
    "one-click-deployment",
    "pii-redaction",
    "incident-response",
    "usage-metering",
    "onboarding-automation",
    "deployment-case-study",
}
EXPECTED_PACKET = {
    "blueprint.json",
    "BLUEPRINT.md",
    "ARCHITECTURE.md",
    "SECURITY.md",
    "IMPLEMENTATION_PLAN.md",
    "ACCEPTANCE.md",
    "SOURCES.md",
    "SCAFFOLD_PLAN.json",
    "EVIDENCE_MANIFEST.json",
}
REFERENCE_FILES = {
    "discovery-interview.md",
    "blueprint-contract.md",
    "capability-packs.md",
    "stack-profiles.md",
    "identity-tenancy.md",
    "connectors-eventing.md",
    "rag-data-privacy.md",
    "operations-deployment.md",
    "customer-success-billing.md",
    "security-verification.md",
    "product-catalog.md",
    "source-provenance.md",
}


def load_asset(name: str) -> dict:
    """Load one of the skill's versioned JSON assets."""
    return json.loads((ASSETS / name).read_text(encoding="utf-8"))


def run_cli(*args: str, input_text: str | None = None) -> subprocess.CompletedProcess[str]:
    """Run the standalone helper with the current test interpreter."""
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        input=input_text,
        capture_output=True,
        text=True,
        check=False,
        cwd=ROOT,
    )


def sample_answers() -> dict:
    """Return a renderable multi-pack answer set with deliberate open decisions."""
    return {
        "engagement": {
            "project_name": "Northstar field integration",
            "mode": "existing",
            "business_outcome": (
                "Customer admins connect identity and support data with auditable delivery"
            ),
            "repository_path": "./services/northstar",
            "non_goals": ["production deployment in this work package"],
        },
        "capabilities": [
            "enterprise-sso",
            "connector-pack",
            "webhook-engine",
            "secure-rag",
            "usage-metering",
            "one-click-deployment",
        ],
        "application": {
            "primary_language": "python",
            "framework": "FastAPI",
            "package_manager": "uv",
            "architecture_style": "service",
        },
        "identity": {
            "protocols": ["oidc", "scim-2.0"],
            "delivery_model": "managed-broker",
            "candidate_products": ["workos"],
        },
        "connectors": {
            "providers": ["slack", "github-apps"],
            "candidate_platforms": ["nango", "paragon"],
        },
        "rag": {"vector_store": ["pgvector"]},
        "metering": {"candidate_products": ["openmeter", "metronome"]},
        "provenance": {
            "reuse_policy": "permissive-oss",
            "dependency_approval": "Product security and legal owner",
        },
    }


def write_answers(path: Path, answers: dict | None = None) -> None:
    """Write a canonical answer fixture."""
    path.write_text(
        json.dumps(answers or sample_answers(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def frontmatter(path: Path) -> dict[str, str]:
    """Parse the simple name and description frontmatter used by the skill."""
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\n")
    raw = text.split("---\n", 2)[1]
    return dict(line.split(": ", 1) for line in raw.splitlines() if line)


def test_capability_pack_contract_is_complete() -> None:
    packs = load_asset("capability-packs.json")["packs"]
    assert {pack["id"] for pack in packs} == EXPECTED_PACKS
    for pack in packs:
        assert pack["outcome"]
        assert pack["scaffold_modules"]
        assert pack["invariants"]
        assert pack["acceptance"]
        assert pack["evidence"]


def test_question_bank_is_unique_and_covers_every_pack() -> None:
    questions = load_asset("questionnaire.json")["questions"]
    ids = [question["id"] for question in questions]
    assert len(questions) >= 100
    assert len(ids) == len(set(ids))
    assert all(question["answer_path"] for question in questions)
    assert {question["type"] for question in questions} == {
        "text",
        "choice",
        "multi_text",
        "multi_choice",
    }
    for pack_id in EXPECTED_PACKS:
        assert any(pack_id in question["applies_to"] for question in questions)


def test_catalog_has_researched_provenance_and_explicit_reuse_boundaries() -> None:
    catalog = load_asset("catalog.json")
    products = catalog["products"]
    product_ids = [product["id"] for product in products]
    assert len(products) >= 90
    assert len(product_ids) == len(set(product_ids))
    assert set(catalog["license_classes"]) == {
        "standard",
        "permissive",
        "copyleft",
        "source-available",
        "commercial",
        "mixed",
    }
    for product in products:
        assert product["license_class"] in catalog["license_classes"]
        assert product["reuse"] in catalog["reuse_modes"]
        assert product["sources"]
        for source in product["sources"]:
            assert source["url"].startswith("https://")
            assert source["checked"] == catalog["researched_on"]
            assert source["status"] in {"cataloged", "reviewed"}


def test_declared_product_choices_have_catalog_entries() -> None:
    questions = {
        question["id"]: question for question in load_asset("questionnaire.json")["questions"]
    }
    product_ids = {product["id"] for product in load_asset("catalog.json")["products"]}
    routed_choices = set()
    for question_id in (
        "identity-products",
        "connector-providers",
        "connector-platforms",
        "rag-store",
        "billing-products",
    ):
        routed_choices.update(questions[question_id]["choices"])
    local_or_open = {"other", "none", "custom-ledger"}
    assert routed_choices.difference(local_or_open) <= product_ids


def test_skill_discovery_shims_share_the_canonical_contract() -> None:
    canonical = SKILL / "SKILL.md"
    codex = ROOT / ".agents" / "skills" / "fde-blueprint" / "SKILL.md"
    claude = ROOT / ".claude" / "skills" / "fde-blueprint" / "SKILL.md"
    metadata = frontmatter(canonical)
    assert set(metadata) == {"name", "description"}
    assert metadata["name"] == "fde-blueprint"
    for shim in (codex, claude):
        assert frontmatter(shim) == metadata
        text = shim.read_text(encoding="utf-8")
        assert "../../../skills/fde-blueprint/SKILL.md" in text
    openai_config = (SKILL / "agents" / "openai.yaml").read_text(encoding="utf-8")
    assert "allow_implicit_invocation: true" in openai_config


def test_reference_library_is_complete_and_has_no_scaffold_placeholders() -> None:
    reference_dir = SKILL / "references"
    assert {path.name for path in reference_dir.glob("*.md")} == REFERENCE_FILES
    assert len((SKILL / "SKILL.md").read_text(encoding="utf-8").splitlines()) < 500
    for path in [SKILL / "SKILL.md", *reference_dir.glob("*.md")]:
        text = path.read_text(encoding="utf-8")
        assert "[TODO" not in text
        assert "TODO:" not in text


def test_catalog_command_emits_machine_readable_filtered_results() -> None:
    result = run_cli("catalog", "--category", "enterprise-sso", "--format", "json")
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["catalog_version"] == "1.0"
    assert {product["id"] for product in payload["products"]} >= {
        "workos",
        "keycloak",
        "microsoft-entra",
    }
    assert all("enterprise-sso" in product["categories"] for product in payload["products"])


def test_catalog_table_handles_a_category_with_no_matches() -> None:
    result = run_cli("catalog", "--category", "does-not-exist")
    assert result.returncode == 0
    assert result.stdout == "No catalog entries matched.\n"


def test_questions_default_to_all_packs_and_narrow_when_selected() -> None:
    all_result = run_cli("questions", "--format", "json")
    assert all_result.returncode == 0, all_result.stderr
    all_payload = json.loads(all_result.stdout)
    assert set(all_payload["capabilities"]) == EXPECTED_PACKS
    assert len(all_payload["questions"]) == len(load_asset("questionnaire.json")["questions"])

    sso_result = run_cli(
        "questions", "--capability", "enterprise-sso", "--format", "json"
    )
    assert sso_result.returncode == 0, sso_result.stderr
    question_ids = {question["id"] for question in json.loads(sso_result.stdout)["questions"]}
    assert "sso-protocols" in question_ids
    assert "connector-providers" not in question_ids


def test_questions_apply_conditions_from_existing_answers(tmp_path: Path) -> None:
    existing_path = tmp_path / "existing.json"
    write_answers(existing_path)
    existing_result = run_cli(
        "questions", "--answers", str(existing_path), "--format", "json"
    )
    assert existing_result.returncode == 0, existing_result.stderr
    existing_ids = {
        question["id"] for question in json.loads(existing_result.stdout)["questions"]
    }
    assert "repository-path" in existing_ids
    assert "scim-scope" in existing_ids
    assert "other-language" not in existing_ids

    greenfield = deepcopy(sample_answers())
    greenfield["engagement"]["mode"] = "greenfield"
    greenfield["engagement"].pop("repository_path")
    greenfield_path = tmp_path / "greenfield.json"
    write_answers(greenfield_path, greenfield)
    greenfield_result = run_cli(
        "questions", "--answers", str(greenfield_path), "--format", "json"
    )
    assert greenfield_result.returncode == 0, greenfield_result.stderr
    greenfield_ids = {
        question["id"] for question in json.loads(greenfield_result.stdout)["questions"]
    }
    assert "repository-path" not in greenfield_ids


def test_validation_failure_uses_stable_exit_code_and_json_error(tmp_path: Path) -> None:
    answers_path = tmp_path / "bad.json"
    answers_path.write_text("{}\n", encoding="utf-8")
    result = run_cli("validate", str(answers_path))
    assert result.returncode == 3
    error = json.loads(result.stderr)
    assert error["status"] == "error"
    assert error["code"] == 3
    assert any(detail.startswith("missing project name") for detail in error["details"])


def test_validation_rejects_malformed_choice_values_without_traceback(
    tmp_path: Path,
) -> None:
    answers = sample_answers()
    answers["capabilities"] = [{"unexpected": "object"}]
    answers_path = tmp_path / "malformed.json"
    write_answers(answers_path, answers)
    result = run_cli("validate", str(answers_path))
    assert result.returncode == 3
    error = json.loads(result.stderr)
    assert error["status"] == "error"
    assert any("expected a list of strings" in detail for detail in error["details"])


def test_validation_rejects_malformed_blueprint_without_traceback(tmp_path: Path) -> None:
    malformed = {
        "schema_version": "1.0",
        "project": {},
        "capabilities": [{"not": "a string"}],
        "evidence": [42],
        "scaffold_plan": [],
    }
    blueprint_path = tmp_path / "blueprint.json"
    blueprint_path.write_text(json.dumps(malformed), encoding="utf-8")
    result = run_cli("validate", str(blueprint_path))
    assert result.returncode == 3
    error = json.loads(result.stderr)
    assert error["status"] == "error"
    assert "blueprint capabilities must contain only strings" in error["details"]
    assert any("evidence items must be objects" in detail for detail in error["details"])


def test_render_dry_run_has_no_file_system_side_effect(tmp_path: Path) -> None:
    answers_path = tmp_path / "answers.json"
    output_path = tmp_path / "packet"
    write_answers(answers_path)
    result = run_cli(
        "render",
        "--answers",
        str(answers_path),
        "--output",
        str(output_path),
        "--dry-run",
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "dry-run"
    assert payload["evidence_status"] == "pending"
    assert {Path(path).name for path in payload["files"]} == EXPECTED_PACKET
    assert not output_path.exists()


def test_render_writes_complete_honest_packet(tmp_path: Path) -> None:
    answers_path = tmp_path / "answers.json"
    output_path = tmp_path / "packet"
    write_answers(answers_path)
    result = run_cli(
        "render", "--answers", str(answers_path), "--output", str(output_path)
    )
    assert result.returncode == 0, result.stderr
    assert {path.name for path in output_path.iterdir()} == EXPECTED_PACKET

    blueprint = json.loads((output_path / "blueprint.json").read_text(encoding="utf-8"))
    selected = {product["id"] for product in blueprint["selected_products"]}
    assert selected >= {
        "workos",
        "nango",
        "paragon",
        "slack",
        "github-apps",
        "pgvector",
        "openmeter",
        "metronome",
    }
    assert blueprint["open_decisions"]
    assert blueprint["provenance"]["source_reuse_policy"].startswith(
        "Owner selection: permissive-oss."
    )
    assert blueprint["evidence"]
    assert {item["status"] for item in blueprint["evidence"]} == {"pending"}
    assert all(item["proof_command"] is None for item in blueprint["evidence"])
    assert all(item["artifact_path"] is None for item in blueprint["evidence"])
    for path in output_path.iterdir():
        assert "{{" not in path.read_text(encoding="utf-8")
    assert "does not claim" in (output_path / "BLUEPRINT.md").read_text(encoding="utf-8")

    validation = run_cli("validate", str(output_path / "blueprint.json"))
    assert validation.returncode == 0, validation.stderr
    assert json.loads(validation.stdout)["kind"] == "blueprint"


def test_other_language_remains_an_open_decision_without_breaking_render(
    tmp_path: Path,
) -> None:
    answers = sample_answers()
    answers["application"]["primary_language"] = "other"
    answers_path = tmp_path / "answers.json"
    output_path = tmp_path / "packet"
    write_answers(answers_path, answers)
    result = run_cli(
        "render", "--answers", str(answers_path), "--output", str(output_path)
    )
    assert result.returncode == 0, result.stderr
    blueprint = json.loads((output_path / "blueprint.json").read_text(encoding="utf-8"))
    assert blueprint["project"]["primary_language"] == "other"
    assert any(
        decision["question_id"] == "other-language"
        for decision in blueprint["open_decisions"]
    )


def test_render_is_byte_deterministic_and_refuses_overwrite(tmp_path: Path) -> None:
    answers_path = tmp_path / "answers.json"
    first = tmp_path / "first"
    second = tmp_path / "second"
    write_answers(answers_path)
    for output in (first, second):
        result = run_cli(
            "render", "--answers", str(answers_path), "--output", str(output)
        )
        assert result.returncode == 0, result.stderr
    for filename in EXPECTED_PACKET:
        assert (first / filename).read_bytes() == (second / filename).read_bytes()

    overwrite = run_cli(
        "render", "--answers", str(answers_path), "--output", str(first)
    )
    assert overwrite.returncode == 4
    error = json.loads(overwrite.stderr)
    assert error["code"] == 4
    assert len(error["details"]) == len(EXPECTED_PACKET)


def test_interview_refuses_to_replace_answers_without_force(tmp_path: Path) -> None:
    answers_path = tmp_path / "answers.json"
    write_answers(answers_path)
    result = run_cli("interview", "--output", str(answers_path))
    assert result.returncode == 4
    assert "refusing to overwrite" in json.loads(result.stderr)["message"]


def test_helper_has_no_runtime_network_client() -> None:
    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
    imported_roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_roots.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_roots.add(node.module.split(".", 1)[0])
    assert imported_roots.isdisjoint(
        {"requests", "httpx", "urllib", "socket", "aiohttp", "http", "ftplib"}
    )
