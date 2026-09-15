# FDE Tools design system

## Design thesis

- **Register:** brand surface with product-level command accuracy.
- **Character:** exact, field-ready, candid.
- **Visual vocabulary:** equipment manifests, ruled inspection sheets, copyable commands.
- **Signature move:** a flat job index opening one full-width working panel.
- **Product proof:** the real local hub near the top, plus a captioned UI capture in every selected tool panel and matching docs page. Images use labelled synthetic sample evidence rather than decoration.
- **What stays quiet:** background, motion, surfaces, and ornament.

## Direction decision

### Chosen: field manifest

Light equipment-paper background, strong grid rules, survey-flag red, dense Sans
copy, Mono for commands. It supports daylight use, comparison, and real command
content without imitating a terminal. Main risk: the required equal grid can feel
generic, so job labels, hard rules, real screenshots, and the shared detail panel
must carry structure. `[P][H]`

This polish keeps that system. It does not introduce a new visual language.

### Rejected: command ledger

Near-black, green/amber accent, monospace across the page, prompt-shaped navigation.
It matched the CLI but failed the brief’s “not terminal cosplay” requirement and
would make long descriptions harder to read.

### Rejected: incident briefing

Large editorial typography, wide narrative sections, and a sequential workflow.
It had a strong voice but falsely implied the tools must be used in order and made
the peer comparison slower.

## System

- **Colors:** background `#f4f2ea`; surface `#fbfaf5`; text `#1e2628`; muted
  `#566064`; accent `#a13d36`; focus `#145f9f`; code `#20282a`.
- **Type:** IBM Plex Sans 100–700 for prose and hierarchy; IBM Plex Mono 400/600
  for commands, tool names, labels, and the wordmark. All files self-hosted with
  `font-display: swap`.
- **Layout:** 76rem maximum width; three tool columns expanded, two at medium,
  one compact; 43rem prose measure.
- **Surfaces:** borders before shadows; no page elevation or decorative blur.
- **Motion:** color feedback only, 140ms; removed under reduced motion.
- **Targets:** navigation, tool blocks, summaries, copy buttons, and screenshot
  full-size links are at least 44px tall on compact screens.

### Verified contrast pairs

| Foreground / indicator | Background | Ratio | Use |
|---|---|---:|---|
| `#1e2628` | `#f4f2ea` | 13.74:1 | Primary text |
| `#566064` | `#f4f2ea` | 5.76:1 | Body and secondary text |
| `#a13d36` | `#f4f2ea` | 5.79:1 | Accent labels and rules |
| `#f6f3e7` | `#20282a` | 13.51:1 | Command text |
| `#818986` | `#f4f2ea` | 3.20:1 | Essential grid boundaries |
| `#145f9f` | `#f4f2ea` | 5.92:1 | Keyboard focus indicator |

## Components and states

| Component | States | Access notes |
|---|---|---|
| Tool link | default, hover, focus, selected, active | Real fragment link; `aria-expanded` mirrors the target |
| Detail panel | default xray, targeted tool | Deep-linkable and visible without JavaScript |
| Copy button | default, hover, focus, copied, failure | Text label and polite live status |
| FAQ disclosure | closed, open, focus | Native `details` / `summary` |
| Code block | long and short commands | Scrolls inside its own container |
| Product screenshot | hub plus eight tool captures; compact reflow | Informative alt; width/height; lazy below the fold; visible caption identifies synthetic sample data; accessible full-size link |
| Star on GitHub | default, hover, focus | The only support action; project repository URL |

## Imagery

- Self-hosted PNG captures at `assets/screenshots/{hub,xray,scrub,mimic,datadiff,debrief,tell,netwatch,awcp}.png`.
- Hub is above the fold and loads eagerly. It lists installed tools only; no selected tool or dataset.
- Tool captures lazy-load. Captions describe the pictured result and label synthetic sample data.
- Tell screenshot is a scrolled report of synthetic slop_sample.md with remote adapters skipped.
- Netwatch screenshot: one completed generic session and two HTTP requests to a local sample endpoint; generated sample evidence, no customer or external traffic. Counts are that example's measurements.
- AWCP screenshot is Eval of recorded sample outputs; no model ran. It does not show Check mode.

## Gates

- Exactly one `h1` and ordered headings per page.
- Visible keyboard focus; no color-only state.
- No ordinary horizontal scroll at target widths.
- No non-essential cookies, storage, analytics, embeds, or external assets.
- awcp's local-only limit (no model, no control plane) remains adjacent to its description and commands.
- Netwatch imagery never implies customer traffic, usage metrics, or whole-machine coverage.
- No donation, coffee, or personal maintainer credit copy.
