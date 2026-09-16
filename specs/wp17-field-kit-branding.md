# WP17 — Field Kit branding

## Outcome

Use **Field Kit** consistently in current public prose, the README, marketing
site and documentation. Replace the illustrated caliper tile with a minimal,
recognizable caliper mark. Ship reusable vector and PNG assets for GitHub social
preview, website sharing and a portfolio card. Repository, package and CLI
identifiers remain unchanged. Existing screenshots remain real and unchanged.

## Ownership and constraints

The orchestrator creates the visual assets and build script, reviews the entire
diff, runs the full required suite, and submits a PR to public `main`. A bounded
Grok worker updates the listed prose, page integration and relevant site checks.
No runtime changes, new dependencies, version bump, merge, deployment, domain
change or changes to personal/private/archive repositories are in scope.
Preserve factual network-consent, installation and release documentation.
Keep literal CLI output transcripts accurate. Do not expose personal identity.
Run CPU-heavy tasks sequentially and reuse installed tools.

## Exact file allowlist — worker

- `CHANGELOG.md`
- `CODE_OF_CONDUCT.md`
- `CONTRIBUTING.md`
- `DESIGN.md`
- `LAUNCH_CHECKLIST.md`
- `README.md`
- `SECURITY.md`
- `THIRD_PARTY_NOTICES.md`
- `docs/RELEASING.md`
- `docs/launch/announcements.md`
- `docs/releases/v0.2.0.md`
- `plugins/fieldkit-awcp/README.md`
- `plugins/fieldkit-datadiff/README.md`
- `plugins/fieldkit-debrief/README.md`
- `plugins/fieldkit-mimic/README.md`
- `plugins/fieldkit-netwatch/DESIGN.md`
- `plugins/fieldkit-netwatch/PRODUCT.md`
- `plugins/fieldkit-netwatch/README.md`
- `plugins/fieldkit-netwatch/SPEC.md`
- `plugins/fieldkit-scrub/README.md`
- `plugins/fieldkit-tell/README.md`
- `plugins/fieldkit-xray/README.md`
- `site/DESIGN-NOTES.md`
- `site/DESIGN.md`
- `site/PRODUCT.md`
- `site/SCREEN-BRIEF.md`
- `site/assets/screenshots/README.md`
- `site/check_site.py`
- `site/docs/awcp.html`
- `site/docs/datadiff.html`
- `site/docs/debrief.html`
- `site/docs/index.html`
- `site/docs/mimic.html`
- `site/docs/netwatch.html`
- `site/docs/plugins.html`
- `site/docs/scrub.html`
- `site/docs/tell.html`
- `site/docs/xray.html`
- `site/index.html`
- `site/llms.txt`
- `site/privacy.html`
- `site/styles.css`
- `site/terms.html`
- `tests/test_site_release.py`
- `site/vercel.json`

## Exact file allowlist — orchestrator

- `specs/wp17-field-kit-branding.md`
- `brand/README.md`
- `brand/avatar.png`
- `brand/avatar.svg`
- `brand/github-social.png`
- `brand/github-social.svg`
- `brand/logo-16.png`
- `brand/logo-32.png`
- `brand/logo-48.png`
- `brand/logo-mono.png`
- `brand/logo-mono.svg`
- `brand/logo-reversed.png`
- `brand/logo-reversed.svg`
- `brand/logo.png`
- `brand/logo.svg`
- `brand/portfolio.png`
- `brand/portfolio.svg`
- `brand/references/brief.md`
- `brand/references/minimal-study.png`
- `brand/references/source-caliper.png`
- `brand/showcase.png`
- `brand/showcase.svg`
- `brand/website-social.png`
- `brand/website-social.svg`
- `brand/wordmark-reversed.png`
- `brand/wordmark-reversed.svg`
- `brand/wordmark.png`
- `brand/wordmark.svg`
- `scripts/build_brand.py`
- `site/assets/mark.svg`
- `site/assets/og.png`
- `site/assets/og.svg`
- `site/assets/wordmark.svg`

## Acceptance evidence

- README and all public site pages use the Field Kit name and new logo.
- Site metadata, structured data, image alt text and social artwork agree.
- SVGs are accessible, self-contained and have outlined wordmarks; logo variants
  share geometry, use at most two colors and remain legible at 16/32/48 px.
- GitHub preview is 1280×640; website sharing image remains 1200×630; portfolio
  image is 1600×900. Asset instructions identify each export's purpose.
- Existing website, docs, security, privacy and full test contracts pass; full
  pytest and Ruff output is retained in `TEST_STDOUT.log` for the PR.
- A browser check verifies desktop/mobile header, docs, and social card previews.
- Tracked screenshot hashes and the original dirty archive remain unchanged.
