# Netwatch interface direction

Netwatch uses a source-first control room. The visual language extends Fieldkit's
evidence-sheet system: warm paper, dark utility rail, near-black ink, thin rules, compact
monospace metadata, and tables that carry the visual weight. It should feel like a field
instrument, not a generic security operations center.

## Product-specific thesis

The arrival question is **who connected, where, and how?** The strongest answer is the
destination evidence itself, followed by the capture path and policy outcome that make the
count meaningful.

The signature element is the **coverage lane**. It stays in the navigation rail and appears
again in session detail and diagnostics. It keeps proxy coverage, attach-only evidence, TLS
opacity, and known blind spots visible before a user interprets zero or low totals.

## Information architecture

Five durable views sit in a stable rail:

1. **Overview** compares all saved evidence by agent, capture source, destination, and
   session.
2. **Live traffic** inspects one selected session through destination, raw-event,
   tool-action, and coverage tabs.
3. **Agents & capture** discovers processes, starts noninteractive argv commands, builds a
   terminal command, and starts attachment.
4. **Policies** edits the one managed policy and explains destination decisions.
5. **Diagnostics** states the available integrations, evidence path, privacy contract, and
   platform limits.

The session selector and freshness state remain stable above every view. Deep links retain
the selected session in the query string and the current view in the hash.

## Hierarchy and units

1. Coverage and local-control state.
2. Current source/session context and freshness.
3. Exceptions: blocked, would-block, failed, and private/local access.
4. Destination groups and their capture units.
5. Raw records, tool actions, policy detail, and diagnostics.

Cross-session totals say **records**, never **calls**. HTTP forward records are requests;
CONNECT and SOCKS records are tunnel attempts; `lsof` records are deduplicated socket
observations. Tool actions occupy a separate table because correlation is not established.

Counts use tabular numerals. Service, raw hostname, port, protocol, network scope, capture
path, decision, and timing remain readable as text. Service identification is labelled as a
local hostname inference.

## Visual system

- Warm paper is the working surface; white panels mark interaction boundaries.
- The dark rail carries navigation and the persistent coverage boundary.
- Rust is reserved for selection and primary action, not decoration.
- Green means allowed/observed/complete, amber means would-block/interrupted, blue means
  starting/running, and red means blocked/failed/unsupported.
- Every semantic color is paired with a status word.
- Rules and alignment do more grouping work than cards, shadows, or empty space.
- Monospace is used for identifiers, endpoints, commands, paths, and changing numbers, not
  for long explanatory copy.

There are no decorative gradients, threat gauges, confidence scores, neon topology maps,
glass panels, generic shields, or fabricated live metrics.

## Interaction model

Overview destinations and selected-session destinations can prefill allow or deny rules.
That action is intentionally staged: open policy, review the selectors, add the draft, and
save. Copy states say that the change is for future runs and leaves existing tunnels alone.

The policy editor keeps unsaved work visibly dirty. Add, edit, move, delete, import, and
export happen in the browser draft; server validation is authoritative before an import is
accepted and again on save. A malformed managed file does not lock the user out: the surface
keeps Import available so a valid draft can repair it. The decision simulator selects audit
or enforce mode and reports matched rule, outcome, and network scope for every resolved
address.

Stop is enabled only for operations owned by the current server process. Delete is enabled
only for stopped sessions and requires confirmation. JSON and CSV remain ordinary download
links because exports do not mutate local evidence.

Interactive agents keep their native terminal. The dashboard's run form is labelled for
noninteractive argv work and provides a copyable terminal command instead of simulating a
terminal it does not have.

## States

State is written in the surface, not hidden in a transient toast:

- local controls ready or read-only evidence;
- local API unavailable, loading, refreshing, or current;
- no sessions, no selected session, no destinations, no matching filters, no tool actions,
  and no detected agents;
- starting, running, complete, interrupted, and failed sessions;
- empty, starter, saved, dirty, imported, invalid, and checked policy states;
- unsupported capture operation and resolution failure;
- stop ownership conflict and destructive delete confirmation; and
- weaker agent integration or partial capture coverage.

## Responsive behavior

Wide screens use a fixed rail, sticky command bar, side-by-side evidence breakdowns, and
dense ledgers. Medium screens collapse the two-column evidence and form panels. Compact
screens turn the rail into horizontal navigation, stack forms and actions, reduce the
summary strip to two columns, and hide lower-priority table fields while preserving source,
destination, records, and outcome.

Tables may scroll horizontally where the comparison genuinely needs it. The surrounding
page does not. Buttons grow to the mobile quality target and destructive actions retain
their labels.

## Accessibility and motion

- A skip link reaches the workspace.
- Navigation, tabs, forms, and table columns have semantic names.
- Evidence tabs use a single tab stop with Arrow, Home, and End keyboard movement.
- Keyboard focus remains visible.
- Status never relies on color alone.
- Loading and mutation feedback use persistent text and live regions.
- Reduced-motion preference removes nonessential transitions.
- The interface performs no decorative animation; running evidence refreshes quietly.

Stored values are escaped before entering dynamic markup. The page applies a restrictive
Content Security Policy and a no-referrer policy. Content that Netwatch does not store,
including prompts, headers, bodies, queries, and full commands, has no place in the
interface.
