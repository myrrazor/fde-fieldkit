# Netwatch product and behavior specification

This document describes the behavior shipped by `fieldkit-netwatch` 0.2.0. Anything in
the final **Future work** section is deliberately not presented as a current capability.

## Product contract

Netwatch answers two questions:

1. Where did this supervised agent or process connect?
2. What did the selected destination policy allow, block, or mark as `would_block`?

It is a local metadata recorder and policy-enforcing proxy, not a packet sniffer. The
strong path is to start a command through Netwatch. Attachment to an already-running
process is a weaker, observation-only socket inventory.

The dashboard is a local control room over the same SQLite evidence and policy engine as
the CLI. It can inspect all saved sessions, launch noninteractive commands, attach to
running processes, edit the managed policy, explain policy decisions, stop operations it
started, delete stopped evidence, and export a session as JSON or CSV.

## Install and launch

Install the core, the plugin, and then start the web hub:

```bash
fieldkit plugin add netwatch
fieldkit netwatch doctor
fieldkit serve
```

`fieldkit serve` binds `127.0.0.1` only (no `--host`). It prefers port 8765 and
picks a free port if that one is taken; `--port N` pins N. The command prints
the URL. Open `/netwatch/` on that URL. Netwatch mutation controls unlock only
for a direct loopback request whose host is also loopback.

From this repository:

```bash
uv sync
uv run fieldkit serve
```

### Interactive coding agents stay in their terminal

The dashboard's **Supervise a command** form starts a direct argv process without a
shell. It is useful for noninteractive commands. It is not a browser terminal.

Interactive Codex and Claude Code sessions should be started in their own terminal:

```bash
fieldkit netwatch run -- codex
fieldkit netwatch run -- claude
```

The **Agents & capture** view builds and copies the equivalent terminal command from its
current mode, integration, policy, and argv fields. A terminal-started session appears in
the dashboard when the CLI and web server use the same evidence database.

## Evidence model and units

A session is one supervised command or one process-attachment window. Session states
currently written by Netwatch are `starting`, `running`, `complete`, `failed`, and
`interrupted`.

The word **record** is the safe cross-source total. Individual capture paths have
different units:

| Capture source | What one network record means | What it does not mean |
| --- | --- | --- |
| `http-forward` | One plaintext HTTP proxy request | A packet or browser action |
| `http-connect` | One HTTPS CONNECT tunnel attempt | An HTTPS request or decrypted URL |
| `socks5` | One SOCKS5 TCP CONNECT attempt | SOCKS BIND, UDP, or a request inside the tunnel |
| `lsof` | One unique established TCP socket observation for an attach session | A request count or a complete history |

Tool actions are stored separately from network records. They come from supported agent
hooks and are not claimed as the cause of a nearby connection.

An **agent source** is the session's integration class: `codex`, `claude`, `generic`, or
`attached-process`. A **capture source** is the transport path in the table above. A
**service** is a local hostname-suffix identification such as OpenAI API, Anthropic API,
GitHub, npm, or PyPI. Unknown services fall back to a hostname label. Service names are
helpful local heuristics, not verified ownership data.

Byte totals count application bytes relayed through Netwatch. They are not Ethernet/IP
packet sizes and do not include all protocol overhead.

## Shipped capture behavior

### Supervised run

`fieldkit netwatch run -- COMMAND...` does the following:

1. Creates a session in SQLite with only the executable retained. All command arguments
   are replaced with `[arguments redacted]` in evidence.
2. Starts HTTP and SOCKS5 listeners on OS-selected ports bound to `127.0.0.1`.
3. Prepares an invocation-local agent integration and proxy environment.
4. Starts the command with argv execution, not shell interpolation.
5. Records policy decisions and metadata for traffic that reaches either proxy.
6. Closes the proxies and marks the session when the command exits or supervision is
   cancelled.

Every command receives upper- and lower-case `HTTP_PROXY`, `HTTPS_PROXY`, `ALL_PROXY`,
and empty `NO_PROXY` variables. `ALL_PROXY` uses `socks5h://`, so compatible clients send
hostnames to the SOCKS proxy for resolution.

### HTTP and HTTPS

