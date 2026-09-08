# WP13 — netwatch: agent network evidence and policy control

Read `AGENTS.md`. Netwatch is a local interception tool, so its deliberate relay traffic is
the second narrow egress exception in the repository. It must never send telemetry, resolve
service names through a remote API, install a certificate authority, or pretend proxy coverage
is whole-machine coverage.

## Files you may create/edit

```
AGENTS.md
DESIGN.md
README.md
TEST_STDOUT.log
examples/netwatch-policy.json
pyproject.toml
uv.lock
specs/wp13-netwatch.md
src/fieldkit/plugins.py
src/fieldkit/web/app.py
src/fieldkit/web/static/index.html
tests/test_api.py
tests/test_plugins.py
plugins/fieldkit-netwatch/pyproject.toml
plugins/fieldkit-netwatch/README.md
plugins/fieldkit-netwatch/PRODUCT.md
plugins/fieldkit-netwatch/DESIGN.md
plugins/fieldkit-netwatch/SCREEN-BRIEF.md
plugins/fieldkit-netwatch/SPEC.md
plugins/fieldkit-netwatch/src/fieldkit_netwatch/__init__.py
plugins/fieldkit-netwatch/src/fieldkit_netwatch/models.py
plugins/fieldkit-netwatch/src/fieldkit_netwatch/destinations.py
plugins/fieldkit-netwatch/src/fieldkit_netwatch/policy.py
plugins/fieldkit-netwatch/src/fieldkit_netwatch/store.py
plugins/fieldkit-netwatch/src/fieldkit_netwatch/proxy.py
plugins/fieldkit-netwatch/src/fieldkit_netwatch/agents.py
plugins/fieldkit-netwatch/src/fieldkit_netwatch/supervisor.py
plugins/fieldkit-netwatch/src/fieldkit_netwatch/attach.py
plugins/fieldkit-netwatch/src/fieldkit_netwatch/control.py
plugins/fieldkit-netwatch/src/fieldkit_netwatch/hook.py
plugins/fieldkit-netwatch/src/fieldkit_netwatch/cli.py
plugins/fieldkit-netwatch/src/fieldkit_netwatch/web.py
plugins/fieldkit-netwatch/src/fieldkit_netwatch/static/index.html
plugins/fieldkit-netwatch/src/fieldkit_netwatch/static/app.js
plugins/fieldkit-netwatch/tests/conftest.py
plugins/fieldkit-netwatch/tests/test_destinations.py
plugins/fieldkit-netwatch/tests/test_policy.py
plugins/fieldkit-netwatch/tests/test_store.py
plugins/fieldkit-netwatch/tests/test_proxy.py
plugins/fieldkit-netwatch/tests/test_agents.py
plugins/fieldkit-netwatch/tests/test_control.py
plugins/fieldkit-netwatch/tests/test_supervisor.py
plugins/fieldkit-netwatch/tests/test_cli.py
plugins/fieldkit-netwatch/tests/test_web.py
site/PRODUCT.md
site/DESIGN.md
site/DESIGN-NOTES.md
site/SCREEN-BRIEF.md
site/index.html
site/styles.css
site/privacy.html
site/terms.html
site/llms.txt
site/sitemap.xml
site/check_site.py
site/docs/index.html
site/docs/plugins.html
site/docs/netwatch.html
site/docs/xray.html
site/docs/scrub.html
site/docs/mimic.html
site/docs/datadiff.html
site/docs/debrief.html
site/docs/tell.html
site/assets/og.svg
site/assets/og.png
site/assets/netwatch-dashboard.png
```

## Product contract

`fieldkit-netwatch` is the seventh installable Fieldkit plugin. It provides two honest
coverage modes:

1. `netwatch run -- <command>` starts loopback-only HTTP CONNECT/forward and SOCKS5 TCP
   proxies, points the child process at them, records metadata in SQLite, and can enforce a
   versioned policy. Codex and Claude Code get supported, invocation-local integration without
   editing either user's global settings.
2. `netwatch attach <pid>` samples established sockets for that process and its descendants
   through `lsof`. Attach is observation-only and must say so in every output surface.

The local proxy stores session metadata, destination host/IP/port, IP scope, protocol, HTTP
method and sanitized path when plaintext makes them visible, decisions, matching policy rule,
timing, and byte counts. It never stores request/response bodies, headers, credentials, or URL
queries. HTTPS stays opaque beyond the CONNECT/SOCKS destination unless an agent hook supplies a
sanitized URL. Session evidence keeps the executable name but drops all command arguments.

## Policy

Policies are JSON, `version: 1`, with an explicit default action and ordered rules. Rules may
match exact or wildcard hosts, IP addresses/CIDRs, ports, and protocols. Deny wins when matching
rules conflict. Private, loopback, link-local, and reserved targets require a matching allow rule
that explicitly opts into private destinations. Audit mode records `would_block` and allows the
connection. Enforce mode refuses to start without a policy file and blocks denied/unmatched
traffic before opening an upstream socket.

