# Stack profiles

## Contents

1. Selection doctrine
2. Shared adapter contract
3. TypeScript
4. Python
5. Go
6. Java
7. .NET
8. Ruby
9. Rust
10. Other stacks
11. Repository mapping
12. Verification matrix

## Selection doctrine

Use the target product's existing language and framework unless the owner is choosing a new
service boundary or the current tool cannot satisfy a necessary contract. Familiarity alone is
not a reason to introduce a second runtime.

Select by:

- existing service and team ownership;
- provider SDK and protocol library quality;
- async, streaming, and worker requirements;
- deployment and operations model;
- security maintenance;
- test and contract-fixture support;
- target repository conventions.

The catalog language profiles are candidate defaults, not mandates.

## Shared adapter contract

Every later language generator should implement the same logical boundaries:

- configuration schema with secret references;
- tenant and actor context;
- provider or protocol interface;
- typed native payload boundary;
- normalized domain boundary;
- idempotency and checkpoint store;
- error taxonomy with retry classification;
- structured telemetry;
- health and readiness;
- fixtures, unit tests, integration tests, and contract tests.

Generated code should expose unsupported behavior explicitly. Do not create empty methods that
return success.

Suggested provider error classes:

- authentication or authorization;
- invalid request;
- conflict;
- rate limited;
- transient provider failure;
- permanent provider failure;
- schema or contract drift;
- local persistence failure;
- unknown outcome requiring reconciliation.

## TypeScript

### Good fit

API-heavy products, web applications, event handlers, provider SDK ecosystems, and shared browser
or server types.

### Framework patterns

- Fastify: plugin encapsulation, schema-based routes, hooks, serializers, inject-based testing.
- NestJS: modules, dependency injection, controllers, guards, interceptors, and providers.
- Next.js route handlers: web-product integration where runtime and deployment constraints are
  understood.
- Express: existing products; add explicit validation and boundaries rather than assuming
  middleware order.

### Module shape

    src/integrations/provider/
      client.ts
      auth.ts
      schemas.ts
      errors.ts
      sync.ts
      webhooks.ts
      index.ts

Match the repository rather than forcing this exact tree.

### Decisions

- Node runtime and module system;
- package manager and lockfile;
- fetch implementation and timeout ownership;
- runtime validation library;
- queue and job runtime;
- database transaction boundary;
- source versus generated API types.

### Verification

Run the repository's formatter, type checker, linter, unit tests, contract fixtures, and integration
tests. TypeScript types do not validate external JSON at runtime.

## Python

### Good fit

Data pipelines, RAG, automation, APIs, operational tools, and provider integrations with mature
Python SDKs.

### Framework patterns

- FastAPI: dependency boundaries, Pydantic request/response models, async lifespan, test clients.
- Django: organizations, admin operations, ORM transactions, management commands, and mature auth.
- Flask: existing lightweight services; make app factory and dependency boundaries explicit.

### Module shape

    app/integrations/provider/
      client.py
      auth.py
      models.py
      errors.py
      sync.py
      webhooks.py

### Decisions

- Python and packaging version;
- uv, Poetry, pip-tools, or repository-authoritative workflow;
- sync versus async client;
- validation model version;
- worker framework;
- ORM and migration tool;
- type-checking strictness.

### Verification

Run formatter or style check, linter, type checker if configured, pytest, contract fixtures, and
integration tests. Mocked HTTP must preserve raw signatures, headers, pagination, and error bodies
needed by production logic.

## Go

### Good fit

Small services, high-concurrency event processing, static deployment artifacts, agents, and
operator tooling.

### Framework patterns

- net/http or chi for explicit, low-dependency service boundaries;
- Gin or Fiber when already established;
- context propagation for deadlines, cancellation, tenant, tracing, and request scope.

### Module shape

    internal/integrations/provider/
      client.go
      auth.go
      types.go
      errors.go
      sync.go
      webhooks.go

Keep provider interfaces consumer-owned and narrow. Avoid giant interfaces designed around every
method in an SDK.

### Decisions

- module and minimum Go version;
- HTTP transport ownership;
- generated versus handwritten client;
- SQL and migration approach;
- worker and retry model;
- error wrapping and retry classification.

### Verification

Use formatting, vet, repository static analysis, race-sensitive tests where concurrency matters,
unit tests, HTTP fixture tests, integration tests, and binary smoke tests.

## Java

### Good fit

Enterprise products, mature service estates, strong transaction needs, JVM operations, and
customer environments standardized on Spring or related frameworks.

### Framework patterns