- Plain HTTP/1.x proxy requests retain method, normalized destination, and a sanitized
  path. Query strings and fragments are removed before storage.
- HTTPS uses CONNECT. Netwatch sees the destination host, resolved IP, port, decision,
  timing, and tunnel byte totals. It does not see HTTPS paths, headers, or bodies.
- Request and response content passes through memory while being relayed but is never
  written to Netwatch evidence.
- Ambiguous HTTP framing is rejected: multiple content lengths, content length combined
  with transfer encoding, and unsupported transfer encodings are not forwarded.

### SOCKS5

- The listener accepts unauthenticated SOCKS5 on loopback only.
- TCP CONNECT is supported for IPv4, IPv6, and hostnames.
- SOCKS BIND and UDP are rejected and recorded as unsupported.

### Policy timing

In enforce mode, a denied destination is recorded and refused before Netwatch opens an
upstream socket. In audit mode, the same decision is recorded as `would_block` and the
connection is allowed to continue.

If DNS returns several addresses and any candidate is denied, Netwatch does not select a
different address to bypass that denial.

## Agent integrations

### Codex

Netwatch checks `codex features list`. When the installed build exposes
`network_proxy`, Netwatch adds an invocation-local `-c` configuration that enables the
Codex sandbox proxy and chains it through Netwatch. If the feature is unavailable, proxy
environment variables remain active and the weaker coverage is recorded on the session.

An existing user-supplied `network_proxy` override is left unchanged and labelled.

### Claude Code

Claude Code 2.1.219 or newer receives an invocation-only settings file with:

- fail-closed sandboxing;
- unsandboxed commands disabled;
- Netwatch's HTTP and SOCKS ports;
- strict network allowlist handoff;
- local binding allowed; and
- a PreToolUse metadata hook.

If the command already supplies `--settings`, Netwatch reads and merges that value into a
private temporary copy. The original file is never edited. Older Claude Code versions
keep the proxy environment but are labelled as weaker coverage.

The hook stores event name, tool name, correlation ID, and a sanitized target. WebFetch
URLs lose user information, query, fragment, and credential-shaped path segments.
WebSearch queries and Bash commands are replaced with fixed redaction labels. Other tool
input is not persisted.

### Generic commands

Generic commands receive the proxy environment. They can still bypass Netwatch if they
ignore those variables or open direct sockets.

### Discovery

`fieldkit netwatch agents` and `GET /api/netwatch/agents` inspect the local process table
for Codex and Claude roots. Child duplicates and known GUI helper processes are filtered.
The executable is shown; arguments are replaced with an explicit redaction label.

## Process attachment

`fieldkit netwatch attach PID` and the dashboard attachment form use `lsof` to sample
established TCP sockets for the requested PID and descendants visible in the process
table.

- A one-shot attachment takes one sample and completes.
- Follow mode repeats until stopped or until sampling fails.
- A fingerprint made from PID, local endpoint, and remote endpoint deduplicates repeated
  observations in the same session.
- Attachment never installs a proxy, changes the target process, or enforces a policy.
- It can miss connections that open and close between samples.
- It cannot recover request paths, byte totals, failed attempts, DNS traffic, UDP, or
  QUIC.

The dashboard defaults to follow mode and exposes the sampling interval. The API rejects
intervals below 0.1 seconds.

## Destination policy

Policies are versioned JSON:

```json
{
  "version": 1,
  "default": "deny",
  "rules": [
    {
      "id": "openai-api",
      "action": "allow",
      "hosts": ["api.openai.com"],
      "ports": [443],
      "protocols": ["https"],
      "note": "model API"
    }
  ]
}
```

Each rule has a unique non-empty ID and an `allow` or `deny` action. It may contain:

- `hosts`: exact hosts or the documented wildcard forms;
- `ips`: IP addresses or CIDR ranges;
- `ports`: integers from 1 through 65535;
- `protocols`: `http`, `https`, or `tcp`;
- `allow_private`: explicit permission for a matching allow rule to reach a restricted
  network scope; and
- `note`: human context for the rule.

Configured categories combine with AND. Values inside one category are alternatives.
Deny wins when matching allow and deny rules conflict. The first matching rule of the
winning action supplies the reported rule ID.

Host matching is intentionally small:

