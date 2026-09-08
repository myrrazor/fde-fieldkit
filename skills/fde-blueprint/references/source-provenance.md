# Source provenance and reuse

## Contents

1. Why provenance is a gate
2. Research sources
3. Product documentation
4. Open-source review
5. Code adaptation
6. License and notices
7. Security and maintenance
8. Local portfolio sources
9. Evidence record
10. Stop conditions

## Why provenance is a gate

The blueprint catalog can point to existing standards, services, and open-source projects, but a
useful idea is not automatically safe or authorized to reuse.

Provenance answers:

- where the design or code came from;
- which exact version was inspected;
- what license and terms apply;
- what was copied, adapted, or merely referenced;
- whether it is maintained and secure enough for the task;
- which notices and obligations travel with it;
- which tests prove the adapted result.

Without that record, later agents cannot distinguish original work, compatible implementation,
licensed adaptation, and accidental copying.

## Research sources

Prefer:

1. Published standard or specification.
2. Official product or API documentation.
3. Official source repository.
4. Exact official license file.
5. Official security and release policy.
6. Maintainer release notes.
7. Package registry metadata linked to official source.

Use third-party articles only for discovery or independent operational context. Do not use them as
the sole source for protocol, license, security, or current product claims.

For current technical claims, re-check the source. A catalog research date is not permanent truth.

## Product documentation

Record:

- product and exact feature;
- documentation URL;
- documentation or API version;
- checked date;
- plan or edition dependency if stated;
- region or deployment model if relevant;
- auth and scope requirements;
- deprecation or migration notices;
- inference separated from documented fact.

Do not quote large passages. Summarize the contract and preserve a direct link.

Marketing pages may establish that a product exists. Use technical documentation for behavior and
official terms for licensing or procurement boundaries.

## Open-source review

Before selection inspect:

- canonical repository and owner;
- exact commit, tag, or release;
- root and file-level licenses;
- contribution or trademark restrictions relevant to distribution;
- source directories and generated artifacts;
- dependency locks and vendored code;
- release cadence;
- supported versions;
- security policy and advisories;
- open critical maintenance signals;
- test suite and CI;
- architecture and operational footprint.

A repository badge or popularity count is not enough.

### Exact revision

Pin a commit or immutable release artifact. Branch names move. Raw file URLs to a branch are useful
for current research but insufficient provenance for copied code.

### File-level boundary

Mixed-license repositories can separate community and enterprise code. Generated SDKs may carry
different notices. Examples, assets, models, fonts, and fixtures can have their own terms. Record
the exact paths considered.

## Code adaptation

Classify every use:

- no reuse: learned only from public behavior or a standard;
- conceptual reference: architecture idea with original implementation;
- API integration: calls product through documented interface;
- dependency: uses released package unchanged;
- adaptation: modifies reviewed source;
- vendoring: incorporates source substantially unchanged;
- generated code: produced from a specification or official generator.

For adaptation or vendoring record:

- upstream revision;
- source file paths;
- destination paths;
- transformation summary;
- retained copyright and notices;
- local tests;
- future update responsibility.

Use the smallest necessary adaptation. Do not copy an entire connector framework to obtain one
OAuth helper.

### Clean implementation from a standard

Implementing a public standard independently still requires:

- specification version;
- conformance interpretation;
- compatible libraries;
- protocol security review;
- test vectors;
- interoperability proof.

Do not copy a reference implementation unless its license and provenance are separately approved.

## License and notices

### Permissive

Usually allows broad use with attribution or notice obligations, but check:

- exact license text;
- copyright notices;
- NOTICE files;
- patent clauses;
- trademarks;
- dependency licenses;
- distribution form.

### Weak copyleft

MPL and similar terms can apply at file level. Understand modification and distribution obligations
for exact files.

### Strong or network copyleft

GPL or AGPL can trigger reciprocal obligations depending on use and distribution. Stop for explicit
owner or legal review before adaptation or selection when relevant.

### Source-available

Do not label as open source. Review use restrictions, competitive use, production grants, managed
service terms, and change date where applicable.

### Commercial

Documentation access does not grant API, SDK, data, or production rights. Confirm approved account,
terms, procurement, scopes, and data processing.

### Mixed

Review feature and directory boundaries. An MIT root does not necessarily cover enterprise
components, and a commercial edition may include source under different terms.

## Security and maintenance

Review:

- security policy;
- supported versions;
- advisories and response;
- release signing or provenance;
- dependency posture;
- privilege and network requirements;
- secret handling;
- telemetry defaults;
- update and rollback.

OpenSSF Scorecard can provide signals, not a verdict. A project can be well maintained and still
be wrong for the customer's trust boundary.

Check whether the project is:

- active;
- feature complete with security-only maintenance;
- in maintenance mode;
- deprecated;
- archived;
- transferred;
- forked after a license change.

Represent maintenance-only projects honestly in the catalog.

## Local portfolio sources

Existing local projects can become candidates only when the user authorizes inspection and the
source is mature enough to extract.

Before extraction:

1. Identify the real git root and exact revision.
2. Check worktree cleanliness and preserve user changes.
3. Read repository policy.
4. Find the smallest coherent kernel and public contract.
5. Run current tests at the inspected revision.
6. Check whether credentials, customer data, private business logic, or proprietary assets are
   entangled.
7. Review ownership and intended reuse.
8. Extract through a separate authorized work package.

Do not copy from a dirty, unverified project into the shared toolkit. Historical proof logs do not
close the gap.

### Extraction shape

A good extracted kernel has:

- explicit inputs and outputs;
- no hidden project globals;
- no customer-specific constants;
- deterministic dry run;
- machine-readable errors;
- tests with safe fixtures;
- source and license record;
- adapter boundary for the original project.

If those conditions are absent, use the project as conceptual reference only.

## Evidence record

For each selected source, keep:

    source:
      name: example
      upstream_url: https://example.invalid/repository
      revision: immutable commit or release
      source_paths:
        - path/to/file
      use: conceptual-reference
      license:
        id: Apache-2.0
        url: https://example.invalid/license
        reviewed_by: owner or reviewer
      notices:
        - retained notice path
      security_review:
        date: owner-supplied review date
        result: pending
      local_destination:
        - planned/path
      tests:
        - pending command and artifact

This example is structural. Do not copy its placeholder URL or invent reviewer and date values.

The initial blueprint SOURCES.md records only selected catalog provenance and reuse policy. A later
implementation provenance manifest should be machine-readable and tied to exact source files.

## Stop conditions

Stop before reuse when:

- canonical source cannot be identified;
- license is absent, ambiguous, or conflicts with intended use;
- enterprise and community boundaries are unclear;
- exact revision cannot be pinned;
- source contains credentials or customer data;
- current worktree is dirty and extraction would mix changes;
- tests do not establish the relevant behavior;
- project is archived or maintenance-only and no owner accepts that risk;
- required legal, security, procurement, or data-egress approval is missing;
- adaptation would expand beyond the task contract.

Record the blocker and choose a clean-room implementation, another candidate, or an explicit owner
decision. Do not route around the gate.
