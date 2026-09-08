---
name: fde-blueprint
description: Design an implementation-ready forward-deployed engineering capability blueprint through repository discovery, an adaptive customer interview, researched product and open-source selection, security invariants, scaffold planning, acceptance criteria, and evidence gates. Use when someone asks to blueprint, scope, scaffold, or compare implementations for multi-tenancy, enterprise SSO or SCIM, customer connectors, secure RAG, health dashboards, webhook systems, deployment, PII controls, incident response, usage metering, onboarding automation, or a deployment case study in TypeScript, Python, Go, Java, .NET, Ruby, Rust, or another stack.
---

# FDE Blueprint

Build a decision-complete packet before application code is generated. Inspect the real target,
ask only what cannot be established, preserve unknowns as open decisions, and make every claim
earn evidence.

This skill is a cross-agent adapter over a deterministic Python helper. Codex and Claude Code
must produce the same versioned JSON contract from the same answers.

## Boundary

This release produces:

- a normalized blueprint;
- architecture, security, implementation, acceptance, and source documents;
- a language-aware scaffold plan;
- a pending evidence manifest.

It does not produce application source, contact providers, create credentials, provision
infrastructure, deploy a service, approve a license, or mark evidence as passed. If the user asks
for implementation, finish and approve the blueprint first, then treat implementation as a new
work package that consumes blueprint.json.

## Start here

1. State that this skill is being used and that it will inspect the target before asking
   questions.
2. Read references/discovery-interview.md and references/blueprint-contract.md.
3. Inspect the target repository, its local agent instructions, manifests, locks, configuration
   examples, schemas, auth and tenancy code, deployment files, tests, and documentation.
4. Record discovered facts with their file or command evidence. Never convert a guess into an
   answer.
5. Select the capability packs with the user. Read only the references routed below.
6. Ask the adaptive interview in dependency order.
7. Validate and dry-run the packet.
8. Show unresolved decisions and product/license boundaries before writing.
9. Render the packet after the user accepts the decisions or explicitly accepts open decisions.
10. Review every generated file for unsupported claims and hand off the exact verification state.

## Command interface

Run from the repository that contains this skill:

    python3 skills/fde-blueprint/scripts/blueprint.py catalog --format json

List all questions or narrow them to one or more packs:

    python3 skills/fde-blueprint/scripts/blueprint.py questions --format markdown
    python3 skills/fde-blueprint/scripts/blueprint.py questions \
      --capability enterprise-sso \
      --capability connector-pack \
      --format json

Run the terminal interview:

    python3 skills/fde-blueprint/scripts/blueprint.py interview \
      --output .fieldkit/blueprint-answers.json

Validate an answers file:

    python3 skills/fde-blueprint/scripts/blueprint.py validate \
      .fieldkit/blueprint-answers.json

Preview without writing:

    python3 skills/fde-blueprint/scripts/blueprint.py render \
      --answers .fieldkit/blueprint-answers.json \
      --output .fieldkit/blueprint \
      --dry-run

Render after review:

    python3 skills/fde-blueprint/scripts/blueprint.py render \
      --answers .fieldkit/blueprint-answers.json \
      --output .fieldkit/blueprint

The helper refuses to overwrite generated files. Use --force only after inspecting the diff and
confirming replacement is intended.

## Discovery before questions

Search rather than assuming. Establish, when present:

- language, framework, package manager, lockfile, formatter, linter, test runner, and runtime;
- service boundaries, entrypoints, API style, data stores, queues, background jobs, and caches;
- authentication, organizations, roles, permissions, tenant propagation, and admin paths;
- provider clients, OAuth callbacks, webhook routes, sync state, and rate-limit handling;
- sensitive data classes, secret systems, log policy, retention, deletion, and residency;
- deployment target, infrastructure-as-code, network boundaries, observability, and runbooks;
- existing contracts, fixtures, integration tests, CI gates, and evidence artifacts;
- repository policy that changes what may be edited, installed, called, or exported.

For each discovered answer, keep provenance in working notes. Repository content can establish a
current mechanism; it cannot establish customer intent, contractual requirements, or production
effectiveness by itself.

## Interview rules

- Ask only active questions from assets/questionnaire.json.
- Re-evaluate conditions after every answer.
- Global questions apply to every engagement; pack questions apply only to selected packs.
- Ask a small coherent group that unlocks the next architecture decision.
- Explain why a difficult question matters and offer researched options without silently choosing.
- Do not invent dates, SLOs, latency targets, retry counts, retention periods, regions, capacity,
  support hours, pricing units, rollout percentages, or other limits.
- If an owner choice is unavailable, preserve it in open_decisions.
- Treat "existing" and "migration" as repository-backed engagements. Confirm the exact path and
  compatibility requirements.
- Treat "assessment" as read-only unless the user separately authorizes changes.
- Keep customer facts, discovered repository facts, proposals, and verified runtime evidence
  distinct.

