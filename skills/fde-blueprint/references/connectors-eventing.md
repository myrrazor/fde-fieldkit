# Connectors and eventing

## Contents

1. Connector contract
2. Build versus platform
3. Authentication methods
4. Provider lifecycle
5. Data synchronization
6. Actions and reconciliation
7. Webhook ingestion
8. Outbound webhooks
9. Events and queues
10. Provider notes
11. Test and evidence matrix

## Connector contract

A connector is more than an HTTP client. It owns:

- connection identity and tenant binding;
- credential reference and lifecycle;
- supported operations and scopes;
- provider-native schemas;
- normalized application schemas;
- pagination and checkpoints;
- rate limits and retry classification;
- idempotency and reconciliation;
- observability and support diagnostics;
- deletion and disconnect behavior.

Publish a capability matrix. Mark unsupported operations explicitly.

## Build versus platform

### Direct adapter

Prefer when:

- only a small number of deep integrations are required;
- provider-specific behavior is a product differentiator;
- data must avoid an integration intermediary;
- the team can own auth, drift, retries, and support;
- a mature official SDK or simple API exists.

### Unified API

Candidates such as Merge can reduce normalized API work across a category. Verify whether the
normalized surface exposes every required provider feature and how native escape hatches, data
storage, regional processing, webhooks, and commercial terms work.

### Auth and connector platform

Nango, Composio, Paragon, and Pipedream occupy different points between auth broker, connector
runtime, action catalog, workflow, and managed execution. Compare actual operations rather than
the label "integration platform."

### Data movement platform

Airbyte and Meltano/Singer focus on source and destination movement. They may fit bulk sync better
than interactive actions. Review connector licensing, runtime ownership, state protocol,
normalization, and customer deployment constraints.

Open source does not erase operating cost, security review, or license obligations.

## Authentication methods

### OAuth authorization code

Model:

- tenant and connection intent before redirect;
- state and PKCE transaction;
- exact redirect URI;
- least scopes;
- consent denial;
- token exchange;
- refresh rotation;
- revocation;
- reconnect;
- provider installation or account identity.

Keep refresh concurrency safe. A provider that rotates refresh tokens can invalidate concurrent
refreshes unless the update is serialized.

### API keys and tokens

Validate format without logging the value. Store in an approved secret system, retain only a
reference in application records, test revocation, and document customer rotation.

### Service accounts and key pairs

Decide who creates and rotates the identity, what resource or tenant it can access, and whether
workload identity can replace a long-lived key.

### App installation

GitHub Apps, Slack apps, Shopify apps, and similar ecosystems bind credentials to an installation,
workspace, shop, or organization. Map provider identity to the local tenant explicitly and handle
uninstall events.

### Delegated versus app-only

Microsoft Graph and Google APIs often distinguish user-delegated and application authority.
Choose based on the operation and customer policy. Do not request application-wide authority to
avoid implementing user consent.

## Provider lifecycle

Use a connection state model such as:

- pending setup;
- active;
- degraded;
- reauthorization required;
- revoked;
- disconnected;
- deleting.

State transitions should derive from verified events and API outcomes. Store:

- tenant;
- provider;
- provider account or installation ID;
- credential reference;
- granted scopes;
- creation and verification metadata;
- last successful operation;
- checkpoint references;
- webhook subscription identifiers;
- current health and actionable reason.

Do not treat an untested stored credential as active.

## Data synchronization

### Native boundary

Preserve provider-native fields in versioned types or raw archival where policy permits. Normalize
only what the application actually consumes. This makes provider drift diagnosable without
letting raw payloads leak through the product.

### Pagination

Test:

- cursor, token, link, offset, and page-number modes;
- empty page with next token;
- repeated token;
- changing collection during scan;
- provider maximum page size;
- expired cursor;
- partial page failure.

Never assume one page means complete.

### Checkpoints

A checkpoint should identify tenant, connection, object stream, version, and provider cursor or
watermark. Write it transactionally with durable effects where possible. If that is impossible,
design replay and reconciliation.

### Backfill and incremental

Separate:

- initial backfill;
- incremental polling;
- event-triggered refresh;
- explicit resync;
- deletion scan;
- repair.

Backfills need bounded resource behavior set by platform evidence or owner requirements, not
invented constants.

### Schema drift

Expect additive fields, new enum values, nullable changes, deleted fields, versioned endpoints,
and provider-specific extensions. Fail visibly on incompatible meaning, but tolerate safe additive
data.

## Actions and reconciliation

For each write action define:

- local command identity;
- provider idempotency support;
- local idempotency key;
- request and response record;
- timeout outcome;
- retry-safe and retry-unsafe errors;
- provider object mapping;
- reconciliation lookup;
- compensation or manual repair.

A timeout after sending may be an unknown outcome, not a failed action. Blind retry can duplicate
effects.

