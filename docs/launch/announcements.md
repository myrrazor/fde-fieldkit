# Announcement drafts for Fieldkit 0.2.0

These are drafts, not posts. Before publishing, read each community's rules
(Show HN guidelines, subreddit self-promotion policy, and X norms). Do not
invent traction, users, timings, or results.

Facts this copy may use:

- Repository: https://github.com/myrrazor/fde-fieldkit
- GitHub Release (intended): https://github.com/myrrazor/fde-fieldkit/releases/latest
- Website: https://fde-tools-review.vercel.app
- License: MIT
- Python >= 3.12
- Not on PyPI. The PyPI name `fieldkit` is an unrelated project.
- Eight plugins: xray, scrub, mimic, datadiff, debrief, tell, netwatch, awcp
- Local by default; Tell remote and Netwatch relay need explicit action

## Show HN

Title: `Show HN: Fieldkit – local CLI tools for messy field-engineering data`

First comment:

```
Fieldkit is a local toolkit for the days you get a mystery CSV, a locked-down
laptop, and a Friday status deadline.

One `fieldkit` core plus eight plugins: profile a file (xray), replace detected
PII (scrub), generate seeded demo data (mimic), explain dump diffs (datadiff),
write weekly status (debrief), inspect a draft for writing tells (tell), watch
where an agent connects (netwatch), and check an AI workload spec (awcp).

It is MIT-licensed, Python 3.12+, and not on PyPI — the PyPI project named
fieldkit is unrelated. Install the GitHub Release wheels by explicit path, or
`uv sync` from the v0.2.0 tag.

Repo: https://github.com/myrrazor/fde-fieldkit
Release: https://github.com/myrrazor/fde-fieldkit/releases/latest
Site: https://fde-tools-review.vercel.app

I would like feedback on whether the GitHub wheel install is clear, and which
tool is missing for real field days.
```

## r/commandline

Title: `Fieldkit: local CLI toolkit for profiling, PII replacement, diffs, and agent network traces`

```
Fieldkit is a local CLI (and loopback hub) for field-engineering grunt work:
mystery dumps, PII before you share a file, seeded demo data, dump diffs,
Friday status notes, draft checks, agent connection traces, and AI workload
spec checks.

Python 3.12+. MIT. Not on PyPI (that name is a different project). GitHub
Release wheels or a pinned v0.2.0 checkout.

https://github.com/myrrazor/fde-fieldkit
https://github.com/myrrazor/fde-fieldkit/releases/latest
https://fde-tools-review.vercel.app

Happy to answer command questions.
```

## r/opensource

Title: `Fieldkit 0.2.0 — MIT-licensed local toolkit (CLI + plugins) for FDE data work`

```
Open-source (MIT) local toolkit aimed at forward-deployed engineers. Core
package plus eight independently installable plugins. No hosted accounts on
the project site. Not published to PyPI; GitHub Release assets only.

https://github.com/myrrazor/fde-fieldkit
https://github.com/myrrazor/fde-fieldkit/releases/latest
https://fde-tools-review.vercel.app

This is a first public GitHub release (0.2.0), not a 1.0. Feedback on packaging
and docs is welcome.
```

## X

Draft thread. Link on the last post, not the first.

1. Mystery CSV, locked-down laptop, Friday status. Fieldkit runs that work on your machine — no telemetry, no hosted upload.
2. Eight plugins: xray, scrub, mimic, datadiff, debrief, tell, netwatch, awcp. Local by default. Tell remote and Netwatch relay only after you ask.
3. MIT, Python 3.12+. Not on PyPI (that name is taken by a different project). GitHub wheels or `uv sync` from the v0.2.0 tag.
4. First public GitHub release is 0.2.0. Early software. Limits are in the README: 50 MB inputs, detectors miss things, Netwatch is not a firewall.
5. Repo https://github.com/myrrazor/fde-fieldkit — release https://github.com/myrrazor/fde-fieldkit/releases/latest — site https://fde-tools-review.vercel.app