| Pattern | Meaning |
| --- | --- |
| `api.example.com` | Exact host only |
| `*.example.com` | Subdomains, not the apex |
| `**.example.com` | Apex and subdomains |
| `*` | Every hostname |

Loopback, private, link-local, multicast, and reserved destinations require a matching
allow rule with `allow_private: true`, even when the policy default is allow.

### CLI policy workflow

```bash
fieldkit netwatch policy init policy.json
fieldkit netwatch policy add policy.json \
  --action allow --id openai-api --host api.openai.com --port 443 --protocol https
fieldkit netwatch policy check policy.json https://api.openai.com
fieldkit netwatch run --mode enforce --policy policy.json -- codex
```

`policy init` writes the loopback-only starter and refuses to replace an existing file
unless `--force` is supplied. `policy add` appends a fully validated rule. `policy check`
may resolve the requested hostname, explains every address internally, and reports the
selected deny-first outcome without opening an application connection.

### Dashboard-managed policy

The dashboard manages one policy file. Its path is:

1. `FIELDKIT_NETWATCH_POLICY`, when set; otherwise
2. `netwatch-policy.json` beside the active evidence database.

When the file does not exist, the UI opens an unsaved deny-by-default starter that allows
loopback. The editor can change the default, add/edit/delete/reorder rules, import JSON,
export the current draft, save a fully validated policy, and simulate a destination.
Policy writes use a private temporary file, fsync, mode `0600`, and atomic replacement;
symlinked targets are refused.

The control token is issued independently of policy parsing. If the managed file is
malformed, the dashboard stays usable, explains the read error, and can replace it through
Import. Imported drafts are normalized by server-side validation without writing the file;
Save remains the only persistent policy mutation.

Allow and deny actions beside an observed destination only prefill a rule draft. The user
must add the rule and save the policy.

**Saved policy changes apply to future supervised runs.** A running proxy keeps the
policy object it loaded at startup. Editing the managed file does not reload that proxy
and does not close an existing tunnel.

Dashboard enforce mode refuses to start until the managed policy has been saved. Audit
mode can either use the saved policy and record `would_block`, or use the built-in
allow-all audit policy.

## Dashboard behavior

The control room has five durable views and a session selector that remains available
across them.

### Overview

- all-session totals for saved sessions, running sessions, captured records, blocked
  records, identified services, and relayed bytes;
- breakdown by agent source and capture source;
- destinations aggregated across sessions, with agent and capture-source labels;
- quick allow/deny rule drafts; and
- a newest-first session ledger.

The overview intentionally uses **records**, not **calls**, because its totals can mix
HTTP requests, tunnels, and socket observations.

### Live traffic

- session state, agent, mode, PID, executable, timestamps, exit code, and totals;
- destination groups with sanitized paths, protocol/scope, record count, outcome, bytes,
  and first/last timestamps;
- raw network records with capture source, destination, decision, rule, resolved IP,
  bytes, and explanation;
- tool-action records in a separate tab;
- per-session coverage paths, proxy addresses, and policy path at startup;
- destination/service search, decision and scope filters for grouped destinations, and
  capture-source filtering for raw network records;
- JSON and CSV downloads;
- stop for a running operation owned by the current web-server process; and
- deletion for stopped session evidence after confirmation.

Running selected sessions refresh by polling the current complete report every two
seconds. This is polling, not an event stream.

### Agents & capture

- start a direct argv command for noninteractive work;
- choose auto, Codex, Claude Code, or generic integration;
- choose audit or enforce mode;
- choose whether an audit run evaluates the saved policy;
- generate and copy the equivalent terminal command;
- discover running Codex and Claude roots; and
- start one-shot or follow attachment by PID.

The command parser supports whitespace, single and double quotes, and backslash escapes.
The server receives an argv list and never invokes a shell.

### Policies

- managed policy save state and exact local path;
- default action;
- ordered rule table;
- add, edit, move, and delete rule drafts;
- JSON import and export;
- full server-side validation on save; and
- audit or enforce destination simulation with one result for every resolved address,
  including the matched rule and network scope.

### Diagnostics

- platform information;
- HTTP/CONNECT, SOCKS5, and `lsof` availability;
- Codex and Claude integration strength;
- evidence database path; and
- explicit TLS, UDP/QUIC, direct-socket, and whole-machine limits.

