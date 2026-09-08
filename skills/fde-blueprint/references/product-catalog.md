# Product catalog guide

## Contents

1. Purpose
2. Catalog fields
3. License classes
4. Reuse modes
5. Selection method
6. Category map
7. Managed versus self-hosted
8. Standards
9. Staleness
10. Adding an entry

## Purpose

assets/catalog.json is a researched decision index for products, open-source projects, standards,
provider APIs, and implementation patterns. It helps an agent ask informed questions and preserve
source provenance.

It is not:

- a procurement approval;
- legal advice;
- dependency approval;
- a claim of current availability;
- a benchmark;
- permission to copy code;
- proof that an integration works.

Every selected candidate still needs target-specific verification.

## Catalog fields

### id

Stable machine identifier used in questionnaire choices and selected_products. Rename only through
a contract version change.

### name

Current human-readable project or product name.

### categories

Searchable capabilities and roles. A product may span several categories, but category overlap
does not imply feature equivalence.

### delivery

Examples:

- managed;
- self-hosted;
- self-hosted-or-managed;
- library;
- standard;
- provider API;
- local implementation pattern.

Review the exact entry because delivery labels are descriptive rather than a closed enum.

### license_class and license_id

license_class groups decision behavior. license_id records the researched license or commercial
status. Exact files, editions, releases, plugins, and enterprise directories can differ.

### reuse

Machine-readable boundary describing whether to implement a standard, inspect and adapt after
review, integrate by API, use as reference only, stop for owner review, or avoid for new
foundations without an explicit reason.

### methods

Protocols, interfaces, or capability methods. This is a navigation aid, not a conformance claim.

### fit

Short decision-oriented description. It should name where the candidate may fit without marketing
language.

### sources

Primary documentation, repository, specification, or license sources with checked date and review
status. A status of cataloged means enough was verified to index the candidate; reviewed means the
specific claim and boundary received closer inspection. Neither means approved.

## License classes

### Standard

An open specification or interoperability standard. The standard may have intellectual-property
terms, and implementations have their own licenses.

Examples in the catalog include CloudEvents, AsyncAPI, SLSA, CycloneDX, and SPDX.

### Permissive

An open-source license such as Apache-2.0, MIT, or BSD-3-Clause. Preserve notices and inspect exact
source, dependencies, trademarks, patents, and generated artifacts before adapting.

Examples include Keycloak, Meltano Singer SDK, Standard Webhooks, Temporal, OpenTofu,
OpenTelemetry, OpenMeter, and Kill Bill.

### Copyleft

An open-source license with reciprocal obligations such as AGPL-3.0. Network use, modification,
distribution, and combined work questions require owner or legal review.

Examples include ZITADEL and Lago in the researched catalog.

### Source-available

Source can be inspected but use, competition, embedding, hosting, or redistribution may be
restricted. Do not call it open source.

Examples include current covered Terraform releases, Vault releases, and n8n's sustainable-use
model.

### Commercial

Proprietary managed service or API. Integrate only with an approved customer account, contract,
scopes, data flow, and operating model.

### Mixed

Different directories, editions, features, or releases carry different terms. Review exact files
and intended use. authentik, Infisical, Windmill, and PostHog illustrate why a repository-level
label may be insufficient.

## Reuse modes

### implement-standard

Implement the published contract or select a separately reviewed compatible library. Standards do
not grant permission to copy one implementation.

### inspect-and-adapt

Potential source reuse after exact revision, file, license, notice, dependency, maintenance,
security, and test review. Adapt the smallest necessary part and preserve provenance.

### integrate-via-api

Use official API or SDK through an approved account. Review credentials, scopes, rate limits,
data processing, retention, regions, and contract.

### reference-only

Learn architecture or user experience. Do not copy source into the scaffold.

### owner-review

Stop before selection or adaptation. This is common for copyleft, mixed-license, or consequential
source-available choices.

### maintenance-only

Support an existing dependency if necessary, but do not select it for a new foundation without
an explicit owner-backed reason. Current Gitleaks maintenance posture is represented this way in
the catalog research.

## Selection method

For each capability:

1. Write the required operations and invariants.
2. Record target language, deployment, network, data, and team constraints.
3. Filter candidates by actual category and method.
4. Compare build, managed, self-hosted, and standard-only paths.
5. Verify current primary documentation for finalists.
6. Inspect license and source boundary.
7. Map data flow, credentials, tenant isolation, and operating ownership.
8. Test the riskiest unknown with a safe fixture or sandbox when authorized.
9. Record the selected exact ID or preserve an open decision.

Do not begin with a preferred vendor and reverse-engineer requirements around it.

## Category map

### Identity

Managed brokers and identity products:

