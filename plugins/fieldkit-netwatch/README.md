# fieldkit-netwatch

See and control the network destinations an AI coding agent reaches.

Netwatch starts loopback HTTP and SOCKS5 proxies, launches a command through them, and
stores metadata-only evidence in SQLite. It strengthens coverage for supported Codex and
Claude Code versions without changing global settings.

```bash
fieldkit plugin add netwatch
fieldkit netwatch doctor
fieldkit serve
```

Open `http://127.0.0.1:8765/netwatch/` for the control room. It includes:

- a cross-session overview by agent, capture path, and destination;
- a filterable live session ledger with grouped destinations, raw records, coverage, and
  separately reported tool actions;
- local discovery and observation of running Codex and Claude processes;
- noninteractive direct-argv launches and observation-only PID attachment;
- a complete policy editor and destination decision simulator;
- diagnostics for the capture paths available on this machine; and
- JSON/CSV session exports, owned-session stop, and stopped-evidence deletion.

The dashboard calls mixed evidence **records**. Plain HTTP records can represent requests,
CONNECT and SOCKS records are tunnels, and attach records are socket observations. They
are not interchangeable request counts.

## Run an interactive agent

Interactive Codex and Claude sessions keep their terminal. Start them there, then watch
the shared session in the dashboard:

```bash
fieldkit netwatch run -- codex
fieldkit netwatch run -- claude
```

The dashboard can launch direct argv commands, but it is not a browser terminal. Use that
form for noninteractive work. Its terminal-command block builds and copies the equivalent
CLI invocation.

## Block destinations

Start from the loopback-only policy and append the hosts your agent actually needs:

```bash
fieldkit netwatch policy init policy.json
fieldkit netwatch policy add policy.json \
  --action allow --id anthropic-api --host api.anthropic.com --port 443 --protocol https
fieldkit netwatch policy add policy.json \
  --action deny --id telemetry --host '*.sentry.io'
fieldkit netwatch policy check policy.json https://api.anthropic.com
fieldkit netwatch run --mode enforce --policy policy.json -- claude
```

Rules can combine host patterns, IP/CIDR ranges, ports, and protocols. Every configured
matcher in a rule must match; repeated values inside one matcher are alternatives. A deny
rule wins over an allow rule. Private and loopback targets require a matching allow rule
with `allow_private: true`.

Host patterns are deliberately small and predictable:

- `api.example.com` matches that exact host.
- `*.example.com` matches subdomains, but not `example.com` itself.
- `**.example.com` matches the apex and its subdomains.
- `*` matches every host.

Audit mode allows traffic and records denied policy decisions as `would_block`. Enforce
mode refuses to start without a policy and blocks before opening the upstream connection.

The dashboard manages one private policy file at `FIELDKIT_NETWATCH_POLICY`, or
`netwatch-policy.json` beside the evidence database when the variable is unset. It can
import/export JSON, edit and reorder rules, prefill rules from observed destinations, and
explain a destination before a run.

Saved policy changes apply to future supervised runs. A running proxy keeps the policy it
loaded at startup, and saving a new rule does not close an existing tunnel.

## Attach to an existing process

```bash
fieldkit netwatch agents
fieldkit netwatch attach 12345
fieldkit netwatch attach 12345 --follow
```

Attach samples established TCP sockets for a PID and its descendants with `lsof`. It is
observation-only: it cannot block, see request paths, or turn a socket snapshot into a
request count. It can also miss sockets that open and close between samples.

## What is and is not covered

Run mode covers connections that traverse its loopback proxies. Netwatch sets standard
proxy variables for every command, enables Codex's supported sandbox proxy when available,
and gives supported Claude Code versions an invocation-only fail-closed sandbox and hook.

It does not install a certificate authority, inspect TLS bodies, capture DNS or UDP/QUIC,
or intercept a direct socket from software that bypasses the proxies. Whole-process or
whole-machine enforcement for arbitrary apps needs a separately signed macOS Network
Extension. `fieldkit netwatch doctor --json` reports exactly which paths are available.

Evidence defaults to `~/.fieldkit/netwatch.db`; override it with `--db` or
`FIELDKIT_NETWATCH_DB`. Prompts, Bash commands, search queries, headers, bodies, URL queries,
and command arguments are never stored. HTTP content passes through memory when proxied but
is not written to evidence.

Netwatch mutation routes unlock only for a direct loopback browser and require a
per-process control token, same-origin request metadata, and JSON. The regular Fieldkit
default is `127.0.0.1`; do not bind the server to a wider interface if other machines should
not be able to read its evidence.

The complete shipped behavior, API, evidence fields, states, and non-goals are in
[`SPEC.md`](SPEC.md).
