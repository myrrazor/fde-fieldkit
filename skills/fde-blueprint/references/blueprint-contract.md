# Blueprint contract

## Contents

1. Contract layers
2. Answers format
3. Normalized blueprint
4. Scaffold plan
5. Evidence manifest
6. Markdown packet
7. Determinism
8. Validation
9. Versioning
10. Consumer rules

## Contract layers

The system separates four things that are often blurred together:

1. Interview answers: customer decisions and repository-discovered facts.
2. Blueprint: normalized scope, products, invariants, acceptance, and provenance.
3. Scaffold plan: modules a future language adapter may generate.
4. Evidence manifest: claims that remain pending until implementation proves them.

The Markdown files are human views. blueprint.json is the authoritative decision contract.

## Answers format

Answers are a nested JSON object. Keys follow the answer_path values in
assets/questionnaire.json. A minimal renderable file looks like:

    {
      "engagement": {
        "project_name": "Acme support connector",
        "mode": "existing",
        "business_outcome": "Support agents see current CRM context in one workflow",
        "repository_path": "./services/support"
      },
      "capabilities": [
        "connector-pack",
        "webhook-engine"
      ],
      "application": {
        "primary_language": "typescript",
        "framework": "Fastify"
      }
    }

This is intentionally incomplete. The renderer preserves active required omissions as open
decisions. An interactive interview should normally produce a much fuller file.

### Answer value rules

- text and choice values are strings;
- multi_choice and multi_text values are arrays of strings;
- choice values must match declared choices exactly;
- missing means unknown or not yet answered;
- an empty string or empty list does not count as an answer;
- false and zero remain legitimate values if a future schema introduces boolean or numeric types;
- no comments or trailing commas are allowed because this is JSON, not JSON5.

### Answer ownership

Repository discovery may establish stack, current architecture, and existing mechanisms. Owners
must establish outcome, acceptance, contract, risk, procurement, and intentional changes. Keep
this distinction in working notes even though both normalize into answers.

## Normalized blueprint

assets/blueprint.schema.json declares the complete top-level shape.

### schema_version

Version of the normalized contract, currently 1.0. It is independent of the catalog and question
bank versions so those assets can evolve without breaking packet consumers.

### project

Contains:

- name;
- engagement_mode;
- business_outcome;
- repository_path or null;
- primary_language;
- framework.

When primary_language is other, the normalized value comes from application.other_language.

### capabilities

Ordered list of selected pack IDs. Order is preserved because it can express the user's preferred
delivery sequence. Consumers must not silently add a pack.

### answers

The original normalized interview object. This retains detailed decisions that are not promoted
to top-level fields and lets future generators consume new answer paths without redesigning the
whole contract.

### selected_products

Only exact catalog IDs found in answers appear here. Each entry carries:

- ID and display name;
- categories and delivery model;
- license class;
- reuse mode;
- primary-source URLs.

Free-text product names remain in answers but cannot acquire catalog provenance automatically.
Resolve them to a reviewed catalog entry before implementation.

### scaffold_plan

One item per selected capability:

- capability;
- title;
- outcome;
- modules.

Modules describe implementation boundaries, not guaranteed files. A language adapter must map
them to the target repository's conventions.

### security_invariants

Statements that must remain true across design, implementation, and operations. These are stronger
than general advice. Later work should turn each applicable invariant into one or more tests,
policy checks, runtime controls, or retained inspections.

### acceptance_criteria

Behavioral exit conditions grouped by capability. An implementation task can refine criteria with
owner-supplied limits, but must not weaken or mark them complete without evidence.

### evidence

Every item includes:

- deterministic ID;
- capability;
- requested artifact;
- status fixed to pending at blueprint time;
- proof_command initially null;
- artifact_path initially null.

The blueprint generator has no transition that marks evidence passed.

### open_decisions

Active, required interview questions without answers. Each preserves question ID, answer path,
prompt, and required status. Consumers must surface these rather than default them.

### provenance

Carries:

- catalog version;
- catalog research date;
- generator identity;
- source reuse policy.

This is not a software bill of materials. It records the research basis for decisions.

## Scaffold plan

SCAFFOLD_PLAN.json is the stable handoff for future generators. It includes:

- schema version;
- normalized project;
- exact language profile when known;
- capability packages;
- explicit plan-only generator boundary.

A future adapter may add a versioned expansion phase such as:

    blueprint.json
      -> language adapter
      -> repository-aware file plan
      -> dry-run diff
      -> approved source changes
      -> verification
      -> evidence update

It must not re-interview the user for decisions already in blueprint.json. It may ask only for new
decisions introduced by the implementation environment.

## Evidence manifest

EVIDENCE_MANIFEST.json is designed for later controlled updates. The initial manifest:

- contains all requested artifacts;
- has only pending statuses;
- carries no invented command;
- carries no invented artifact path;
- states the claim boundary.

A later evidence tool should record exact revision, environment, command, exit code, result,
artifact checksum, redaction state, and reviewer. That extension needs its own schema and review.

## Markdown packet

### BLUEPRINT.md

Executive view of outcome, scope, products, non-goals, open decisions, and the claim boundary.

### ARCHITECTURE.md

Planning view of application context, modules, trust flow, cross-cutting contracts, and deployment
context. Its Mermaid diagram is a hypothesis until checked against the target.

### SECURITY.md

Data and security decisions, non-negotiable invariants, threat exercises, secret handling, and
supply-chain gate.

### IMPLEMENTATION_PLAN.md

Dependency-aware packages with modules and exit evidence. It avoids fabricated schedules and
capacity limits.

### ACCEPTANCE.md

Behavioral criteria and pending evidence inventory. This is not a passed test report.

### SOURCES.md

Exact provenance for selected catalog products plus license and reuse boundaries.

## Determinism

The same:

- answer bytes after JSON parsing;
- question bank;
- capability packs;
- catalog;
- templates;
- generator version

must produce identical packet bytes.

Therefore the generator excludes:

- current timestamps;
- random identifiers;
- machine paths other than user-supplied output references;
- environment probes;
- network results;
- unstable dictionary iteration;
- inferred repository state.

JSON keys are sorted and evidence IDs derive from pack order, artifact order, and artifact text.

## Validation

Exit code 2 means input or command usage is malformed. Exit code 3 means structurally valid JSON
does not satisfy the answer or blueprint contract. Exit code 4 means the requested write is unsafe
or failed.

Answer validation checks:

- minimum render fields;
- known capabilities;
- declared answer types;
- declared choices;
- active required omissions for open decision reporting.

Blueprint validation checks:

- required top-level fields;
- schema version;
- known, non-empty capabilities;
- evidence list shape;
- pending-only status;
- unique evidence IDs.

The bundled checker is deliberately dependency-free. Any later strict JSON Schema integration
must agree with assets/blueprint.schema.json and retain the same behavioral tests.

## Versioning

Change schema_version only for a contract change that existing consumers cannot safely interpret.
Additive catalog entries and new source research normally change catalog_version. Question routing
changes should update questionnaire schema_version when their consumer contract changes.

Never mutate a published interpretation while retaining its version. Preserve fixtures that prove
the old and new behavior when consumers exist.

## Consumer rules

Consumers must:

- use blueprint.json, not scrape Markdown;
- reject unsupported schema versions;
- preserve capability and module ordering;
- surface open decisions;
- honor repository policy and source reuse mode;
- dry-run planned files before writes;
- refuse overwrite by default;
- keep secrets out of generated source and packets;
- never transform pending evidence into passed evidence;
- report generated, tested, deployed, and live-verified states separately.
