# Launch checklist — Fieldkit

Reusable release procedure for maintainers. Unchecked boxes are not evidence
that the step happened. Record completion separately. This is not an
attestation that unpublished GitHub assets, deploys, or posts already exist.

Omit donation, personal-site, analytics, new branding, and registry-account
work; those are out of scope for this project.

Automated placeholder gate:

```bash
bash scripts/check-placeholders.sh docs README.md CHANGELOG.md SECURITY.md CONTRIBUTING.md LAUNCH_CHECKLIST.md site
```

Must exit 0 before tagging. The script does not recurse into `.venv`, `.git`,
`dist`, or test fixtures.

## Placeholders

- [ ] `check-placeholders.sh` on the paths above exits 0
- [ ] No double-brace blanks or unconfirmed launch-TODO markers in README, docs, site, changelog, security policy, or this checklist

## Repo

- [ ] `LICENSE` present (MIT)
- [ ] `CHANGELOG.md` has a dated 0.2.0 section and a fresh Unreleased heading
- [ ] `SECURITY.md` describes GitHub 0.2.0 plus current `main`, with no LTS promise
- [ ] Public identity is the project GitHub links and `myrrazor` noreply only

## README and site

- [ ] README 5-second test: name, what it is, hub screenshot, GitHub install
- [ ] Existing screenshots remain; no recaptures in this work package
- [ ] https://github.com/myrrazor/fde-fieldkit/releases/latest is linked from README and the site hero
- [ ] Copy says Not on PyPI; install Fieldkit wheels with `wheels/*.whl`
- [ ] Hosted site copy is https://fde-tools-review.vercel.app with in-repo `site/` fallback
- [ ] `python3 site/check_site.py` exits 0

## Release packaging

- [ ] `python3 scripts/build_release.py dist` on the intended commit
- [ ] 9 wheels + 9 underscore sdists + `fieldkit-0.2.0-wheels.tar.gz` + manifest + `SHA256SUMS` (20 checksummed assets)
- [ ] Fresh venv install uses `wheels/*.whl` only (no `pip install fieldkit`)
- [ ] `fieldkit --version` prints `0.2.0`
- [ ] `(cd dist && shasum -a 256 -c SHA256SUMS)` passes

## Publication

- [ ] Full suite, Ruff, JS syntax, privacy, secrets, dep-audit recorded
- [ ] Hosted CI and CodeQL on the final main commit
- [ ] `v0.2.0` tag on public `main`
- [ ] GitHub Release published with the named assets above (not `dist/*`)
- [ ] `releases/latest/download/fieldkit-0.2.0-wheels.tar.gz` returns 200
- [ ] https://fde-tools-review.vercel.app is the public site
- [ ] Downloaded assets match `SHA256SUMS`

## Announcements (drafts only)

- [ ] `docs/launch/announcements.md` is fact-only
- [ ] Community rules are checked before anyone posts
- [ ] No invented origin story, traction, quotas, or timings