- WorkOS;
- Auth0;
- Okta;
- Microsoft Entra.

Self-hosted or application identity candidates:

- Keycloak;
- Ory Hydra;
- authentik;
- SuperTokens;
- Logto;
- ZITADEL.

Differentiate IdP, federation broker, OAuth server, app-auth library, user management, SCIM client,
and directory sync.

### Connector platforms

- Nango;
- Airbyte;
- Meltano Singer SDK;
- Composio;
- Merge;
- Pipedream.

Differentiate auth broker, unified API, ELT connector, action catalog, workflow, and hosted
execution.

### Webhooks and event standards

- Standard Webhooks;
- Svix;
- Hookdeck;
- CloudEvents;
- AsyncAPI.

Specifications, libraries, managed delivery, ingress observability, and event contracts are
separate choices.

### Queues and workflows

- Temporal;
- Amazon SQS;
- Google Pub/Sub;
- Azure Service Bus;
- Apache Kafka;
- NATS JetStream;
- RabbitMQ;
- Valkey;
- AWS EventBridge.

Compare durability, ordering, replay, workflow semantics, deployment, and operations.

### RAG and search

Stores:

- pgvector;
- Qdrant;
- Pinecone;
- Weaviate;
- Milvus;
- OpenSearch;
- Azure AI Search.

Frameworks and parsing:

- LlamaIndex;
- LangChain;
- Unstructured.

Framework selection never replaces retrieval authorization.

### Privacy and secret detection

- Microsoft Presidio;
- Google Sensitive Data Protection;
- AWS Comprehend;
- Azure AI Language PII;
- detect-secrets;
- Gitleaks.

Compare local versus managed processing, languages, entity coverage, transformation, data egress,
maintenance, and evaluation.

### Deployment and secrets

- Docker Compose;
- Kubernetes;
- Helm;
- K3s;
- OpenTofu;
- Terraform;
- Pulumi;
- SOPS;
- Vault;
- Infisical;
- External Secrets Operator.

Track current license and exact operating boundary.

### Operations and analytics

- OpenTelemetry;
- Sentry;
- PagerDuty;
- PostHog;
- Apache Superset.

Telemetry, error monitoring, paging, product analytics, and BI are distinct.

### Billing

- Stripe Billing;
- OpenMeter;
- Lago;
- Kill Bill.

The questionnaire also lists managed candidates such as Metronome and Orb. Add full catalog
entries before automatic selected-product provenance is expected.

### Workflow automation

- n8n;
- Windmill;
- Kestra;
- Dagster;
- Prefect.

Match workflow type and operating model, not feature count.

### Provider APIs

- Slack;
- Microsoft Graph;
- Google APIs;
- GitHub Apps;
- Salesforce;
- HubSpot;
- Jira;
- ServiceNow;
- Zendesk;
- Shopify;
- Linear;
- Snowflake;
- AWS EventBridge.

These entries describe the provider integration boundary, not reusable connector source.

### Supply chain

- SLSA;
- OpenSSF Scorecard;
- CycloneDX;
- SPDX;
- Sigstore.

These are standards and tools used to generate or assess evidence.

## Managed versus self-hosted

Compare the complete responsibility model.

Managed service:

- vendor operates core service;
- customer still owns configuration, identities, scopes, integration, monitoring, contract, and
  incident coordination;
- introduces external data path and availability dependency.

Self-hosted:

- customer or product team owns capacity, security updates, backup, restore, upgrades, telemetry,
  availability, and incident response;
- may improve deployment control;
- does not automatically improve security or cost.

Embedded library:

- runs in application process;
- affects dependency and release lifecycle;
- may simplify operation;
- increases blast radius and compatibility coupling.

Standard:

- improves interoperability;
- requires an implementation and conformance proof;
- does not operate anything.

## Staleness

Products, docs, pricing, SDKs, APIs, licenses, and maintenance status change. Treat researched_on
as a warning label.

Refresh an entry when:

- selecting it for a real implementation;
- its license or ownership changed;
- official docs moved;
- a provider deprecated an auth or app model;
- a major version changes behavior;
- maintenance status is uncertain;
- data handling or region claims matter.

Use current primary sources. Record the date. Clearly label inference.

## Adding an entry

An entry is ready when:

- ID is unique and stable;
- categories match real function;
- delivery is accurate;
- license class and ID have a primary source;
- reuse mode follows the license and intended use;
- methods avoid unverified marketing claims;
- fit is concise and comparative;
- every source uses HTTPS;
- checked date is current research;
- status reflects review depth;
- questionnaire IDs match when the product is a declared choice;
- catalog integrity tests pass.

Do not add a product solely to make the catalog look broad.