Diagnostics inspect local executables and features. They do not contact vendor APIs.

## Web API

The plugin is mounted under `/api/netwatch`.

### Read routes

| Method and path | Shipped response |
| --- | --- |
| `GET /status` | Platform, capture features, agent integrations, DB path, and whether this request can use controls |
| `GET /control` | Per-process control token and managed policy path; direct loopback only |
| `GET /overview` | Cross-session totals grouped by agent, capture source, and destination |
| `GET /agents` | Discovered Codex and Claude roots with redacted arguments |
| `GET /sessions` | Newest-first sessions, DB path, and IDs owned by this server |
| `GET /sessions/{id}` | Session, totals, grouped destinations, raw network records, and tool records |
| `GET /sessions/{id}/export.json` | Complete metadata-only report download |
| `GET /sessions/{id}/export.csv` | Labelled network/tool ledger download |
| `GET /policy/starter` | Deny-by-default loopback starter document |
| `GET /policy` | Managed policy path, save state, and policy document |

### Control routes

| Method and path | JSON request | Result |
| --- | --- | --- |
| `POST /runs` | `command`, `mode`, `agent`, `use_policy` | Starts a background supervised argv process and returns its ready session with HTTP 202 |
| `POST /attachments` | `pid`, `follow`, `interval` | Starts a one-shot or background socket observation with HTTP 202 |
| `POST /sessions/{id}/stop` | `{}` | Cancels a run/attachment owned by this server and returns the session |
| `DELETE /sessions/{id}` | `{}` | Deletes a stopped session and cascades its evidence |
| `PUT /policy` | Full policy v1 document | Validates and replaces the managed policy |
| `POST /policy/validate` | Full policy v1 document | Validates and normalizes a draft without writing it |
| `POST /policy/check` | `destination`, `protocol`, `mode` | Resolves and explains the managed-policy decision |

Control requests require all of the following:

- the browser client address and request host are loopback;
- same-origin `Origin`/`Referer` when either header is present;
- `Sec-Fetch-Site` absent, `none`, or `same-origin`;
- `Content-Type: application/json`; and
- the per-process token in `X-Fieldkit-Control`.

The token is generated when the plugin module loads and issued only by `/control` to a
direct loopback request. It is not stored in SQLite or a policy file.

Read-only evidence routes do not require this token. `fieldkit serve` always binds
loopback; the host is not configurable. Remote browsers cannot reach the dashboard
or obtain Netwatch controls.

## Session ownership and deletion

The dashboard can stop only operations launched by the current Fieldkit application
instance. CLI-owned runs and operations from an earlier server process remain visible but
are not controllable through its Stop button. Separate Fieldkit app instances own and shut
down their work independently, even when they run inside the same Python process.

Stopping a dashboard-owned supervised run cancels supervision and terminates its process
group. One-shot and follow attachments are owned while their sampling work is active.
Stopping either waits for an in-flight snapshot to finish before marking the session
interrupted, so background work cannot write more evidence after Stop reports completion.
Application shutdown applies the same cleanup to every operation that instance owns.

The current ownership map is in memory and is not reconstructed after a server restart.
Deletion is allowed only after a session has left `starting` or `running`; deleting the
session also deletes its network and tool records through SQLite foreign keys.

## Reports and stored fields

Session reports contain:

- session ID, timestamps, status, mode, agent class, redacted command, root PID, active
  coverage labels, policy path, proxy addresses, exit code, and note;
- totals for allowed, observed, blocked, would-block, failed, public, local/private,
  services, tool events, and bytes;
- destination groups keyed by service, host, port, protocol, and scope; and
- full ordered network and tool record arrays.

JSON export mirrors this report. CSV is one ledger with a `record_type` column so network
records and tool records stay distinguishable. String cells that spreadsheet applications
could interpret as formulas are prefixed with an apostrophe. Empty fields do not imply
that encrypted or redacted content was collected.

## Privacy and local security boundary

### Stored locally

- executable name and agent class;
- session timing, status, mode, PID, coverage, and policy path;
- destination host, resolved IP, port, protocol, IP scope, and local service label;
- capture source, plaintext HTTP method, sanitized plaintext path, decision, matching
  rule, explanation, timing, and relayed byte totals;
