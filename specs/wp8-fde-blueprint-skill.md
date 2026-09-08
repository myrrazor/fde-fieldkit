# WP8 — FDE blueprint skill foundation

## Outcome

Ship the first cross-agent foundation for `fieldkit blueprint`: an Agent Skills-compatible
workflow plus a deterministic, dependency-free Python helper that interviews an engineer,
validates the answers, and renders an implementation blueprint packet. This work package
does not generate production application code yet. It produces the versioned contract,
scaffold plan, security gates, acceptance plan, evidence manifest, and source-provenance
record that later language-specific code generators must consume.

The skill must be discoverable from both Codex and Claude Code without maintaining two
independent copies of its substantive instructions.

## Acceptance criteria

- The canonical skill follows the Agent Skills directory contract and passes the bundled
  `skill-creator` validator.
- Codex and Claude Code project discovery shims point agents to the same canonical skill.
- The interview covers all twelve FDE capability packs and branches on engagement mode,
  selected capabilities, application stack, tenancy, providers, data sensitivity,
  reliability needs, deployment environment, and delivery evidence.
- The catalog distinguishes managed products, permissive open source, copyleft open source,
  source-available products, standards, and local implementation patterns. Every external
  entry has a primary-source URL and a research date.
- The helper has machine-readable output, non-interactive operation, dry-run support,
  explicit exit codes, refusal to overwrite by default, and no runtime network access.
- Rendered packets never claim that code, security controls, tests, or deployments exist.
  Evidence starts in a pending state and must be earned by later implementation.
- Tests cover discovery shims, catalog integrity, question routing, validation failures,
  dry runs, packet rendering, overwrite refusal, and deterministic output.
- The full Fieldkit test suite and Ruff pass, with the combined output captured in
  `TEST_STDOUT.log`.

## Files in scope

- `specs/wp8-fde-blueprint-skill.md`
- `README.md`
- `TEST_STDOUT.log`
- `.agents/skills/fde-blueprint/SKILL.md`
- `.claude/skills/fde-blueprint/SKILL.md`
- `skills/fde-blueprint/SKILL.md`
- `skills/fde-blueprint/agents/openai.yaml`
- `skills/fde-blueprint/assets/catalog.json`
- `skills/fde-blueprint/assets/capability-packs.json`
- `skills/fde-blueprint/assets/questionnaire.json`
- `skills/fde-blueprint/assets/blueprint.schema.json`
- `skills/fde-blueprint/assets/templates/BLUEPRINT.md.tmpl`
- `skills/fde-blueprint/assets/templates/ARCHITECTURE.md.tmpl`
- `skills/fde-blueprint/assets/templates/SECURITY.md.tmpl`
- `skills/fde-blueprint/assets/templates/IMPLEMENTATION_PLAN.md.tmpl`
- `skills/fde-blueprint/assets/templates/ACCEPTANCE.md.tmpl`
- `skills/fde-blueprint/assets/templates/SOURCES.md.tmpl`
- `skills/fde-blueprint/references/discovery-interview.md`
- `skills/fde-blueprint/references/blueprint-contract.md`
- `skills/fde-blueprint/references/capability-packs.md`
- `skills/fde-blueprint/references/stack-profiles.md`
- `skills/fde-blueprint/references/identity-tenancy.md`
- `skills/fde-blueprint/references/connectors-eventing.md`
- `skills/fde-blueprint/references/rag-data-privacy.md`
- `skills/fde-blueprint/references/operations-deployment.md`
- `skills/fde-blueprint/references/customer-success-billing.md`
- `skills/fde-blueprint/references/security-verification.md`
- `skills/fde-blueprint/references/product-catalog.md`
- `skills/fde-blueprint/references/source-provenance.md`
- `skills/fde-blueprint/scripts/blueprint.py`
- `tests/test_blueprint_skill.py`

## Boundaries

- Do not modify `src/fieldkit/core/` or add a root CLI command in this work package.
- Do not copy code from local portfolio repositories or external repositories.
- Do not add dependencies. The helper uses the Python standard library only.
- Do not contact external services at runtime. Research URLs are documentation and
  provenance records, not live dependencies.
- Do not create credentials, vendor accounts, infrastructure, deployments, or pull requests.
- Do not mark any generated evidence item as passed without a later command and artifact that
  proves it.

## Verification

```text
python3 <skill-creator>/scripts/quick_validate.py skills/fde-blueprint
python3 skills/fde-blueprint/scripts/blueprint.py catalog --format json
python3 skills/fde-blueprint/scripts/blueprint.py questions --format json
uv run pytest -q
uv run ruff check .
```
