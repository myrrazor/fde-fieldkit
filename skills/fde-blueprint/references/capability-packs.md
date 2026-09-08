# Capability packs

## Contents

1. How packs work
2. Dependency map
3. Multi-tenant SaaS
4. Enterprise SSO
5. Connector pack
6. Secure RAG
7. Customer health
8. Webhook engine
9. One-click deployment
10. PII redaction
11. Incident response
12. Usage metering
13. Onboarding automation
14. Deployment case study
15. Combination rules

## How packs work

A pack is an outcome, module map, security contract, acceptance set, and evidence request. It is
not a fixed repository template. assets/capability-packs.json is authoritative for generated
content; this reference explains implementation judgment and combinations.

Select a pack only when removing it would leave the stated outcome unmet or unproven. Shared
mechanisms may serve several packs, but each pack retains distinct acceptance and evidence.

## Dependency map

Common relationships:

    enterprise-sso ----> multi-tenant-saas
             |                    |
             v                    v
       onboarding ----------> customer-health

    connector-pack ----> webhook-engine ----> incident-response
          |                    |
          v                    v
      secure-rag          usage-metering
          |
          v
    pii-redaction

    all runtime packs ----> one-click-deployment ----> deployment-case-study

These arrows mean "often depends on," not "automatically include." For example, a single-tenant
internal connector may not need a SaaS tenancy pack. Record why an apparent dependency is omitted.

## Multi-tenant SaaS

### Use when

Multiple customer organizations share an application, service, database, queue, cache, file store,
search index, vector store, or operations plane.

### Decisions

- tenant unit and organization hierarchy;
- user-to-organization membership and active context;
- role and permission model;
- storage isolation pattern per store;
- tenant context in jobs, caches, logs, metrics, exports, and deletions;
- support and administrative cross-tenant access;
- tenant lifecycle and legal hold behavior.

### Typical implementation shape

- organization, membership, role, and permission records;
- server-created tenant context;
- tenant-scoped repository APIs;
- database policies where supported;
- tenant-bearing job envelope and idempotency key;
- tenant-safe telemetry attributes;
- isolation, export, deletion, and admin-path tests.

### Failure proof

Exercise guessed IDs, stale membership, missing context, forged headers, cache-key collisions,
queued work after deprovisioning, support impersonation, exports, and inference through counts or
error differences.

## Enterprise SSO

### Use when

Customer organizations require SAML or OIDC federation, domain or organization connection
discovery, just-in-time membership, directory provisioning, or enterprise login administration.

### Decisions

- protocol and flow;
- managed broker, direct identity provider, self-hosted control plane, or existing auth;
- organization binding and connection discovery;
- IdP-initiated support;
- account linking and email-change behavior;
- JIT versus SCIM ownership;
- Users, Groups, membership, and extension scope;
- deactivation, reactivation, deletion, and break-glass access.

### Typical implementation shape

- connection record bound to an organization;
- state, nonce, PKCE, redirect, issuer, audience, signature, and time validation;
- callback transaction store;
- membership policy;
- SCIM resources, pagination, filters, errors, and reconciliation;
- secret rotation and audit events.

### Failure proof

Test wrong-organization assertions, replay, expired state, malicious redirect, issuer or audience
mismatch, certificate rollover, duplicate email, deactivated user, partial provisioning, and group
reconciliation.

## Connector pack

### Use when

The product reads, writes, or triggers actions in customer SaaS, cloud, database, messaging, or
support systems.

### Decisions

- exact providers and operations;
- OAuth, API key, service account, app installation, workload identity, or customer-managed auth;
- least scopes and approval flow;
- managed integration platform versus direct adapter;
- native and normalized schemas;
- cursor, checkpoint, backfill, and deletion behavior;
- rate limits, partial failure, retry, and reconciliation;
- per-tenant credential and connection boundaries.

### Typical implementation shape

- provider definition and capability matrix;
- credential reference;
- setup and callback flow;
- typed client and error taxonomy;
- checkpointed sync or action worker;
- normalization boundary;
- recorded contract fixtures;
- unsupported-operation errors.

### Failure proof

Test denial, expiry, refresh race, revocation, reinstallation, pagination loops, provider schema
drift, 429 and reset behavior, accepted-but-lost writes, partial pages, poison records, and replay.

## Secure RAG

### Use when

Customer documents or records are ingested, indexed, retrieved, and supplied to a model or search
experience under tenant or document permissions.

