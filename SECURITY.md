# Security policy

## Report privately

Use [GitHub private vulnerability reporting](https://github.com/myrrazor/fde-fieldkit/security/advisories/new).
Do not open a public issue containing a vulnerability, personal information,
credentials, customer files, or an unredacted Netwatch database.

Include the affected version or commit, reproduction steps using synthetic data,
the expected security boundary, and the observed result. A minimal test or patch
is helpful. Share only what is necessary to reproduce the problem. If the private
reporting form is unavailable, do not publish the details; use GitHub support to
resolve access to the reporting form.

Maintainers will assess the report, coordinate a fix, and agree on disclosure
where practical. There is no paid response SLA or bug-bounty program.

## Supported code

Fieldkit is in early development. Security fixes target the current `main`
branch; there is no separate long-term-support branch. Package version 0.2.0
currently identifies the source and does not imply a published release.

## Boundaries

- The browser hub binds to loopback. Host checks and same-origin controls are
  part of the boundary; do not expose it through an untrusted reverse proxy.
- Tell sends draft text to configured vendors only after explicit per-run
  consent. Package installation and optional model downloads can use the network.
- Netwatch supervises traffic that traverses its proxies. It is not a system
  firewall, TLS inspection service, or whole-machine enforcement mechanism.
  Attaching to an already-running process is observation-only.
- Scrub detection can miss sensitive values. Reversal mappings are sensitive.
  Mimic specifications can retain non-PII source values and distributions.
- Reports and local databases may contain private data. Keep them out of Git and
  review exports before sharing them.

Do not test these boundaries against systems or data you do not have permission
to assess. Never send real credentials to a scanner just to determine whether
an example token is valid.
