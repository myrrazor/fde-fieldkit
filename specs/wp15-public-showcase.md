# WP15: Public README and tool showcase

## Outcome

Make Fieldkit understandable on first visit, show real local UI results for the
hub and all eight tools, and replace personal support/credit copy with a single
Star on GitHub action. Preserve the existing field-manifest visual system.

## Authorized files

- README.md
- site/index.html
- site/styles.css
- site/script.js
- site/check_site.py
- site/vercel.json
- site/llms.txt
- site/PRODUCT.md
- site/DESIGN.md
- site/SCREEN-BRIEF.md
- site/privacy.html
- site/terms.html
- site/docs/index.html
- site/docs/plugins.html
- site/docs/xray.html
- site/docs/scrub.html
- site/docs/mimic.html
- site/docs/datadiff.html
- site/docs/debrief.html
- site/docs/tell.html
- site/docs/netwatch.html
- site/docs/awcp.html
- site/assets/screenshots/README.md
- site/assets/screenshots/hub.png
- site/assets/screenshots/xray.png
- site/assets/screenshots/scrub.png
- site/assets/screenshots/mimic.png
- site/assets/screenshots/datadiff.png
- site/assets/screenshots/debrief.png
- site/assets/screenshots/tell.png
- site/assets/screenshots/netwatch.png
- site/assets/screenshots/awcp.png
- tests/test_site_release.py
- specs/wp15-public-showcase.md
- TEST_STDOUT.log (local verification evidence, ignored)

## Contract

The orchestrator captures actual UI using synthetic examples and isolated local
databases. Images must show real output, with visible captions identifying sample
data. No fake UI, customer claims, activity, or usage metrics. All assets stay
self-hosted. The website never uploads data or contacts external runtime services.

Every selected tool panel and corresponding docs page shows its screenshot with
informative alt text and a full-size image link. The README has an immediate
product definition, working checkout instructions, a hub image, and accessible
per-tool screenshots with commands and limits. Keep the documented PyPI, offline
installation, detector accuracy, explicit remote opt-in, model download, and
Netwatch coverage limitations. Preserve existing license notices and security
contracts. No dependencies or core/runtime changes are needed.

Remove donation language and personal maintainer attribution. Only project GitHub
links remain as support actions. Report privacy findings without copying private
identifiers into public documentation. No private Git history may enter the PR.

## Verification

Run locked workspace lint and the full pytest suite, the self-contained site
checker, browser JavaScript syntax checks, and public privacy checks. Verify
images resolve, tool selections and copy controls work, keyboard focus is visible,
and layouts reflow at compact, tablet, and desktop widths. Inspect rendered
screenshots. Capture suite output in TEST_STDOUT.log. The orchestrator reviews,
commits, pushes a feature branch, and opens the authorized PR directly to main;
the implementation worker leaves changes uncommitted.