### Decisions

- source systems and authority for ACLs;
- document, version, chunk, deletion, and permission provenance;
- parser and classification pipeline;
- embedding provider and data egress;
- vector or hybrid search store;
- tenant and ACL filter model;
- citation requirements;
- prompt-injection and retrieval evaluation set;
- retention, deletion, re-indexing, and legal holds.

### Typical implementation shape

- permission-aware ingestion;
- immutable source/version identifiers;
- classified and optionally redacted chunks;
- tenant/ACL-aware index;
- authorization filters inside retrieval;
- citation assembler;
- deletion propagation;
- leakage and relevance evaluation.

### Failure proof

Exercise stale ACLs, copied links, cross-tenant filters, deleted sources, adversarial documents,
encoded sensitive values, citation mismatch, empty retrieval, oversized documents, and model
instructions embedded in sources.

## Customer health

### Use when

Customer success or field teams need an operational view of adoption, integration health, risk,
support burden, or milestones.

### Decisions

- decisions the score supports;
- authoritative event and account sources;
- visible metrics versus composite score;
- freshness and correction semantics;
- tenant and employee access;
- qualitative notes and ownership;
- escalation and workflow links;
- how score behavior is explained and audited.

### Typical implementation shape

- metric definitions and event contracts;
- account snapshot;
- transparent score components;
- stale/missing data indicators;
- drill-down evidence;
- role-safe dashboard or export;
- quality checks and reconciliation.

### Failure proof

Test missing events, late corrections, duplicate accounts, stale snapshots, changed definitions,
inaccessible customer data, misleading aggregation, and score behavior without sufficient data.

## Webhook engine

### Use when

The system receives untrusted asynchronous HTTP events or delivers outbound webhooks with retries.

### Decisions

- provider signature scheme and raw-body needs;
- tolerance and replay window supplied by protocol or owner;
- dedupe identifier and retention;
- acknowledgement versus processing boundary;
- queue, ordering, concurrency, and idempotency;
- retry classification and dead-letter behavior;
- replay authorization and audit;
- outbound subscription, signing, rotation, and delivery logs.

### Typical implementation shape

- raw request capture with strict size/content handling;
- signature verification before parsing;
- event inbox and deterministic dedupe;
- durable worker and handler registry;
- idempotent effects;
- dead-letter and replay controls;
- outbound delivery state machine.

### Failure proof

Test forged, stale, duplicated, reordered, malformed, oversized, unknown-version, and poison events;
worker crashes; accepted-but-uncommitted events; key rotation; endpoint timeouts; and replay.

## One-click deployment

### Use when

A repeatable customer or demo environment must be installed, upgraded, rolled back, and removed
with a narrow interface.

### Decisions

- target platform and ownership boundary;
- managed cloud, customer cloud, on-premises, edge, or air-gapped model;
- image, artifact, and dependency distribution;
- configuration and secret inputs;
- infrastructure-as-code engine;
- database and migration lifecycle;
- network, DNS, certificate, and identity dependencies;
- health, rollback, backup, restore, upgrade, and teardown.

### Typical implementation shape

- validated configuration contract;
- pinned artifacts and provenance;
- dry-run plan;
- idempotent provision/update path;
- readiness and smoke tests;
- rollback and cleanup;
- operator guide.

### Failure proof

Test missing permissions, partial provision, repeated apply, incompatible upgrade, failed migration,
lost connectivity, expired certificate, restore, rollback, teardown, and sensitive output.

## PII redaction

### Use when

Sensitive values must be detected, classified, transformed, blocked, or audited in files, text,
events, prompts, logs, support artifacts, or model pipelines.

### Decisions

- data classes and jurisdictions;
- structured, unstructured, image, audio, and multilingual scope;
- detect, mask, tokenize, hash, encrypt, block, or review action;
- reversibility and key ownership;
- false-positive and false-negative priorities;
- custom entities and context rules;
- quarantine and human review;
- evaluation corpus and safe evidence.

### Typical implementation shape

- policy model;
- detector adapters;
- structured-field rules;
- transformation engine;
- audit record without exposed value;
- evaluation harness;
- safe samples and regression suite.

### Failure proof

Test formatting variants, Unicode, nested JSON, encoded content, overlapping entities, secrets,
partial identifiers, multilingual text, allowlists, repeated deterministic transformations, and
round trips when reversibility is approved.

