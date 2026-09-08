# FDE Tools design notes

The site uses a light “field manifest” instead of a dark terminal skin. Graphite,
warm equipment-paper neutrals, and one survey-flag red accent feel at home beside a
deployment checklist without turning the page into terminal cosplay. IBM Plex Sans
handles dense reading; IBM Plex Mono is reserved for commands, tool names, labels,
and the terminal-style wordmark.

The shipped tools are peers, so the three-column index is a real comparison
surface rather than a decorative card wall. Flat rules, no icons, no shadows, and
job labels (`Inspect`, `Sanitize`, `Compare`) keep the blocks useful. The small
parchment caliper in the wordmark follows the repo’s Relic Parchment logo rule while
the surrounding site stays contemporary and quiet.

Tool detail is a same-page fragment panel. It keeps the index as context, deep-links
to every tool, and works without JavaScript through
`:target`. JavaScript only adds copy feedback and keeps `aria-expanded` current.

Netwatch earns one product screenshot because its repeated-use control room is part of
the product, not decorative artwork. The image sits inside the existing ruled system,
uses generated local sample evidence, and carries a visible caption that separates the
example hosts and totals from customer traffic, telemetry, and benchmark claims.
