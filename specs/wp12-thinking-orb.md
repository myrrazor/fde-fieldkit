# WP12 — shared thinking-orb working indicator

Read AGENTS.md. This bonus changes only the shared busy indicator, so all six tool pages
inherit it without page-specific code.

## Files you may edit

```
src/fieldkit/web/static/fieldkit.js
src/fieldkit/web/static/fieldkit.css
tests/test_api.py
specs/wp12-thinking-orb.md
```

## Behavior

Keep the public API unchanged:

```js
withBusy(container, label, task)
```

For ordinary motion settings, the helper mounts a 20px high-DPI canvas in the existing
`.spinner` slot. Canvas 2D draws three short arcs in the computed `--accent` color. Arc
rotation and sub-pixel radius wobble produce the working state without changing layout
or blocking input.

The animation:

- uses `requestAnimationFrame`;
- stops and cancels its frame when the task settles;
- pauses while `document.hidden` is true and resumes on `visibilitychange`;
- removes its visibility listener during cleanup;
- falls back to the existing CSS ring if canvas is unavailable.

The implementation includes a concise provenance comment for Jakub Antalik's MIT
`thinking-orbs` package. It copies no dependency and adds no package.

When `prefers-reduced-motion: reduce` matches, canvas animation does not start. The
existing CSS ring remains visible at its slowed 2.5-second rotation, preserving progress
status without the multi-arc motion.

## Acceptance

- `withBusy` retains its arguments and return behavior.
- The ordinary path draws three accent-colored arcs on a 20px canvas.
- The reduced-motion path uses the slowed CSS ring.
- Visibility changes pause and resume frame scheduling.
- Cleanup cancels work and removes the indicator even when the task throws.
- Static contract tests cover canvas, reduced-motion, visibility, cleanup, and the CSS
  fallback.
- Browser smoke covers tell and at least one other tool page.
- `uv run pytest -q` passes and `uv run ruff check .` is clean.
