# FDE Tools design system

## Design thesis

- **Register:** brand surface with product-level command accuracy.
- **Character:** exact, field-ready, candid.
- **Visual vocabulary:** equipment manifests, ruled inspection sheets, copyable commands.
- **Signature move:** a flat job index opening one full-width working panel.
- **Product proof:** one wide, captioned Netwatch control-room capture inside its detail
  panel and docs page; the image uses labelled sample evidence rather than decoration.
- **What stays quiet:** background, motion, surfaces, and ornament.

## Direction decision

### Chosen: field manifest

Light equipment-paper background, strong grid rules, survey-flag red, dense Sans
copy, Mono for commands. It supports daylight use, comparison, and real command
content without imitating a terminal. Main risk: the required equal grid can feel
generic, so job labels, hard rules, and the shared detail panel must carry real
structure. `[P][H]`

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
- **Targets:** navigation, tool blocks, summaries, and copy buttons are at least
  44px tall on compact screens.

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
| Product screenshot | full-width Netwatch dashboard, compact reflow | Informative alt text; visible caption identifies generated sample evidence |

## Gates

- Exactly one `h1` and ordered headings per page.
- Visible keyboard focus; no color-only state.
- No ordinary horizontal scroll at target widths.
- No non-essential cookies, storage, analytics, embeds, or external assets.
- awcp's local-only limit (no model, no control plane) remains adjacent to its description and commands.
- Netwatch imagery never implies customer traffic, usage metrics, or whole-machine coverage.
