# Netwatch product contract

Netwatch answers one operational question before everything else: **where did this agent
connect, and what did policy do?** It is for developers and FDEs who need auditable network
evidence around coding-agent work without turning a laptop into an enterprise appliance.

## Primary jobs

1. Start a coding-agent command through local proxies and see its destination evidence.
2. Separate public internet traffic, local/private access, failures, and blocked attempts.
3. Turn observed destinations into a small deny-by-default policy.
4. Explain the rule that will apply before starting an enforce run.
5. Export or delete local evidence without sending it to a hosted service.

The secondary job is attaching to an already-running process for an honest,
observation-only socket inventory.

## Product thesis

Trust is the product. Coverage appears before totals. The interface distinguishes HTTP
requests, CONNECT/SOCKS tunnels, socket observations, and tool actions rather than calling
all of them network calls. Status words remain visible when color is unavailable.

The dashboard is a high-frequency local control room with five durable areas: overview,
live traffic, agents and capture, policies, and diagnostics. It prioritizes comparison and
evidence tables over generic KPI cards or security theater.

Interactive coding agents remain terminal-owned. The dashboard can run a noninteractive
argv command and monitor it, but it does not pretend to be a browser terminal. It generates
the corresponding CLI command for Codex or Claude and then reads the same local evidence.

## Shipped outcome

A user can:

- compare saved traffic by agent class, proxy path, destination, network scope, decision,
  service heuristic, and relayed byte count;
- inspect and filter one session's grouped destinations and raw records;
- view sanitized supported-hook actions without implying causal correlation;
- discover running Codex and Claude roots and attach by PID;
- start and stop dashboard-owned noninteractive supervision or follow attachment;
- edit, import, export, save, and test the managed destination policy;
- download a complete JSON report or labelled CSV ledger; and
- delete stopped evidence after confirmation.

## Trust boundary

Netwatch stores metadata locally, never decrypts TLS, never installs a CA, never sends
telemetry, and never edits global Codex or Claude settings. Prompts, shell commands, search
queries, headers, bodies, URL queries, raw tool input, and command arguments are not evidence.

Run mode proves only what traverses its local proxies. Attachment proves only that an
established TCP socket was present when sampled. Direct sockets, DNS packets, UDP/QUIC,
short-lived sockets missed between samples, and HTTPS content remain outside coverage.

Dashboard mutations require a direct loopback request and a per-process control token.
Read evidence follows the interface on which the user chooses to bind `fieldkit serve`; the
safe default is loopback.

## Non-goals

- whole-machine packet capture or firewall replacement;
- TLS interception;
- remote fleet management;
- packet-level byte accounting;
- guaranteed vendor ownership from a hostname label;
- proven tool-action-to-network causality;
- a browser PTY for interactive agents; or
- changing the policy of a running proxy or closing its existing tunnels.

Success is an accurate, useful evidence trail and predictable future-run policy. It is not
a claim of universal visibility from a user-space proxy. See [`SPEC.md`](SPEC.md) for the
complete shipped contract and the separately labelled future-work list.