- attach PID/process name and deduplication fingerprint; and
- sanitized supported-hook metadata.

The default database is `~/.fieldkit/netwatch.db`, or `FIELDKIT_NETWATCH_DB` when set.
CLI commands also accept `--db`. SQLite uses WAL mode and the database file is set to
`0600` when the filesystem supports POSIX permissions.

### Never stored as Netwatch evidence

- request or response headers and bodies;
- credentials or proxy authorization;
- URL queries and fragments;
- prompts, Bash commands, search queries, or file contents;
- full command arguments; or
- raw tool input.

The dashboard uses escaped stored values, a restrictive page Content Security Policy, and
`no-referrer`. Netwatch sends no telemetry and uses no remote service-identification or
enrichment API. A user-requested policy check may perform normal system DNS resolution.

Path redaction removes queries, fragments, UUID-shaped values, long token-shaped values,
and segments named like credentials. It is a defensive pattern filter, not a guarantee
that every personal identifier embedded in a path can be recognized.

## Platform and coverage limits

- The package requires Python 3.12 or newer.
- Proxy listeners are user-space TCP listeners on loopback, not a VPN or firewall.
- Direct sockets from software that ignores proxy configuration are outside run-mode
  capture and enforcement.
- DNS packets and lookups are not recorded as network records.
- UDP and QUIC are not captured or enforced.
- TLS is never decrypted and no certificate authority is installed.
- SOCKS BIND and UDP are unsupported.
- Attachment requires `lsof` and the expected `ps` process-table interface.
- Attach sees only established TCP sockets present when a sample runs.
- The Claude hook is the only shipped tool-action integration. Codex tool actions are not
  reported.
- Tool actions and network records are not causally correlated.
- Service identification is a local hostname heuristic.
- Universal enforcement for arbitrary macOS processes requires a separately signed
  Network Extension and is not part of this plugin.

## Interface states and access

The shipped UI covers:

- local controls available and read-only controls locked;
- local API unavailable;
- loading and manual refresh;
- no sessions, no destinations, no matching filters, no tool records, and no detected
  agents;
- starting, running, complete, failed, and interrupted sessions;
- policy starter not saved, saved, dirty, imported, invalid, and decision-check states;
- stop ownership conflict and delete confirmation/error;
- per-session partial-coverage notes;
- compact, medium, and wide layouts; and
- reduced-motion, keyboard focus, skip link, named controls, scoped table headings,
  status words, and redundant status color.

At narrow widths the navigation becomes a horizontal rail, forms and panels stack, lower
priority table columns hide, and essential destination/outcome data remains visible.

## CLI reference

| Command | Behavior |
| --- | --- |
| `doctor [--json]` | Report local capture and integration availability without opening a network socket |
| `agents [--json]` | Discover running Codex and Claude roots |
| `run [--mode audit\|enforce] [--policy PATH] [--db PATH] [--agent KIND] -- COMMAND...` | Supervise one command through the proxies |
| `attach PID [--follow] [--interval SECONDS] [--db PATH]` | Sample established TCP sockets; observation only |
| `sessions [--json] [--db PATH]` | List saved sessions |
| `report SESSION [--json] [--db PATH]` | Show grouped destination evidence |
| `policy init PATH [--force]` | Write the loopback-only starter |
| `policy add PATH --action allow\|deny [match options]` | Append a validated rule |
| `policy check PATH DESTINATION [--protocol PROTOCOL] [--mode MODE]` | Explain a decision; blocked enforce checks exit with status 3 |

## Future work, not shipped

These are useful extensions, not current promises:

- policy snapshots or revision history embedded in every session;
- live policy reload for running proxies or a command to close existing tunnels;
- cursor-based event pagination, incremental polling, or server-sent events instead of
  full-report polling;
- durable recovery of browser-owned operation control after a server restart;
- proven causal correlation between tool actions and network records;
- a browser PTY for fully interactive Codex or Claude sessions;
- named policy libraries, session labels, cross-session comparison, and retention rules;
- richer locally maintained service attribution; and
- a signed macOS Network Extension for broader process-level enforcement.
