# RAG, data, and privacy

## Contents

1. Security model
2. Source and permission ingestion
3. Parsing and provenance
4. Classification and redaction
5. Embeddings and stores
6. Retrieval authorization
7. Generation and citations
8. Deletion and lifecycle
9. Product patterns
10. Evaluation and evidence

## Security model

A secure retrieval system must preserve authorization from source through answer. The pipeline is:

    source identity and ACL
      -> ingestion
      -> parse and classify
      -> chunk and embed
      -> index with tenant and ACL
      -> authorization-filtered retrieval
      -> citation assembly
      -> generation
      -> output policy and audit

Every arrow is a trust or data boundary. Post-filtering retrieved results is insufficient because
unauthorized content may already have entered ranking, logs, caches, traces, or the model prompt.

Treat source content as untrusted. It can contain prompt injection, malicious markup, encoded
payloads, misleading instructions, secrets, or content the current user cannot access.

## Source and permission ingestion

For each source define:

- tenant and provider connection;
- stable source object ID;
- source version or modification marker;
- container, project, channel, drive, repository, or folder;
- authoritative ACL or membership source;
- inherited versus direct permissions;
- link-sharing semantics;
- deletion and tombstone signal;
- rate and backfill behavior;
- supported content types and size boundaries from evidence.

Permission ingestion and content ingestion must reconcile. If ACL refresh fails, choose a
fail-closed behavior rather than serving stale broad access.

### Identity mapping

Map source principals to local subjects:

- exact provider user or group ID;
- local user or group;
- organization or tenant;
- unresolved or external principal.

Email can assist mapping but is not stable authorization. Preserve unmapped permissions and
exclude those documents until resolution when fail-closed behavior is required.

## Parsing and provenance

Each document and chunk should carry:

- tenant;
- connection;
- source system;
- source object and version;
- canonical URL where safe;
- title and content type;
- parser and parser version;
- chunk strategy version;
- source offsets or page information;
- ACL identifiers;
- data classification;
- created, modified, ingested, and deleted markers as supplied by source;
- content hash where policy permits.

Do not put secret values into debug provenance. Separate searchable metadata from restricted audit
metadata.

### Parser choices

Unstructured and similar libraries can support many document forms, but parser coverage, external
service use, native dependencies, OCR, tables, images, and licensing must be reviewed. A parser
that silently drops tables or permissions can produce convincing but unsafe results.

### Chunking

Choose chunking from content structure and retrieval evaluation. Record overlap, hierarchy, and
version as decisions only when owner requirements or measured evidence support them. Do not invent
universal token counts.

## Classification and redaction

### Policy before detector

Define:

- data classes;
- jurisdictions and customer contracts;
- where each class may be stored or processed;
- allowed model and embedding providers;
- detect, transform, block, quarantine, or review action;
- reversible versus irreversible handling;
- audit and retention.

Then choose detectors.

### Structured data

Use declared schemas and field policy where possible. Validate nested objects, arrays, free-form
maps, attachments, headers, and metadata. Structured identifiers can become sensitive in
combination even if no regex detects them.

### Unstructured data

Candidates include:

- Microsoft Presidio for local or extensible detection and anonymization;
- Google Sensitive Data Protection;
- AWS Comprehend PII;
- Azure AI Language PII;
- custom deterministic rules;
- domain classifiers and human review.

Managed DLP products introduce data egress, region, retention, contract, and cost decisions.
Local libraries introduce model, language, deployment, tuning, and maintenance decisions.

### Secrets

detect-secrets and Gitleaks are candidates for repository or text secret detection. Secret
scanning is distinct from PII detection. Check current maintenance posture and supported use
before selecting a tool for a new foundation.

### Transformation

Actions include:

- fixed mask;
- partial mask;
- format-preserving token;
- deterministic pseudonym;
- keyed hash;
- encryption;
- deletion;
- quarantine;
- block.

Reversible transforms require key ownership, access control, rotation, and incident planning.
Deterministic transforms can leak equality and frequency. State the tradeoff.

## Embeddings and stores

### Embedding boundary

Decide:

- local or managed model;
- content and metadata sent;
- tenant isolation;
- region and retention;
- model and dimensionality;
- version changes and re-embedding;
- truncation and unsupported language behavior;
- batch and failure semantics.