The CLI can create a safe starter policy, add allow/deny rules without losing existing entries,
and explain a policy decision for a destination before the user runs an agent.

## Agent integration and coverage labels

- Every supervised command receives standard upper- and lower-case HTTP(S)/ALL proxy variables
  and an empty NO_PROXY so loopback attempts are visible when the client honors proxies.
- Supported Codex versions also receive the experimental sandbox network-proxy feature configured
  to chain through the environment proxy. Netwatch checks the installed feature list first and
  records whether this stronger path was active.
- Claude Code receives an invocation-only `--settings` file enabling fail-closed sandboxing,
  custom HTTP/SOCKS ports, a strict sandbox allowlist handed off to Netwatch, and PreToolUse hooks.
  Existing user/project settings continue to load; Netwatch never edits them.
- Claude hook input is reduced to event/tool metadata and a sanitized target. Prompts, Bash
  commands, search queries, and file contents are not persisted.
- Direct sockets from software that ignores proxies, UDP/QUIC, DNS packets, in-process browser
  traffic without a supported hook, and already-running process enforcement are labelled
  uncovered. Universal blocking is reserved for a separately signed macOS Network Extension.

## CLI and web surface

```
fieldkit netwatch doctor [--json]
fieldkit netwatch agents [--json]
fieldkit netwatch run [--mode audit|enforce] [--policy PATH] [--db PATH] -- COMMAND...
fieldkit netwatch attach PID [--follow] [--db PATH]
fieldkit netwatch sessions [--json] [--db PATH]
fieldkit netwatch report SESSION [--json] [--db PATH]
fieldkit netwatch policy init PATH
fieldkit netwatch policy add PATH --action allow|deny [match options]
fieldkit netwatch policy check PATH DESTINATION [--protocol PROTOCOL]
```

The browser page is a repeated-use local control room. Its arrival question is “where did this
agent connect, and what should happen next?” It provides cross-session/source evidence, live
session inspection, agent discovery, observation-only attachment, supervised command launch and
stop, managed policy editing/import/export/checking, report export, and saved-session deletion.
The existing CLI remains available for terminal-first workflows.

Browser mutations are a local code-execution boundary. They must require a loopback client and
loopback Host, a same-origin request, JSON plus a per-process control token, and an operation owned
by the current server when stopping a run. The browser never accepts an arbitrary database or
policy filesystem path. When Fieldkit is served on a non-loopback interface, Netwatch stays a
read-only evidence viewer.

Tables use tabular numerals and plain status words; color is redundant. Loading, empty, error,
partial coverage, permission/read-only, running, stopped, destructive, overfull, keyboard,
reduced-motion, compact, and wide layouts are covered.

## Acceptance

- `fieldkit plugin add netwatch` resolves the workspace package and the CLI/web entry points load.
- A supervised HTTP request and HTTPS CONNECT tunnel reach a local test server and produce
  metadata-only rows; a denied request never reaches that server.
- SOCKS5 TCP CONNECT is recorded and enforced; BIND and UDP are rejected and labelled unsupported.
- Policy tests cover wildcard boundaries, deny precedence, CIDRs, ports, protocols, private-network
  opt-in, invalid JSON, audit `would_block`, and enforce default denial.
- Codex/Claude adapters are version/capability aware, invocation-local, and tested without calling
  either vendor API. Claude hooks persist no prompt, command, query, headers, or body content.
- Attach parsing identifies parent/child processes and deduplicates repeated socket snapshots;
  attach never claims enforcement.
- CLI and web reports group destinations by identified service and host, with counts, decisions,
  scope, bytes, first/last seen, and explicit coverage limitations.
- The dashboard provides CLI-equivalent doctor, agent discovery, supervised run, attach, sessions,
  report, policy initialization/editing/checking, and JSON/CSV export workflows. Interactive agent
  terminals remain terminal-owned; the dashboard launches direct argv commands without a shell.
- All browser mutation routes reject non-loopback clients/hosts, cross-origin requests, missing or
  invalid control tokens, and non-JSON bodies. Policy writes stay inside Netwatch's managed private
  file and supervised stop only cancels tasks owned by the current web process.
- The web page escapes stored content, has semantic controls/tables, visible focus, labelled status,
  and usable compact/laptop/wide layouts.
- Root docs, local hub, public site, policy example, plugin registry, and privacy/egress language all
  agree that there are seven Fieldkit plugins and that Netwatch relays only user-requested traffic.
- The anti-slop scan has no new confirmed finding in Netwatch files. Browser smoke has no console
  errors and responsive captures are reviewed.
- `uv run pytest -q` passes, `uv run ruff check .` is clean, and the passing test output is captured
  in `TEST_STDOUT.log`.
