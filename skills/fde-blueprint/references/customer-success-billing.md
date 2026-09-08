# Customer success, metering, and onboarding

## Contents

1. Shared operating model
2. Customer health
3. Usage metering
4. Billing products
5. Onboarding automation
6. Workflow products
7. Data contracts
8. Authorization and privacy
9. Failure semantics
10. Evidence

## Shared operating model

Customer health, usage metering, and onboarding often consume the same account and event data, but
they serve different authorities:

- health supports human prioritization and diagnosis;
- metering supports entitlements, reporting, allocation, or billing;
- onboarding coordinates a durable process.

Do not collapse them into one mutable score or workflow table. Share versioned events and stable
tenant identity while preserving separate source-of-truth contracts.

## Customer health

### Start with the decision

Ask what action the view supports:

- identify integration failure;
- prioritize adoption outreach;
- identify blocked onboarding;
- prepare an executive review;
- detect risk;
- verify value realization;
- coordinate support and engineering.

A dashboard without an action and owner becomes decorative.

### Metric contract

For every metric record:

- name and plain-language meaning;
- source;
- tenant and environment;
- event or snapshot;
- time field and timezone;
- inclusion and exclusion;
- correction and backfill behavior;
- freshness;
- missing-data behavior;
- owner;
- version.

Do not let an event name imply its meaning. "active" might mean login, API call, completed workflow,
or contract status.

### Transparent health

Prefer visible components over an unexplained score. If a composite score is required:

- show component values and weights;
- version the formula;
- distinguish missing from bad;
- retain reason codes;
- recalculate historical values deliberately;
- let operators drill into evidence;
- test edge behavior.

Never fabricate a universal "healthy above 80" threshold. The owner or measured product evidence
must establish thresholds.

### Data quality

Surface:

- last refresh;
- incomplete sources;
- late events;
- duplicate mapping;
- unresolved tenant identity;
- changed metric version;
- provider outage;
- reconciliation status.

Stale confidence is worse than visible uncertainty.

### Tool patterns

PostHog can supply product event analysis; Apache Superset can visualize governed data. Neither
defines account identity, metric meaning, or access policy. A bespoke dashboard may better embed
action workflows. Compare data egress, deployment, licensing, row access, and operator workflow.

## Usage metering

### Event contract

A usage event commonly needs:

- stable event ID;
- schema version;
- tenant or account;
- subject or resource;
- meter name;
- quantity and unit;
- event time;
- observed or ingested time;
- source;
- idempotency key;
- correction or reversal reference;
- attributes allowed by policy.

Use decimal or integer semantics appropriate to the unit. Do not let floating-point behavior
silently alter billed totals.

### Time

Separate:

- when usage happened;
- when the system received it;
- when it entered the ledger;
- which billing or reporting window consumes it.

Late and corrected events need owner-defined policy. The blueprint must not invent a cutoff.

### Ledger

Prefer an append-oriented record that supports:

- idempotent ingest;
- correction rather than invisible mutation;
- trace from source to aggregate;
- deterministic rerun;
- reconciliation;
- tenant export;
- dispute investigation;
- retention and deletion policy consistent with contractual records.

### Aggregation

Define:

- count, sum, maximum, duration, unique, tier, or custom measure;
- grouping keys;
- window and timezone;
- plan or entitlement version;
- correction behavior;
- empty usage;
- negative or reversal events;
- rounding;
- provider export mapping.

### Entitlement and billing boundary

Metering measures usage. Entitlements decide allowed access. Pricing converts usage into charges.
Invoice systems issue financial documents. These may be integrated but should remain separately
testable.

## Billing products

### Stripe Billing

Stripe supports subscriptions and usage-based billing patterns. Current product guidance may route
new usage cases toward Stripe's Metronome offering; verify current official documentation and
account availability before selecting an architecture.

### OpenMeter

OpenMeter is an Apache-licensed metering candidate. Review exact event, aggregation, entitlement,
storage, and managed versus self-hosted features.

### Lago

Lago is an AGPL-licensed billing candidate with managed offerings. Reciprocal obligations and
deployment model require explicit owner review.

### Kill Bill

Kill Bill is an Apache-licensed billing platform candidate. Its plugin and operational model is
substantially larger than a narrow meter; select only if those capabilities are necessary.

### Commercial meters

Metronome and Orb are managed candidates. Compare ingestion semantics, corrections, dimensions,
pricing model, exports, data processing, support, and contract.

### Custom ledger

