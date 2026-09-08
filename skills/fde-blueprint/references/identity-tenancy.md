# Identity and tenancy

## Contents

1. Trust model
2. Tenant model
3. Authorization
4. Enterprise SSO
5. SCIM lifecycle
6. Product patterns
7. Data and jobs
8. Administrative access
9. Migration
10. Test matrix

## Trust model

Authentication establishes an identity through a trusted mechanism. Authorization decides what
that identity may do in a specific tenant and context. Tenant selection, organization membership,
role, entitlement, and provider connection are separate decisions.

Never authorize solely from:

- a client-supplied tenant or organization ID;
- email domain;
- unverified token claims;
- a UI-hidden control;
- a default ORM scope;
- a provider object ID without local ownership lookup;
- a support role without an explicit audited elevation.

Resolve trusted context server-side from the authenticated principal and current membership or a
narrow, signed machine identity.

## Tenant model

Define the tenant unit:

- customer account;
- organization;
- workspace;
- project;
- environment;
- legal entity;
- nested combination.

Then define whether users can belong to several tenants and how the active tenant is selected.
Model stable internal IDs separately from customer domains, provider organization IDs, slugs, and
display names.

### Storage patterns

Common patterns include:

- shared tables with tenant columns and scoped repositories;
- database row-level security;
- schema per tenant;
- database per tenant;
- account or namespace per tenant in external stores;
- hybrid isolation based on data class or customer contract.

No one pattern covers every store. Inventory database, object storage, cache, queue, search,
vector, analytics, logs, metrics, backups, exports, and support artifacts.

### Context propagation

Tenant context should enter:

- request context;
- authorization policy;
- repository and query;
- transaction;
- job payload and worker context;
- cache key;
- object path;
- vector namespace and filter;
- provider connection lookup;
- log, trace, and metric attributes;
- audit event.

Reject work when context is absent or ambiguous. Do not fall back to a "default" tenant in shared
runtime code.

## Authorization

Define:

- subjects: users, service accounts, API keys, support operators, workflows;
- resources: organizations, records, files, connections, jobs, settings, reports;
- actions: read, create, update, delete, export, administer, impersonate, replay;
- context: tenant, environment, ownership, classification, state, time;
- policy authority and change workflow.

Test the API against object-level, property-level, and function-level authorization. A user who can
read a record may not be allowed to read every field, export it, or trigger a privileged action.

Roles are bundles of permissions, not authorization logic. Keep permission checks close to the
operation and data boundary.

## Enterprise SSO

### Connection discovery

Discovery may use:

- verified domain;
- organization slug entered by the user;
- explicit invitation;
- provider or connection ID from a trusted link;
- admin-configured routing.

Discovery chooses a login connection. It does not prove membership.

### OIDC and OAuth

Decide:

- authorization code flow;
- PKCE use;
- state and nonce storage;
- redirect allowlist;
- issuer and audience;
- signature algorithm and key rotation;
- clock handling based on library and owner policy;
- requested scopes;
- user-info use;
- logout and session revocation;
- account linking.

Use a maintained library. Do not hand-roll JWT signature or protocol validation.

### SAML

Decide:

- service-provider or IdP initiation;
- entity IDs and assertion consumer URLs;
- signed response and assertion expectations;
- issuer, audience, destination, recipient, time, and InResponseTo validation;
- encrypted assertions;
- certificate rotation and metadata refresh;
- NameID and attribute mapping;
- logout support;
- organization binding.

SAML parsing and signature wrapping defenses belong in a reviewed library and integration tests.

### Managed versus direct

Managed brokers such as WorkOS or Auth0 can normalize enterprise connections and directory sync,
but introduce a managed data path, commercial terms, and provider dependency. Direct Okta,
Microsoft Entra, or other IdP integration preserves a narrower dependency but increases protocol
and customer-configuration burden.

