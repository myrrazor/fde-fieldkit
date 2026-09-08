# Security and verification

## Contents

1. Claim discipline
2. Threat model
3. Security invariants
4. API and integration risks
5. LLM and RAG risks
6. Secrets and sensitive data
7. Supply chain
8. Verification layers
9. Evidence quality
10. Release gate

## Claim discipline

Blueprints describe intent. Source proves an implementation exists at a revision. Tests prove
specific controlled behavior. Runtime evidence proves behavior in a named environment at a time.
None of these automatically proves the others.

Use precise states:

- proposed;
- selected;
- scaffolded;
- implemented;
- statically verified;
- tested with fixtures;
- tested in sandbox;
- deployed;
- live verified;
- monitored.

The blueprint generator is allowed to claim only proposed or selected decisions and pending
evidence.

## Threat model

Identify:

- assets;
- actors and privileges;
- trust boundaries;
- entrypoints;
- sensitive data paths;
- external dependencies;
- administrative paths;
- failure and recovery paths.

Assets often include:

- customer data;
- credentials and signing keys;
- identities and memberships;
- provider connections;
- documents and ACLs;
- usage and billing records;
- workflow approvals;
- deployment state;
- evidence and audit records.

Attackers and failures include:

- unauthenticated external actor;
- authenticated user crossing tenant or object boundaries;
- compromised customer admin;
- compromised provider credential;
- malicious or buggy external provider;
- untrusted webhook or document;
- support or global administrator misuse;
- dependency or build compromise;
- operator mistake;
- worker retry or race;
- stale authorization or cache.

## Security invariants

Good invariants:

- are testable;
- name the protected boundary;
- remain true during retries, migration, support, and failure;
- do not depend on UI behavior;
- fail closed when context is missing.

Examples:

- Every persistent and transient customer-data access is constrained by trusted tenant context.
- A provider credential can be resolved only through its owning tenant and connection.
- A webhook is authenticated before its payload affects durable business state.
- Unauthorized chunks never enter retrieval candidates, model prompts, caches, or traces.
- A duplicate usage event cannot change the authoritative total twice.
- Generated output contains secret references, never credential values.

Turn each invariant into multiple proofs where it spans layers.

## API and integration risks

Use the OWASP API Security Top 10 as a review lens, not a substitute for a product-specific threat
model.

### Object authorization

Test direct and indirect references across tenants, users, connections, files, jobs, and exports.

### Authentication

Test token validation, session lifecycle, API keys, service identities, and credential rotation.
Rate or resource protections must derive from platform and owner requirements.

### Property authorization

Test sensitive fields in reads, writes, logs, exports, errors, and normalized provider records.

### Resource consumption

Validate size, complexity, concurrency, queue, and provider-use controls from measured capacity or
contract. Do not invent universal limits in a blueprint.

### Function authorization

Test administrative actions, replay, export, delete, support access, provider writes, billing
corrections, and deployment operations.

### Sensitive business flows

Protect signup, invitation, OAuth installation, onboarding, billing, export, and support workflows
against automation and abuse according to real business requirements.

### Server-side request forgery

Outbound webhooks, imports, callbacks, and URL fetchers need scheme, destination, redirect, DNS,
network, and metadata-service protections appropriate to the deployment.

### Misconfiguration and inventory

Inventory versions, routes, providers, scopes, public endpoints, environments, and deprecated
interfaces. Remove unsupported behavior rather than leaving hidden compatibility paths.

### Unsafe API consumption

Treat provider data as hostile. Validate schemas, constrain rendered output, classify errors, and
avoid trusting provider redirects or identifiers as local authority.

## LLM and RAG risks

Use the OWASP guidance for LLM applications as another lens.

### Prompt injection

Separate trusted instructions from untrusted source content. Constrain tools by server-side
authority. Do not let retrieved text grant permissions or alter security policy.

### Sensitive disclosure

Filter authorization before retrieval. Control prompt, response, telemetry, cache, evaluation,
and support artifacts. Avoid claiming that a model will reliably self-redact.

### Supply chain

Models, prompt templates, vector databases, loaders, parsers, plugins, and evaluation data are
dependencies. Pin and review them according to risk.

### Data and model poisoning

Preserve source provenance and version. Restrict ingestion sources. Detect unexpected changes and
evaluate adversarial documents.