Embedding is data processing, not an anonymous mathematical operation.

### PostgreSQL and pgvector

Useful when relational authority, transactions, and row-level security already live in
PostgreSQL. Verify query plans, index choice, metadata filters, tenant policies, and operational
scale with actual workload evidence.

### Qdrant

Supports collection, payload, and filtering patterns. Decide shared versus per-tenant collection
based on required isolation and operating scale. Apply tenant and ACL filters in the query.

### Pinecone

Managed namespaces can isolate tenant data logically. Confirm namespace behavior, metadata
filtering, deletion, region, project/account boundaries, and contract.

### Weaviate and Milvus

Self-hosted or managed vector systems change operations and tenancy design. Verify authorization,
collection boundaries, backup, restore, upgrade, and deletion rather than relying on query filters
alone.

### OpenSearch and Azure AI Search

Useful for hybrid lexical and vector retrieval. Azure AI Search security trimming patterns and
OpenSearch document-level controls require exact configuration and query proof.

The catalog entry is a candidate record, not a scale claim.

## Retrieval authorization

Build the query from trusted context:

- tenant;
- current subject;
- current groups and roles;
- allowed source connections;
- document ACL;
- classification and purpose restrictions;
- current source version and deletion state.

Apply these constraints before candidates return. If the store cannot express the required policy
safely, choose a different isolation boundary or store.

### Cache

Cache keys must include tenant, identity or policy version, query, retrieval configuration, and
source/index version as needed. A shared semantic cache can become a cross-tenant leak.

### Ranking

Rerankers and model-based filters see candidate content. Include them in the data-flow and provider
review. Do not send unauthorized candidates to an external reranker.

## Generation and citations

The generator should receive:

- explicit system policy;
- user request;
- authorized source excerpts;
- stable citation identifiers;
- clear separation between instructions and untrusted content;
- tool and output constraints.

Require citations that map to retrieved source/version/offset records. A model-produced URL without
that mapping is not provenance.

Handle:

- no authorized evidence;
- conflicting evidence;
- stale evidence;
- incomplete coverage;
- source deletion between retrieval and response;
- requested output containing sensitive values.

The correct response may be refusal, uncertainty, or a request for access.

## Deletion and lifecycle

Deletion must reach:

- raw source cache;
- parsed document;
- chunks;
- embeddings;
- lexical index;
- query and answer caches;
- evaluation datasets;
- logs and traces according to policy;
- backups according to declared lifecycle.

Keep tombstones or audit facts only where policy permits. Reconciliation should detect documents
that vanished without a deletion event.

On permission removal, block retrieval before asynchronous physical cleanup.

## Product patterns

LlamaIndex and LangChain can provide orchestration and integrations. They do not supply tenant
authorization by default. Review their exact modules, transitive dependencies, callback and
telemetry behavior, and abstraction escape hatches.

Provider-managed vector and model services reduce infrastructure operations but add contractual
and egress decisions. Self-hosted systems preserve more control but add security patching, backup,
scaling, and incident ownership.

Use standards and narrow interfaces at the boundary:

- document and chunk records;
- embedding adapter;
- index adapter;
- authorization filter;
- retriever;
- citation assembler;
- evaluation case.

Do not let a framework-specific document type become the product's enduring data contract.

## Evaluation and evidence

Create a safe evaluation set with:

- allowed and denied documents for several tenants and roles;
- stale and changed ACLs;
- deleted and superseded versions;
- direct and indirect prompt injection;
- sensitive and encoded content;
- multilingual and structured content in scope;
- no-answer cases;
- conflicting sources;
- citation checks;
- retrieval relevance cases.

Measure only owner-approved or task-derived thresholds. Report raw metrics without turning an
arbitrary target into a release gate.

Required evidence should include:

- data-flow and provider inventory;
- tenant and ACL query tests;
- deletion propagation test;
- redaction evaluation;
- prompt-injection exercise;
- citation-to-source verification;
- safe logs and traces;
- exact model, parser, embedding, index, and policy versions.

Synthetic evaluation proves controlled cases. It does not prove current customer permissions or
production effectiveness.