- Spring Boot configuration properties and profiles;
- controller, service, repository, scheduled worker, and message-listener boundaries;
- SecurityFilterChain and method authorization;
- Jakarta validation;
- Testcontainers or equivalent integration proof when the repository already permits it.

### Decisions

- Java, Spring, Maven or Gradle versions;
- servlet versus reactive stack;
- transaction and outbox boundaries;
- identity and security integration;
- JSON and generated-client conventions;
- queue and workflow runtime.

### Verification

Compile, static analysis, unit tests, slice tests, integration tests, migration tests, and provider
contract fixtures. Avoid mixing blocking SDKs into reactive paths without an explicit boundary.

## .NET

### Good fit

Microsoft-centric enterprise estates, Azure deployments, Graph integrations, and applications
already using ASP.NET Core.

### Framework patterns

- Minimal APIs or controllers based on the target;
- options validation;
- authentication and authorization policies;
- HttpClientFactory with named or typed clients;
- hosted services for workers;
- Entity Framework transactions and migrations when established.

### Decisions

- target framework;
- nullable and analyzer settings;
- controller versus minimal API convention;
- identity library and token cache;
- queue or worker host;
- JSON source generation and API client approach.

### Verification

Run formatting or analyzer gates, build, unit tests, integration tests, authorization tests,
provider fixtures, and publish smoke tests for the actual runtime target.

## Ruby

### Good fit

Existing Rails products, customer workflows, CRUD-heavy operational applications, and provider
integrations that fit the product's current job system.

### Framework patterns

- Rails engines or namespaces for bounded capabilities;
- Active Job with the repository's queue adapter;
- Active Record scopes plus database isolation;
- service objects only where they clarify transactional or provider boundaries;
- request specs and job specs.

### Decisions

- Ruby and Rails versions;
- Bundler and lockfile;
- Active Job adapter;
- tenancy pattern;
- HTTP client and retry behavior;
- serializer and validation approach.

### Verification

Run RuboCop or repository style gate, unit and request tests, job tests, migration tests, provider
fixtures, and boot checks. Default scopes alone are a fragile tenant boundary.

## Rust

### Good fit

Performance-sensitive services, agents, gateways, event processors, and environments that value a
small static runtime and explicit types.

### Framework patterns

- Axum state and extractor boundaries;
- tower middleware for tracing, auth, timeouts, and limits;
- serde types for external and internal payloads;
- sqlx or repository-established database layer;
- Tokio cancellation and task ownership.

### Decisions

- compiler and edition;
- async runtime;
- HTTP and TLS stack;
- database compile-time verification requirements;
- error surface;
- generated API client approach.

### Verification

Run formatting, Clippy with project policy, tests, integration fixtures, database checks, and
release-build smoke tests. Model unknown external fields and provider errors deliberately rather
than relying on exhaustive enums that break on additive changes.

## Other stacks

For PHP, Kotlin, Swift, Elixir, Clojure, C++, or another target:

1. Record the exact language and framework in application.other_language and framework.
2. Inspect the repository's established extension point.
3. Map every shared adapter contract explicitly.
4. Research authoritative framework and protocol libraries.
5. Add a language profile only after tests cover its package workflow and verification commands.
6. Keep SCAFFOLD_PLAN language_profile null until the catalog contains a reviewed profile.

Do not relabel another profile as "close enough."

## Repository mapping

Before proposing files, build a mapping:

| Logical module | Existing location | Existing convention | Proposed change |
| --- | --- | --- | --- |
| provider client | unknown | unknown | open decision |
| tenant context | middleware | request scoped | extend current context |
| event inbox | data layer | transactional repository | new repository and migration |

Check:

- public versus internal modules;
- dependency direction;
- shared schema ownership;
- migration and generated-file rules;
- test placement;
- logger and telemetry conventions;
- configuration and secret resolution;
- whether a separate service is actually necessary.

## Verification matrix

Every adapter should eventually prove:

| Layer | Proof |
| --- | --- |
| Parse and validation | malformed, additive, missing, and boundary payload fixtures |
| Authentication | valid, absent, expired, revoked, rotated, and wrong-scope credentials |
| Authorization | tenant, object, property, function, provider-connection, and admin boundaries |
| Provider behavior | pagination, limits, partial failure, timeouts, unknown outcome, and drift |
| Persistence | transactions, idempotency, checkpoints, correction, and recovery |
| Async work | replay, ordering, cancellation, poison input, and worker restart |
| Operations | telemetry, health, alert path, runbook, and safe diagnostics |
| Deployment | build, configuration failure, migration, readiness, rollback, and teardown |

Use real provider or environment proof only when authorized. Label fixtures, sandboxes, staging,
and production evidence accurately.