### Improper output handling

Treat model output as untrusted before HTML, SQL, shell, code, URL, or provider-action use. Use
structured validation and narrow commands.

### Excessive agency

Grant the minimum tools, scopes, tenants, operations, and confirmation behavior. An agent should
not inherit a global connector credential for convenience.

### Vector weaknesses

Test cross-tenant filters, stale ACL, shared cache, poisoned metadata, deletion, and index
reconciliation.

## Secrets and sensitive data

Inventory:

- OAuth client and refresh secrets;
- API keys;
- webhook signing secrets;
- SAML private keys;
- database credentials;
- cloud and deployment identities;
- encryption and pseudonymization keys;
- provider service-account keys;
- evidence and support exports.

Prefer:

- workload identity;
- short-lived credentials;
- secret-manager references;
- least scope;
- rotation;
- revocation;
- access audit.

Do not expose secrets in:

- source;
- answer files;
- blueprint packets;
- process arguments;
- environment dumps;
- logs and traces;
- test snapshots;
- screenshots;
- infrastructure outputs;
- error messages.

Sanitization must preserve enough structure to diagnose and audit without leaking values.

## Supply chain

### Source review

For any reused code record:

- upstream URL;
- exact commit or release;
- file paths;
- license and notices;
- modification;
- transitive dependencies;
- maintenance and security status;
- test evidence;
- internal reviewer.

### Standards and formats

CycloneDX and SPDX can describe components and licenses. SLSA provides a supply-chain integrity
framework. Sigstore can sign and verify artifacts. OpenSSF Scorecard can surface repository
security signals.

These are inputs to policy. A high score or signed artifact does not replace review of behavior,
authority, or customer fit.

### Dependencies

Before adding a dependency verify:

- it is necessary;
- official source and package identity;
- current supported version;
- license;
- maintenance;
- known security concerns;
- transitive footprint;
- runtime permissions and network behavior;
- target-language and framework compatibility;
- removal or replacement path.

Blueprint generation adds no runtime dependency.

## Verification layers

### Static

- formatting and lint;
- type checking;
- schema validation;
- dependency and license inventory;
- secret scan;
- infrastructure plan and policy;
- route and permission inventory.

### Unit

- parsers;
- validators;
- policy decisions;
- signature construction;
- idempotency keys;
- normalization;
- retry classification;
- aggregation and correction.

### Integration

- database policies and transactions;
- tenant boundary;
- queue redelivery;
- secret resolution;
- provider fixture contracts;
- SCIM and webhook behavior;
- vector filters and deletion.

### Sandbox

- real OAuth consent;
- token refresh and revocation;
- provider pagination and limits;
- SSO configuration;
- webhook delivery;
- billing export;
- deployment target behavior.

### Live

Only when authorized:

- current customer or production configuration;
- real end-to-end user path;
- operational alert and runbook;
- current access and data boundary;
- rollback or recovery behavior safe to exercise.

Label every layer. A sandbox provider can differ from production plans, scopes, limits, data, and
event behavior.

## Evidence quality

Strong evidence includes:

- exact revision;
- exact command;
- environment;
- input fixture or safe test identity;
- stdout, stderr, and exit code;
- retained artifact path and checksum;
- expected and observed behavior;
- redaction method;
- reviewer when required.

Weak evidence includes:

- a historical screenshot;
- a copied log without revision;
- a test name without output;
- documentation saying a feature should work;
- generated source that was not executed;
- a mocked success for a live-provider claim;
- an unverified status dashboard.

Do not expose customer data merely to make evidence stronger. Use safe identities, synthetic
fixtures, minimized excerpts, and controlled artifact access.

## Release gate

Before claiming implementation complete:

- every necessary invariant maps to proof;
- authorization covers object, property, function, tenant, provider, and admin boundaries;
- failure, retry, replay, correction, and reconciliation paths are tested;
- secret and sensitive-data scans are clean or findings are resolved;
- dependencies and source reuse have exact provenance;
- build, tests, lint, and target-specific checks pass;
- deployment and rollback claims match the exercised environment;
- evidence artifacts belong to the inspected revision;
- open decisions that affect safety or correctness are resolved;
- unsupported or unverified modes are labeled.

The blueprint itself should never pass this release gate. Its job is to define it.