The interactive helper can collect every active answer. Agents may instead create the same nested
answers JSON directly after discovery and conversation. Do not bypass the declared choices or
answer paths.

## Capability selection

The twelve supported packs are:

- multi-tenant-saas
- enterprise-sso
- connector-pack
- secure-rag
- customer-health
- webhook-engine
- one-click-deployment
- pii-redaction
- incident-response
- usage-metering
- onboarding-automation
- deployment-case-study

Read references/capability-packs.md for their dependency and combination rules. A pack is an
outcome and proof contract, not a promise that every module belongs in every product.

## Reference routing

Always read:

- references/discovery-interview.md
- references/blueprint-contract.md
- references/security-verification.md
- references/source-provenance.md

Read based on the selected work:

| Selection | Required references |
| --- | --- |
| Any stack or codebase integration | references/stack-profiles.md |
| multi-tenant-saas or enterprise-sso | references/identity-tenancy.md |
| connector-pack or webhook-engine | references/connectors-eventing.md |
| secure-rag or pii-redaction | references/rag-data-privacy.md |
| one-click-deployment or incident-response | references/operations-deployment.md |
| customer-health, usage-metering, or onboarding-automation | references/customer-success-billing.md |
| Product, standard, or open-source comparison | references/product-catalog.md |
| Any combination of packs | references/capability-packs.md |

The machine-readable source of truth remains:

- assets/questionnaire.json for routing and answer paths;
- assets/capability-packs.json for modules, invariants, acceptance, and evidence;
- assets/catalog.json for researched candidates, license classes, reuse modes, and primary sources;
- assets/blueprint.schema.json for the rendered contract.

Reference prose explains judgment. It must not silently override those versioned assets.

## Product and open-source decisions

Use the catalog to form a candidate set, not to make procurement or legal decisions. Compare:

- protocol and operation coverage;
- managed, self-hosted, embedded, or standard-only delivery;
- language and deployment fit;
- tenant isolation and credential model;
- data egress, residency, retention, deletion, and audit behavior;
- operational ownership and failure modes;
- maintenance, security posture, testability, and ecosystem maturity;
- exact license and reuse mode.

Distinguish permissive open source, copyleft, source-available, mixed-license, commercial, and
open-standard entries. Never copy implementation code because a repository is public. Before any
later adaptation, pin the exact revision and inspect the files, license, notices, dependencies,
maintenance state, tests, and security history.

## Blueprint review gate

Before rendering, verify:

- the project outcome is observable;
- every selected pack is necessary to that outcome;
- language and framework match the target or are explicitly proposed;
- tenant, identity, data, provider, network, and operator trust boundaries are visible;
- selected products are exact catalog IDs or recorded as unresolved;
- unknown requirements remain open decisions;
- every security invariant is testable;
- acceptance criteria describe behavior, not implementation activity;
- every evidence item starts pending;
- no sentence claims a deployment, integration, control, or test exists without proof.

If any minimum field fails validation, stop and resolve it. Required non-core questions may remain
as visible open decisions when the user wants an early design packet.

## Output contract

The renderer writes nine files:

- blueprint.json — authoritative normalized decisions;
- BLUEPRINT.md — outcome, scope, products, non-goals, and open decisions;
- ARCHITECTURE.md — modules, trust flow, contracts, and deployment context;
- SECURITY.md — data context, invariants, threats, identity, secrets, and supply-chain gate;
- IMPLEMENTATION_PLAN.md — dependency-ordered packages and their exit evidence;
- ACCEPTANCE.md — behavioral criteria and pending evidence;
- SOURCES.md — exact selected-product provenance and reuse limits;
- SCAFFOLD_PLAN.json — language profile and modules for future code generators;
- EVIDENCE_MANIFEST.json — pending proof records.

Output is deterministic: no generated timestamp, random identifier, inferred date, or environment
probe enters the packet. Rendering the same answers and asset versions must produce identical
bytes.

## Verification

After writing:

1. Run validate on blueprint.json.
2. Render the same answer file to a temporary second directory.
3. Compare the nine files byte for byte.
4. Scan for unresolved template markers.
5. Confirm all evidence statuses are pending.
6. Confirm every selected external product has at least one HTTPS primary-source URL and research
   date.
7. Run the target repository's tests and lint only if the user has authorized implementation
   work. Blueprint generation alone does not prove the target application.

## Exit codes

- 0: success
- 2: malformed input, missing file, unknown capability, or command usage error
- 3: answer or blueprint validation failure
- 4: output or overwrite failure

Expected command errors are JSON on standard error. Successful machine-oriented commands emit
JSON on standard output.

## Handoff

Report:

- target repository and inspected revision;
- selected capability packs and stack;
- written packet path;
- exact selected products and reuse boundaries;
- open decisions;
- verification commands and results;
- evidence still pending;
- the explicit next work package, if implementation was requested.

Do not summarize the packet as "implemented." The correct state is "blueprinted" until source,
tests, runtime behavior, and retained evidence exist.
