# Screen brief — tool index and detail

## Mode

Audit → shape → revamp → harden.

## User and job

- **User:** forward-deployed engineer with an unfamiliar file or delivery task.
- **Question on arrival:** “Which tool should I run, and what is the command?”
- **Primary action:** select a tool block, then copy an install or example command.
- **Failure cost:** unsafe data handling, wasted setup time, or a misleading maturity claim.
- **Platform/input:** responsive web; keyboard, pointer, touch, screen reader.

## Decision sequence and hierarchy

1. Understand that Fieldkit has eight shipped plugins, including a local awcp spec checker.
2. Match the current job to a tool.
3. Read capability, constraints, and maturity.
4. When evaluating netwatch, see the real local control room and its coverage limits.
5. Copy a source-accurate command.

The title and one-paragraph definition lead. The three-column tool index is next.
One detail panel follows the grid; operating constraints and FAQ are supporting
content.

## Layout by window

- **Compact (360/390):** one tool per row, 16px gutters, full-width detail,
  horizontally contained code, 44px controls, condensed header.
- **Medium (768):** two tool columns, stacked detail regions.
- **Expanded:** three tool columns; description and commands share the detail row.
  The Netwatch product capture spans the full detail width beneath them.

## Interaction and states

- Fragment links provide deep linking and no-JavaScript fallback.
- The first detail is xray until another fragment is targeted.
- Copy actions report success or failure without replacing the command.
- Focus remains visible. Reduced motion removes smooth scrolling and transitions.
- Long commands scroll inside the code surface, never the page.
- The Netwatch capture has informative alt text and a visible sample-evidence caption.

## Acceptance criteria

- Eight source-accurate Fieldkit tools, with awcp described as a local spec checker.
- Netwatch is identified as the seventh shipped plugin; awcp is the eighth.
- Install and example blocks are copyable and verified against both READMEs.
- The dashboard image is a local asset and never presents sample evidence as telemetry,
  customer traffic, benchmark data, or product adoption.
- 360, 390, 768, and desktop have no horizontal overflow, clipping, or overlap.
- Metadata, JSON-LD, OG image, robots, sitemap, llms.txt, privacy, and terms pass checks.
- No external asset requests, cookies, storage, analytics, or embedded third-party code.