## Incident response

### Use when

The delivered system needs explicit detection, ownership, investigation, mitigation,
communication, recovery, and learning paths.

### Decisions

- service ownership and escalation authority;
- severity model and customer communication;
- telemetry and alert signals;
- evidence retention and access;
- credential compromise, data exposure, provider outage, and integrity scenarios;
- isolation, rollback, failover, and feature-disable controls;
- post-incident review and follow-up ownership.

### Typical implementation shape

- ownership metadata and runbooks;
- alert routing;
- incident record;
- timeline and evidence collection;
- narrow mitigations;
- communication templates;
- exercise plan.

### Failure proof

Tabletop and, where safe, exercise alert delivery, revoked credentials, queue backlog, bad deploy,
provider outage, tenant exposure signal, stale runbook, unavailable owner, rollback, and recovery
verification.

## Usage metering

### Use when

Events affect quotas, entitlements, customer reporting, invoices, cost allocation, or contractual
usage.

### Decisions

- billable event and measurement unit;
- identity and tenant attribution;
- event time, processing time, and correction semantics;
- dedupe and idempotency key;
- aggregation windows and owner-supplied lateness policy;
- source-of-truth ledger;
- pricing and entitlement boundary;
- reconciliation, dispute, export, and audit.

### Typical implementation shape

- versioned usage event;
- append-only ingest;
- idempotency and correction model;
- aggregation;
- ledger-to-provider export;
- reconciliation report;
- customer-visible breakdown.

### Failure proof

Test duplicates, reordering, late arrival, corrections, tenant mismatch, negative values, clock
skew, provider outage, reruns, plan changes, partial export, and ledger disagreement.

## Onboarding automation

### Use when

Customer setup spans multiple systems, prerequisites, approvals, long-running steps, or handoffs.

### Decisions

- onboarding definition of done;
- actors and approvals;
- prerequisite and credential checks;
- workflow engine or in-application state machine;
- idempotency, retry, pause, resume, cancellation, and rollback;
- manual task and escalation behavior;
- customer-visible progress;
- sensitive input and audit rules.

### Typical implementation shape

- versioned workflow definition;
- durable execution state;
- step adapters;
- approval and manual-task records;
- retry and compensation policy;
- progress view;
- audit trail and completion evidence.

### Failure proof

Test duplicate starts, approval denial, missing credential, provider timeout, process restart,
manual delay, cancellation, changed workflow version, compensation failure, and resumed execution.

## Deployment case study

### Use when

The outcome includes a reproducible, honest demonstration of field delivery, not only reusable
infrastructure.

### Decisions

- audience and claim;
- source scenario and permitted artifacts;
- environment and reproduction path;
- before and after behavior;
- architecture and security decisions worth explaining;
- exact commands and evidence safe to publish;
- redaction and customer-confidentiality boundary;
- limitations and unproven claims.

### Typical implementation shape

- scenario brief;
- reproducible setup;
- sanitized fixtures;
- architecture narrative;
- command transcript;
- retained outputs;
- limitations and lessons.

### Failure proof

Have an independent operator reproduce it from the documented starting point. Confirm secrets and
customer data are absent, links work, outputs match the inspected revision, and every public claim
maps to retained evidence.

## Combination rules

### SSO plus multi-tenancy

Bind identity connection, assertion, membership, and role to the expected organization. Email
domain alone is discovery, never authorization.

### Connector plus webhook

Use one connection identity and event model. Installation, token refresh, webhook subscription,
inbound verification, sync checkpoint, and deletion should reconcile as one lifecycle.

### Connector plus RAG

Carry provider object ID, version, tenant, ACL, connection, and deletion identifiers through every
chunk. Provider permissions must constrain retrieval.

### RAG plus PII

Decide whether classification or redaction happens before storage, before embedding, before
retrieval output, before generation, or at several stages. Each stage has different deletion,
quality, and evidence implications.

### Metering plus customer health

Do not let a mutable health score become a billing ledger. They may share events, but billing
requires its own versioned, reconcilable authority.

### Onboarding plus every integration

Onboarding coordinates setup; it does not own provider protocol logic. Keep connector, identity,
deployment, and workflow adapters independently testable.

### Deployment plus incident response

Every automated deployment needs rollback, ownership, health signals, and incident entrypoints.
Every runbook must identify the exact deployment unit and configuration boundary.