## Webhook ingestion

### Receive

Preserve the raw body and signature-relevant headers. Enforce transport and size policy before
expensive parsing.

### Verify

Use the provider or Standard Webhooks scheme exactly:

- secret selection and rotation;
- signature algorithm;
- signed content construction;
- timestamp or replay rule;
- constant-time comparison where applicable.

Never parse and reserialize before verifying a signature over raw bytes.

### Persist

After verification, persist an inbox record with:

- provider event ID or deterministic digest;
- tenant and connection;
- event type and version;
- received metadata;
- raw or safely transformed payload per policy;
- processing status.

### Acknowledge

Acknowledge only after reaching the selected durability boundary. Synchronous business processing
can make provider retry behavior unpredictable.

### Process

Handlers must be idempotent. Separate unknown event type, invalid contract, transient dependency,
permanent business rejection, and poison payload.

### Replay

Authorize replay narrowly, preserve the original event identity, record who replayed it and why,
and prevent replay from bypassing idempotency by default.

Svix and Hookdeck are candidate managed or self-hosted webhook infrastructure. Standard Webhooks
is a specification and library ecosystem. These are different selections.

## Outbound webhooks

Model:

- tenant-owned endpoint and subscriptions;
- endpoint verification if required;
- signing key reference and rotation;
- event envelope and version;
- delivery attempt;
- response status and safe excerpt;
- retry state;
- disable and re-enable;
- replay.

Protect against server-side request forgery:

- validate schemes;
- resolve and evaluate destinations according to approved network policy;
- handle DNS changes;
- block local or metadata endpoints when required;
- control redirects;
- apply egress policy;
- revalidate on changes.

Do not log authorization headers, signing secrets, or sensitive payloads.

## Events and queues

CloudEvents can standardize event envelopes. AsyncAPI can document event channels and schemas.
Neither supplies durability.

Queue and workflow candidates include:

- Amazon SQS;
- Google Pub/Sub;
- Azure Service Bus;
- Apache Kafka;
- NATS JetStream;
- RabbitMQ;
- Temporal;
- cloud event buses such as EventBridge.

Select from required semantics:

- delivery model;
- ordering unit;
- replay and retention;
- dedupe support;
- transaction or outbox integration;
- scheduled work;
- long-running workflow and human steps;
- customer deployment boundary;
- operating ownership.

Assume at-least-once effects unless an end-to-end contract proves otherwise. Broker guarantees do
not remove application idempotency.

## Provider notes

### Slack

OAuth installation, workspace identity, scopes, Events API verification, retries, and uninstall
must map to one connection lifecycle.

### Microsoft Graph

Choose delegated or application permissions, tenant consent, token cache, throttling, pagination,
delta queries, subscriptions, renewal, and validation tokens deliberately.

### Google APIs

Choose user OAuth, service account, domain-wide delegation, or workload identity based on
authority. Scope verification and refresh-token behavior vary by application status and policy.

### GitHub Apps

Model app, installation, repository selection, installation token expiry, webhook delivery, and
permission changes. Do not substitute a personal access token for the app lifecycle.

### Salesforce

Account for org identity, OAuth policy, object permissions, API limits, bulk APIs, cursors, and
schema customization.

### HubSpot

Model private or public app choice, scopes, CRM paging, association schemas, webhooks, and app
uninstall.

### Jira and Atlassian

Prefer current OAuth 2.0 authorization code guidance for new cloud integrations. Track Atlassian's
platform transitions rather than starting a deprecated app model.

### ServiceNow and Zendesk

Separate customer instance identity, OAuth or token administration, object permissions, rate
limits, audit expectations, and custom fields.

### Shopify

Model shop identity, install or token exchange, offline versus online authority, API version,
webhooks, uninstall, and mandatory privacy topics.

### Linear

Use OAuth and PKCE where applicable, model workspace identity and actor type, handle GraphQL
errors, webhooks, and OAuth application actor semantics.

### Snowflake

Choose OAuth, key-pair, workload identity, or customer-established auth. Record role, warehouse,
database, schema, network, query, and result handling separately.

## Test and evidence matrix

Prove:

- setup, denial, callback, exchange, refresh, rotation, revocation, reconnect, disconnect;
- least scopes and wrong-scope failure;
- tenant and provider-account binding;
- pagination and checkpoint resume;
- rate limit and provider outage;
- malformed and additive responses;
- partial batch failure;
- unknown write outcome and reconciliation;
- signed webhook, forgery, replay, duplicate, ordering, and poison input;
- queue redelivery and worker restart;
- deletion and uninstall;
- safe logging and support diagnostics.

Retain sanitized fixtures, exact provider documentation revision or date, test output, and—when
authorized—sandbox or live configuration evidence. Do not record credential values.