Self-hosted platforms such as Keycloak change the operating model. Catalog license classes and
reuse modes must be reviewed before selecting source code or a deployment.

## SCIM lifecycle

SCIM is an HTTP provisioning protocol, not merely user CRUD.

### Resources

Decide support for:

- Users;
- Groups;
- group membership;
- enterprise user extension;
- custom schemas;
- ServiceProviderConfig;
- ResourceTypes;
- Schemas.

### Operations

Cover:

- create;
- retrieve;
- replace;
- patch;
- delete or deactivate;
- filter;
- pagination;
- sorting if claimed;
- bulk if claimed.

Return SCIM media types and error shapes where required. Preserve provider identifiers and local
mapping independently.

### Ownership

Choose whether SCIM owns:

- user existence;
- active status;
- profile attributes;
- group membership;
- application role;
- organization membership.

Do not let JIT login silently reactivate a directory-deactivated user if the directory is the
lifecycle authority.

### Reconciliation

Plan for duplicate create, reordered update, unknown user, changed email, renamed group, membership
before user creation, provider retry, partial failure, and resync. Deactivation should block access
before destructive cleanup.

## Product patterns

### Managed enterprise identity

Candidates include WorkOS and Auth0. Compare required protocols, organization model, directory
sync, admin portal, data residency, SDK language, audit behavior, and contract.

### Customer identity providers

Okta and Microsoft Entra are common conformance targets. Customer setup documentation and tested
configuration matrices matter as much as callback code.

### Self-hosted identity

Keycloak, authentik, ZITADEL, SuperTokens, Logto, and Ory components cover different layers.
Identity provider, OAuth authorization server, application auth, proxy, and user management are
not interchangeable categories. Inspect exact feature and license scope.

## Data and jobs

Apply tenant and identity rules to:

- refresh tokens and credential references;
- SSO transactions;
- sessions;
- invitations;
- membership sync;
- webhook and directory events;
- reconciliation jobs;
- audit events;
- support exports.

Encrypt or isolate sensitive token material using an approved secret system. Ordinary records
should contain references and non-secret metadata.

A queued job must carry a trusted tenant and connection reference. The worker must revalidate that
the tenant, connection, and actor or service authority remain active before privileged effects.

## Administrative access

Design:

- break-glass login independent of customer IdP failure;
- support role eligibility;
- explicit tenant selection;
- reason and duration;
- approval if required by owner policy;
- visible customer notification where intended;
- comprehensive audit;
- revocation and session termination.

Do not create an invisible global-admin bypass. Test administrative reads, writes, exports,
impersonation, and provider actions separately.

## Migration

When adding SSO or tenancy to an existing product:

1. Inventory current identities, accounts, domains, memberships, and provider connections.
2. Define deterministic organization mapping.
3. Resolve duplicate emails and shared domains.
4. Decide account-linking proof.
5. Backfill tenant IDs and validate every store.
6. Introduce server-side scope before enabling customer access.
7. Rehearse rollback without reopening cross-tenant paths.
8. Preserve an audited break-glass route.
9. Reconcile IdP and directory state after cutover.

Never infer organization membership solely from historic email domain.

## Test matrix

### Authentication

- valid login;
- wrong issuer, audience, destination, recipient, or organization;
- expired, future, replayed, or malformed response;
- state and nonce mismatch;
- key or certificate rotation;
- denied consent;
- account link conflict;
- deactivated user.

### Provisioning

- Users and Groups happy paths;
- duplicate create;
- patch variants;
- filter and pagination;
- deactivate and reactivate;
- group membership ordering;
- extension attributes;
- retry and reconciliation;
- invalid bearer credential;
- tenant-bound credential isolation.

### Tenant authorization

- guessed object ID;
- list enumeration;
- field-level secret;
- privileged function;
- cache collision;
- job replay;
- file and search access;
- vector filter;
- export and deletion;
- support and break-glass paths.

Passing one layer does not prove the others.
