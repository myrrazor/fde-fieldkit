# Screen brief — Netwatch control room

**Primary user:** A developer or FDE inspecting repeated coding-agent runs on a local Mac.

**Frequency:** Repeated during an engagement or security review; density and keyboard fluency
matter more than landing-page spectacle.

**Global arrival question:** Who connected, where, and how?

**Persistent context:** Coverage lane, local-control state, session selector, evidence
freshness, and local database path.

## Overview

**Question:** What happened across the evidence I have saved?

**Primary actions:** Start a capture, edit the managed policy, or open a session.

**Content:** Saved/running session totals, captured records, blocked records, identified
services, relayed bytes, capture-source breakdown, agent breakdown, cross-session
destinations, and newest-first sessions.

**Truth rule:** Mixed data is called records. Requests, tunnels, and socket observations are
never flattened into “calls.” Service names are labelled as local hostname identification.

## Live traffic

**Question:** Where did this selected session connect, and what did policy do?

**Primary actions:** Filter evidence, export JSON/CSV, prefill an allow/deny rule, stop an
owned running session, or delete stopped evidence.

**Tabs:** Destinations, raw events, tool actions, and coverage.

**Filters:** Destination/service search, decision, capture source, and network scope.

**Truth rule:** Tool actions remain a separate lane and are not presented as causes of
network records. Attach rows remain socket observations. CONNECT/SOCKS rows remain tunnels.

## Agents & capture

**Question:** Which process should Netwatch supervise or observe?

**Primary actions:** Start a noninteractive argv command, copy a terminal-owned interactive
agent command, or attach to a PID.

**Run fields:** Command/arguments, integration, audit/enforce mode, and saved-policy use.

**Attach fields:** Root PID, sample interval, and follow mode. Detected Codex and Claude roots
can prefill the PID. Arguments are always labelled redacted.

**Truth rule:** The dashboard is not a PTY. Interactive Codex and Claude sessions keep their
terminal. Attachment cannot block, count requests, or see sockets between samples.

## Policies

**Question:** What will happen to the next connection attempt in a future run?

**Primary actions:** Add/edit/move/delete rule drafts, change the default, import/export JSON,
save the managed policy, and simulate a destination.

**Recovery:** A malformed managed file leaves Import enabled. The server validates an
imported draft without saving it, so the user can review the repaired policy before Save.

**Simulator:** Select audit or enforce and show a separate matched-rule outcome and scope for
every resolved address.

**Rule fields:** Stable ID, allow/deny, hosts, IP/CIDR, ports, protocols, private-network
permission, and reason.

**Truth rule:** Quick Allow/Deny only prefills a draft. Unsaved changes are not active. Saved
changes apply to future runs and do not reload running proxies or close existing tunnels.

## Diagnostics

**Question:** What can this machine and this browser prove?

**Content:** Platform, HTTP/CONNECT, SOCKS5, `lsof`, Codex, Claude Code, evidence path, TLS
opacity, UDP/QUIC absence, direct-socket bypass, and the signed Network Extension boundary.

**Truth rule:** Diagnostics inspect local capabilities only and do not call vendor APIs.

## Layout

**Wide:** Dark persistent rail, sticky session command bar, six-cell summary strips,
side-by-side breakdowns, full ledgers, and adjacent capture/policy work panels.

**Medium:** Horizontal navigation replaces the side rail; two-column content collapses while
tables preserve their comparison structure.

**Compact:** Controls and forms stack, summary strips use two columns, action groups wrap, and
lower-priority fields such as byte totals, rule detail, resolved IP, and long command text
yield before source, destination, record count, and outcome.

## Required states

- direct loopback controls available;
- read-only evidence because controls are locked;
- local API unavailable;
- initial loading, manual refresh, and quiet running-session polling;
- no sessions and no selected session;
- no captured destinations, no matching filters, no tool actions, and no detected agents;
- starting, running, complete, interrupted, and failed sessions;
- stronger Codex/Claude integration and proxy-environment fallback;
- attach one-shot, attach follow, process gone, and `lsof` unavailable;
- unsaved starter, saved policy, dirty draft, malformed-file repair, import success/failure,
  validation failure, audit/enforce selection, and multi-address decision results;
- unsupported SOCKS operation, failed DNS resolution, blocked, would-block, observed, and
  allowed records;
- stop unavailable because another process owns the session;
- stopped-session delete confirmation and failure; and
- long hostnames, paths, IDs, high counts, many records, keyboard focus, text scaling, and
  reduced motion.

## Safety copy that remains visible

- Run mode covers only traffic routed through its local proxies.
- HTTPS paths and bodies stay encrypted unless a supported hook reports a sanitized target.
- Attachment is observation-only and can miss short-lived sockets.
- DNS, UDP/QUIC, and proxy-bypassing direct sockets are not captured.
- Universal macOS enforcement needs a separately signed Network Extension.
- Policy edits affect future supervised runs, not existing tunnels.

The exhaustive shipped behavior and API are documented in [`SPEC.md`](SPEC.md).
