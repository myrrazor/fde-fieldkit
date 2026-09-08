# Discovery and adaptive interview

## Contents

1. Purpose
2. Evidence hierarchy
3. Repository discovery
4. Engagement modes
5. Interview sequence
6. Question techniques
7. Resolving contradictions
8. Recording unknowns
9. Completion gate

## Purpose

The interview converts an ambiguous field request into decisions that a later engineer or
generator can implement and prove. It is not a form-filling ritual. Start with the real repository
and customer context so the user is not asked to repeat facts already available.

The question bank is deliberately broad. Routing is what makes it usable:

- global questions establish outcome, stack, data, security, reliability, and delivery;
- capability questions appear only for selected packs;
- conditional questions appear only after their parent answer makes them relevant;
- repository evidence may answer technical-state questions;
- only the owner can answer intent, risk, contract, scope, and acceptance questions.

## Evidence hierarchy

Prefer evidence in this order:

1. Current runtime behavior observed in the target environment.
2. Current source and configuration at the exact inspected revision.
3. Passing tests and retained artifacts for that revision.
4. Current customer or owner statement.
5. Current authoritative vendor or standards documentation.
6. Project documentation that agrees with current source.
7. Historical notes, screenshots, logs, or prior blueprints.
8. Inference.

An inference can guide the next question. It cannot become a confirmed answer. Historical proof
does not prove a changed working tree, and mocked behavior does not prove a live integration.

Record discovered facts in a temporary ledger:

| Answer path | Value | Source | Confidence | Needs owner confirmation |
| --- | --- | --- | --- | --- |
| application.primary_language | python | pyproject.toml | confirmed current source | no |
| deployment.platform | AWS | infrastructure directory | likely | yes |
| security.retention | unknown | no policy found | unknown | yes |

Do not put this temporary confidence metadata into answer values. Preserve unresolved facts as
open decisions.

## Repository discovery

### Policy and boundaries

Inspect first:

- root and nested agent instruction files;
- git root, branch, current revision, worktree status, and nested checkouts;
- read-only, no-network, no-egress, dependency, branch, and test requirements;
- directories and files the task permits changing;
- customer-data handling restrictions.

Policy can narrow the workflow. It cannot expand user authorization.

### Stack

Look for:

- language manifests and lockfiles;
- framework entrypoints and route registration;
- formatter, linter, type checker, unit, integration, contract, and end-to-end test commands;
- container base image and runtime version;
- monorepo package boundaries;
- generated-code conventions;
- public API or plugin contracts.

Record the authoritative package workflow. Do not recommend a second package manager just because
the catalog lists one.

### Architecture

Trace:

- inbound request and authentication path;
- tenant or organization context creation and propagation;
- service and repository layers;
- primary database, object storage, vector stores, cache, queue, and search;
- background job and event boundaries;
- outbound provider clients;
- deployment unit and network boundary;
- operator, support, and break-glass paths.

Use a small flow diagram when three or more trust boundaries interact.

### Existing capabilities

Search for actual mechanisms, not feature names:

- SAML, OIDC, OAuth callbacks, SCIM routes, membership sync;
- tenant_id, organization_id, row policies, scoped repositories, admin bypasses;
- provider token storage, refresh, pagination, checkpoints, reconciliation;
- webhook signature verification, raw body access, dedupe, replay, dead letters;
- document ingestion, ACL metadata, vector filters, citations, deletion;
- redaction, DLP, secret detection, structured logging;
- metrics, traces, alerts, incident records, support tooling;
- usage events, ledgers, billing exports, corrections;
- onboarding state, workflow execution, approvals, retries.

Presence is not effectiveness. A route named scim is not SCIM conformance, and a tenant column is
not tenant isolation.

### Delivery and proof

Find:

- deployment manifests and infrastructure state;
- CI jobs and branch gates;
- test fixtures and recorded provider contracts;
- runbooks, dashboards, alerts, and incident templates;
- release evidence, SBOMs, provenance, signatures, and retained logs;
- known environment limitations that can invalidate local proof.

## Engagement modes