A custom ledger avoids a vendor abstraction only by owning correctness, reconciliation, pricing
change, audit, dispute, migration, and operations. Do not label it simpler without evidence.

## Onboarding automation

### Define done

Customer onboarding may require:

- organization creation;
- contract or approval;
- identity connection;
- directory sync;
- provider installation;
- data backfill;
- permission verification;
- configuration;
- deployment;
- training;
- live acceptance.

Define which steps are automated, customer-owned, internal manual work, or external prerequisites.

### Workflow state

Persist:

- workflow definition version;
- tenant;
- execution ID;
- current and completed steps;
- inputs by reference;
- outputs safe for storage;
- attempt and outcome;
- approval;
- manual task;
- cancellation;
- audit.

Do not store credentials as workflow values when a secret reference is sufficient.

### Durable semantics

For each step define:

- precondition;
- idempotency;
- timeout from authoritative provider or owner policy;
- retryable errors;
- permanent errors;
- pause and resume;
- compensation;
- cancellation;
- evidence.

Retries are not a substitute for reconciliation.

### Human work

Model human tasks explicitly:

- owner;
- reason;
- required input;
- approval authority;
- due date only when owner-supplied;
- escalation;
- audit;
- resume condition.

A hidden Slack message is not durable workflow state.

### Customer experience

Show:

- steps complete;
- current work;
- blockers and who owns them;
- safe corrective action;
- last update;
- expected next event;
- support contact;
- evidence of completion.

Avoid exposing internal stack traces, secrets, or cross-customer data.

## Workflow products

### Temporal

Temporal fits durable application workflows with activities, retries, signals, timers, and
long-running execution. It adds a service and programming model that the team must operate or buy.

### n8n

n8n offers broad visual automation under a sustainable-use license. Source availability does not
make every embedding or commercial use permissible. Review the exact license and hosting model.

### Windmill

Windmill combines scripts, workflows, apps, and workers with mixed licensing and enterprise areas.
Review file and feature boundaries.

### Kestra

Kestra is an Apache-licensed orchestration candidate. Evaluate event, workflow, plugin, deployment,
and operations fit.

### Dagster

Dagster focuses on data assets and pipelines. It may fit onboarding only when onboarding is truly a
data orchestration problem.

### Prefect

Prefect focuses on Python workflow orchestration with managed and self-hosted choices. Review
current server, worker, state, and commercial boundaries.

### In-application state machine

A local state machine may be sufficient for short, simple workflows already bounded by the
application database and worker system. It still needs durability, idempotency, visibility,
cancellation, migrations, and tests.

## Data contracts

Use stable shared identifiers:

- tenant;
- account;
- user or actor;
- provider connection;
- environment;
- product or entitlement;
- workflow execution;
- usage event;
- metric definition version.

Version event schemas. Validate producers and consumers. Keep provider-native identifiers beside
local IDs, never in place of tenant authority.

Late, corrected, and replayed events must have deterministic meaning across health, metering, and
workflow consumers.

## Authorization and privacy

Decide who may:

- view account health;
- view raw events;
- edit qualitative notes;
- change metric or score definitions;
- replay or correct usage;
- view invoice-impacting details;
- start, cancel, or override onboarding;
- impersonate a customer;
- export data.

Apply tenant and field-level controls. Customer success notes, usage, billing, and onboarding
artifacts can contain confidential and personal data. Include retention, deletion, legal hold,
audit, and regional processing decisions.

## Failure semantics

Exercise:

- unknown tenant mapping;
- duplicate and late events;
- provider outage;
- stale account snapshot;
- partial backfill;
- changed metric definition;
- billing export timeout with unknown outcome;
- corrected usage;
- workflow worker restart;
- duplicate workflow start;
- denied approval;
- missing credential;
- cancellation during external work;
- compensation failure;
- customer and operator viewing different states.

Show degradation explicitly. Never turn missing data into a healthy zero without a declared
contract.

## Evidence

Customer health:

- metric dictionary;
- source-to-account reconciliation;
- freshness and missing-data tests;
- authorization tests;
- score explanation and version test when applicable;
- operator workflow demonstration.

Metering:

- event schema and ledger invariant tests;
- duplicate, late, correction, rerun, and reconciliation tests;
- provider sandbox evidence when authorized;
- tenant export trace;
- invoice or entitlement boundary proof.

Onboarding:

- workflow graph and ownership;
- restart, retry, pause, resume, cancel, and compensation tests;
- manual approval audit;
- safe progress view;
- independent end-to-end rehearsal.

Keep synthetic, sandbox, staging, and production evidence labeled separately.
