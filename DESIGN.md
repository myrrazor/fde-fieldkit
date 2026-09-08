# fieldkit — design notes

## Product context

Forward-deployed engineers on customer sites. Episodic but intense use: data day
(xray → scrub → mimic), migration day (datadiff), Friday (debrief). Everything runs
locally — that's a compliance feature, and the UI says so out loud. Stakes: leaking
customer PII ends engagements. So: trust, legibility under density, zero theatrics.

Register: product UI. The hub gets the only brand moment, and it's small.

## Direction: field-paper workbench

Instruments and printed reports, not a SaaS template. Warm paper background, ink
text, one burnt-orange accent doing all the action work, uppercase letterspaced
labels like equipment engraving, mono for anything that is data.

Rejected: dark ops console (the default dev-tool cliché, and worse for reading
dense tables in bright rooms); neutral admin blue (belongs to no product).

Signature move: the shared **report panel** — every tool's output lands in the same
dense, printable report structure that mirrors the CLI's rich tables. Plus the
local-only strip on every page.

Netwatch adds one safety-specific rule: coverage appears before metrics. Its tables never
let “0 events” imply whole-machine silence when the active backend only covers proxy-routed
traffic or sampled sockets. Denied traffic uses the existing danger family; audit-only
`would block` uses warning text, so color is never the only distinction.

## Tokens (in fieldkit.css)

- bg `#faf8f4` paper · surface `#ffffff` · sunken `#f3f0ea`
- ink `#1c1a17` · muted `#6b675f` · subtle `#938f86` · border `#e4e0d8`
- accent text/links `#9a3412` · accent action bg `#9a3412` (white text, ~5.9:1)
- success `#166534`/`#f0fdf4` · warn `#854d0e`/`#fefce8` · danger `#991b1b`/`#fef2f2`
  · info `#1e40af`/`#eff6ff` — PII flags use the danger family
- sans: system stack · mono: ui-monospace stack (no webfonts — offline is a feature)
- radius 6px · borders over shadows · tabular-nums on all numeric columns
- motion: state feedback only (spinner, toast); honors prefers-reduced-motion

Single light theme is a deliberate v1 call [H]: localhost tool, print-adjacent
output. Revisit if field feedback asks for dark.

## Copy voice

Utilitarian, lowercase-leaning, no exclamation marks, no marketing verbs.
"drop a csv, get a profile" — not "Unlock insights from your data!"
