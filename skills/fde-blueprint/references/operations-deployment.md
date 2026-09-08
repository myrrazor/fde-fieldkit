# Operations and deployment

## Contents

1. Deployment contract
2. Environment models
3. Infrastructure as code
4. Artifacts and supply chain
5. Configuration and secrets
6. Database and state
7. Health and observability
8. Incident response
9. Upgrade, rollback, and teardown
10. Verification

## Deployment contract

"One click" means one narrow, repeatable interface over explicit prerequisites and failure
behavior. It does not mean hiding permissions, state, cost, or rollback.

Define:

- operator;
- target account, subscription, project, cluster, or host;
- deployment unit;
- prerequisite identities and permissions;
- configuration inputs;
- secret references;
- data and state ownership;
- network and DNS dependencies;
- success, readiness, and acceptance checks;
- update, rollback, backup, restore, and removal.

Every command needs a dry-run or plan when its platform supports one. Output must not expose
secrets.

## Environment models

### Managed cloud

The product team operates infrastructure. Decide account boundaries, regions, customer isolation,
service identities, egress, backups, incident ownership, and tenancy.

### Customer cloud

The customer owns the account; the provider may supply artifacts and automation. Define who can
inspect state, receive telemetry, rotate secrets, apply upgrades, and handle incidents.

### On-premises

Account for restricted registries, proxies, certificates, DNS, storage classes, identity systems,
maintenance windows, and limited remote access.

### Edge

Plan for intermittent connectivity, local state, update signing, hardware variance, remote
diagnostics, resource constraints, and recovery.

### Air-gapped

Define an offline dependency and artifact bundle, integrity verification, license and SBOM
delivery, secret bootstrap, time synchronization, update transfer, and offline evidence
collection. Do not assume any package registry or certificate endpoint is reachable.

## Infrastructure as code

### OpenTofu

OpenTofu is a candidate open-source Terraform-compatible infrastructure engine under MPL-2.0.
Confirm provider and module compatibility for the target.

### Terraform

Current Terraform licensing is source-available under BUSL for covered versions. Integrating the
CLI under customer terms differs from adapting its source. Record exact version and terms.

### Pulumi

Pulumi's core tooling is a permissive open-source candidate with language-based definitions.
Review backend, state, provider, and managed-service choices separately.

### Docker Compose

Useful for a local or single-host demonstration and some customer environments. It does not
substitute for high availability, multi-host scheduling, managed secrets, or production backup
without explicit additional design.

### Kubernetes, Helm, and K3s

Kubernetes is an orchestration platform, Helm is a packaging mechanism, and K3s is a distribution.
Choose each independently. A chart must still define security context, resources from evidence,
storage, upgrades, rollback, probes, network, secrets, and ownership.

### Selection

Prefer the target platform's established tool. A new IaC engine needs an owner decision if it
changes state, review, credentials, or operations.

## Artifacts and supply chain

Pin:

- source revision;
- dependency lock;
- compiler and runtime;
- container base and digest where the workflow supports it;
- generated assets;
- infrastructure providers and modules;
- model or data artifacts in scope.

Produce or retain, as required:

- build log;
- tests;
- SBOM using CycloneDX or SPDX;
- provenance aligned with SLSA concepts;
- vulnerability and policy results;
- OpenSSF Scorecard input for dependency review;
- signature and verification using Sigstore or the approved system;
- license notices.

These standards and tools support evidence. They do not make an artifact trustworthy without a
verified pipeline and policy.

## Configuration and secrets

Separate:

- non-secret validated configuration;
- secret names and references;
- generated identifiers and outputs;
- runtime-discovered state;
- customer-provided values.

Candidate secret mechanisms include:

- cloud-native secret managers and workload identity;
- SOPS-encrypted configuration;
- Vault;
- Infisical;
- External Secrets Operator.

Vault is source-available for current covered releases; Infisical has mixed licensing; SOPS and
External Secrets have permissive or weak-copyleft terms recorded in the catalog. Review exact
deployment and feature scope.

Prefer workload identity over long-lived credentials where the target supports it. Never put
secret values into plan files, command arguments visible to process listings, logs, generated
Markdown, or state outputs without a protected design.

Validate required configuration before mutating infrastructure.

## Database and state

Inventory:

- application database;
- infrastructure state;
- object storage;
- queue and event retention;
- vector or search index;
- cache;
- secrets;
- backups;
- audit records.

For schema changes define:

- compatibility requirement from actual consumers;
- preflight;
- migration transaction behavior;
- long-running or locking risk;
- application rollout order;
- backfill;
- validation;
- rollback or forward-fix;
- backup and restore.

Never claim rollback if a destructive data migration cannot be reversed.

Infrastructure state must have access control, locking, backup, and secret-handling appropriate to
the target. A local state file is not an invisible implementation detail.

## Health and observability

### Health

Separate:

- process liveness;
- readiness to receive traffic;
- dependency or provider degradation;
- background backlog;
- business-level correctness.

Do not make liveness depend on every remote provider and cause cascading restarts.

### Telemetry

OpenTelemetry is a candidate standard and implementation ecosystem for traces, metrics, and logs.
Define stable attributes for tenant, connection, operation, outcome, and correlation without
exposing sensitive data.

### Error reporting

Sentry is a managed candidate for error and performance monitoring. Review payload scrubbing,
source maps, environment, release identity, region, retention, and access.

### Alerting

PagerDuty or another incident platform can route alerts. An alert requires:

- actionable condition;
- owner;
- severity;
- safe context;
- runbook;
- escalation;
- resolution signal.

Do not turn every error log into a page.

### Product analytics

PostHog and similar tools concern product usage, not service health. Review event data, identity,
deployment model, license scope, consent, retention, and customer policy.

## Incident response

Define scenarios:

- customer data exposure;
- credential compromise;
- provider outage or revocation;
- queue backlog;
- bad deploy or migration;
- corrupted state;
- certificate or DNS failure;
- regional or host failure;
- observability outage;
- unauthorized administrative access.

For each scenario record:

- detection;
- triage owner;
- evidence sources;
- immediate containment;
- customer impact assessment;
- communication authority;
- recovery;
- validation;
- follow-up.

Runbooks should use exact service, dashboard, and command names only after they exist. Blueprint
runbooks remain planned.

## Upgrade, rollback, and teardown

### Upgrade

Plan:

- version discovery;
- release notes and compatibility;
- backup;
- dry run;
- schema and infrastructure changes;
- phased or atomic application update;
- readiness;
- reconciliation;
- evidence.

### Rollback

State which layers can roll back:

- application artifact;
- configuration;
- infrastructure;
- database schema;
- data backfill;
- provider configuration.

If rollback is impossible for one layer, define containment and forward recovery.

### Teardown

Inventory resources before removal. Protect shared and retained data. Confirm tenant, environment,
account, region, and owner. Revoke credentials and provider subscriptions. Retain audit and
evidence according to policy. Report what remains.

## Verification

Test:

- clean install;
- missing or invalid prerequisites;
- plan with no mutation;
- repeated apply;
- partial failure and resume;
- configuration validation;
- secret absence from output;
- migration and data validation;
- readiness and smoke behavior;
- backup and restore;
- upgrade;
- rollback or documented forward recovery;
- provider or network degradation;
- alert delivery and runbook;
- teardown and orphan detection;
- offline install for air-gapped claims;
- independent reproduction.

Record the exact environment and revision. A local container smoke test does not prove a customer
cloud, Kubernetes, on-premises, edge, or air-gapped deployment.