### Greenfield

The stack and architecture may be proposed, but do not silently choose them. Ask about the team's
operating ability, target environment, data restrictions, and deployment ownership before
selecting a managed or self-hosted component.

### Existing product

The current repository is authoritative for integration conventions. Ask which compatibility
constraints are contractual; do not preserve obsolete interfaces by instinct. Name the receiving
module, existing extension point, and proof command.

### Migration

Capture both source and destination. Ask:

- what behavior and data must survive;
- whether identities and provider IDs must remain stable;
- cutover, coexistence, rollback, reconciliation, and audit expectations;
- how historical events or documents are reprocessed;
- which legacy behavior should intentionally end.

Migration does not imply unlimited backward compatibility.

### Assessment

Remain read-only. Produce current-state findings, proposed target state, gaps, decisions, and a
proof plan. Do not create credentials, call customer systems, modify repositories, or deploy.

## Interview sequence

Ask in dependency order:

1. Outcome and acceptance owner.
2. Engagement mode, target repository, and explicit non-goals.
3. Selected capability packs.
4. Application language, framework, architecture, package workflow, and data stores.
5. Actors, organizations, tenant boundary, identity source, and authorization model.
6. Data classes, residency, retention, deletion, and secret handling.
7. Provider and protocol decisions.
8. Event, retry, idempotency, ordering, and reconciliation semantics.
9. Deployment, network, observability, incident, and rollback model.
10. Acceptance environment, fixtures, live proof, artifacts, and handoff.

After each group:

- normalize answers at their declared answer paths;
- re-run question routing;
- summarize what changed;
- identify the next decision that is now unlocked;
- preserve disagreement explicitly.

## Question techniques

Ask for observable behavior:

- Weak: "Should it be secure?"
- Strong: "What must happen when an authenticated user supplies another tenant's object ID?"

Ask for source of truth:

- "Which system owns membership activation and deactivation?"
- "Which ledger owns billable usage after a correction?"

Ask for failure behavior:

- "What happens when the provider accepts a request but the local checkpoint write fails?"
- "What happens when a webhook arrives twice or out of order?"

Ask for authority:

- "Who can authorize cross-tenant support access?"
- "Who accepts a license with reciprocal obligations?"

Ask for evidence:

- "Which environment and identity-provider configuration count as live SSO proof?"
- "Which retained artifact demonstrates deletion across every declared store?"

Explain tradeoffs without selecting by default. A managed broker reduces protocol implementation
but introduces procurement, data-flow, and vendor dependency decisions. A self-hosted identity
system changes operational ownership. A standard defines interoperability but does not provide an
operated implementation.

## Resolving contradictions

When source, docs, and owner statements disagree:

1. State the exact conflict.
2. Identify which fact concerns current behavior and which concerns desired behavior.
3. Verify cheaply when possible.
4. Record current state and proposed state separately.
5. Ask the owner only for the decision they uniquely control.

Do not average conflicting answers. Do not silently let stale documentation override source.

## Recording unknowns

Unknown is a valid design state. Store it by omitting the value and allowing the renderer to create
an open_decisions entry.

Never use placeholders that look real, including:

- example customer names presented as selected customers;
- invented regions, domains, tenant IDs, provider scopes, or redirect URLs;
- assumed RTO, RPO, SLO, retry, retention, or rate limits;
- fabricated approval, test, audit, or production status.

If an unresolved decision blocks even a coherent architecture, do not render. The helper enforces
minimum fields; the agent must also recognize semantic blockers such as an undefined tenant
boundary for a multi-tenant design.

## Completion gate

The discovery phase is complete when:

- the target and engagement mode are unambiguous;
- selected packs map to the stated outcome;
- the actual or proposed stack is explicit;
- all material trust and data boundaries are named;
- selected providers are exact or visibly unresolved;
- source-of-truth and failure semantics are explicit;
- security invariants can become tests;
- acceptance owners, environments, commands, and artifacts are known or open;
- no assumption is disguised as a requirement.

Render only after showing the user the decision summary and remaining unknowns.
