# Field Kit product context

## Product

- **Name:** Field Kit
- **One-sentence purpose:** Help forward-deployed engineers choose and run the right local utility for an immediate field problem.
- **Maturity:** Field Kit is working development software with eight shipped plugins. awcp is the local spec-check slice, not a delivery control plane.
- **Platform:** static website pointing to local CLI and browser software.
- **Business model or service model:** no accounts, payments, subscriptions, or hosted runtime on this site.

## Users and context

### Primary user

- **Who:** a technically fluent FDE working under customer-data, access, and time constraints.
- **Expertise:** comfortable with a terminal and a checkout; does not need a hosted account.
- **Situation/environment:** mystery dump, locked-down laptop, Friday status deadline.
- **Frequency:** occasional, high-stakes field days rather than daily SaaS use.
- **Input modes:** keyboard, pointer, touch, and screen reader.
- **What they are trying to avoid:** sending customer data to a hosted service, overstating what a local check proves.

## Critical job

- **Arrival question:** “What is this, who is it for, how do I install the GitHub wheels or a pinned checkout, and which tool handles the problem in front of me?”
- **Single most important job:** find the right tool, understand its limit, and copy a README-accurate command.
- **Success state:** the user sees the real local UI, copies a working command, and knows the tool’s limits.
- **Failure cost:** sharing unsafe data, reporting the wrong change, or overstating what a local check proves.
- **Time pressure:** same-day field work.

## Critical journey

1. Read what Field Kit is, that it is not on PyPI, and how to install GitHub wheels or `uv sync` from a pinned checkout.
2. See the local hub with all eight tools installed.
3. Match the current job to one of eight shipped plugins.
4. Open one tool without losing the index; see its UI, capability, and limit.
5. For netwatch, inspect the real control-room surface, its local-sample capture, and coverage contract.
6. For awcp, see that eval scores recorded cases and does not call a model.
7. Copy an install or example command, or star the repository.

## Constraints and voice

- Static HTML/CSS/JS; no framework and no external runtime requests.
- Customer data never enters the website.
- Product imagery uses the real interface with synthetic sample evidence, clearly labelled rather than telemetry, customer traffic, or product metrics.
- Copy is exact, candid, and operational. Avoid “AI-powered,” “seamless,” and unsupported readiness claims.
- Support action is a single Star on GitHub control. No donation, coffee, or personal maintainer credit.
- Required widths: 360, 390, 768, and desktop.
- Anti-references: terminal cosplay, startup-gradient landing pages, icon-tile card walls, fabricated proof, personal attribution.

## Open hypothesis

- **H1:** Job labels make the shipped-tool grid faster to scan than grouping by implementation package. Validate with FDE users after launch.
