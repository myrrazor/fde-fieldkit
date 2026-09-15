# Screen brief — public README and tool showcase

## Mode

Audit → revamp → harden. Preserve the field-manifest brand; do not invent a new system.

## User and job

- **User:** forward-deployed engineer with an unfamiliar file or delivery task.
- **Question on arrival:** “What is Fieldkit, how do I run it from a checkout, and which tool should I use?”
- **Primary action:** understand the product, see real local UI, select a tool, copy a command, or star the repository.
- **Failure cost:** unsafe data handling, wasted setup time, or a misleading maturity claim.
- **Platform/input:** responsive web and GitHub-rendered README; keyboard, pointer, touch, screen reader.

## Decision sequence and hierarchy

1. Understand that Fieldkit is a local toolkit, not on PyPI, run from a checkout.
2. See the local hub with all eight tools installed.
3. Match the current job to a tool.
4. Read capability, constraints, and the matching UI screenshot.
5. When evaluating netwatch, see the real local control room, local-sample capture, and coverage limits.
6. When evaluating awcp, see that eval scores recorded cases and does not call a model.
7. Copy a source-accurate command, or star the GitHub repository.

The title and one-paragraph definition lead. The hub capture is next. The
three-column tool index follows. One detail panel includes commands and the
tool’s screenshot; operating constraints and FAQ are supporting content.

## Layout by window

- **Compact (360/390):** one tool per row, 16px gutters, full-width detail and
  screenshots, horizontally contained code, 44px controls, condensed header.
- **Medium (768):** two tool columns, stacked detail regions, screenshots full width.
- **Expanded:** three tool columns; description and commands share the detail row.
  Each selected tool’s product capture spans the full detail width beneath them.
  The hub capture is full-width above the index.

## Interaction and states

- Fragment links provide deep linking and no-JavaScript fallback.
- The first detail is xray until another fragment is targeted.
- Copy actions report success or failure without replacing the command.
- Focus remains visible. Reduced motion removes smooth scrolling and transitions.
- Long commands scroll inside the code surface, never the page.
- Every product capture has informative alt text, width/height, and a visible
  full-size image link. Below-the-fold images lazy-load.
- The only support action is Star on GitHub.

## Acceptance criteria

- Eight source-accurate Fieldkit tools, with awcp described as a local spec checker.
- Hub screenshot near the top; each selected tool panel and matching docs page
  shows `assets/screenshots/{tool}.png`.
- Netwatch is identified as the seventh shipped plugin; awcp is the eighth.
- Install and example blocks are copyable and verified against the README.
- Screenshots are local assets labelled as synthetic sample data, never presented
  as telemetry, customer traffic, benchmarks, or product adoption.
- 360, 390, 768, and desktop have no horizontal overflow, clipping, or overlap.
- Metadata, JSON-LD, OG image, robots, sitemap, llms.txt, privacy, and terms pass checks.
- No donation, coffee, or personal maintainer credit. Star on GitHub is the support action.
- No external asset requests, cookies, storage, analytics, or embedded third-party code.
