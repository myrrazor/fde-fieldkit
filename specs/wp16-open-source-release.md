# WP16 — first public GitHub release

## Outcome

Publish version 0.2.0 from reviewed public main with all nine Python packages,
checksums, a tested fresh installation, clear release and contribution guidance,
and a publicly usable website with a release link. Keep the existing MIT license,
package names, screenshots, tool behavior, and explicit network-consent boundary.
The PyPI project named fieldkit is unrelated: this release is distributed through
GitHub assets, and every wheel installation must explicitly select our core wheel.

## Allowed files

- specs/wp16-open-source-release.md
- README.md
- CHANGELOG.md
- SECURITY.md
- CONTRIBUTING.md
- LAUNCH_CHECKLIST.md
- build-constraints.txt
- docs/RELEASING.md
- docs/releases/v0.2.0.md
- docs/launch/announcements.md
- scripts/build_release.py
- scripts/check_release_artifacts.py
- scripts/check-placeholders.sh
- .github/ISSUE_TEMPLATE/bug.yml
- .github/ISSUE_TEMPLATE/config.yml
- .github/pull_request_template.md
- .github/workflows/ci.yml
- tests/test_open_source_release.py
- tests/test_docs_contract.py
- tests/test_site_release.py
- tests/test_release_build.py
- tests/test_api.py
- tests/test_ci_config.py
- plugins/fieldkit-tell/src/fieldkit_tell/sentences.py
- plugins/fieldkit-tell/src/fieldkit_tell/web.py
- plugins/fieldkit-tell/tests/test_tell_signals.py
- plugins/fieldkit-xray/README.md
- plugins/fieldkit-scrub/README.md
- plugins/fieldkit-mimic/README.md
- plugins/fieldkit-datadiff/README.md
- plugins/fieldkit-debrief/README.md
- plugins/fieldkit-tell/README.md
- plugins/fieldkit-netwatch/README.md
- plugins/fieldkit-awcp/README.md
- site/index.html
- site/docs/index.html
- site/docs/plugins.html
- site/llms.txt
- site/check_site.py
- site/vercel.json
- site/PRODUCT.md
- site/SCREEN-BRIEF.md
- site/assets/og.svg
- site/assets/og.png

Additional allowed files, for canonical documentation URL replacement only:

- pyproject.toml
- plugins/fieldkit-xray/pyproject.toml
- plugins/fieldkit-scrub/pyproject.toml
- plugins/fieldkit-mimic/pyproject.toml
- plugins/fieldkit-datadiff/pyproject.toml
- plugins/fieldkit-debrief/pyproject.toml
- plugins/fieldkit-tell/pyproject.toml
- plugins/fieldkit-netwatch/pyproject.toml
- plugins/fieldkit-awcp/pyproject.toml
- site/docs/xray.html
- site/docs/scrub.html
- site/docs/mimic.html
- site/docs/datadiff.html
- site/docs/debrief.html
- site/docs/tell.html
- site/docs/netwatch.html
- site/docs/awcp.html
- site/privacy.html
- site/terms.html
- site/robots.txt
- site/sitemap.xml
- site/.well-known/security.txt

Replace the protected fde-tools.vercel.app alias with the existing public production
address https://fde-tools-review.vercel.app in current project documentation URLs.
Regenerate the static CSP hash after JSON-LD URL changes. No package versions or
dependency declarations change.

The protected shorter alias must remain unchanged unless the owner explicitly
approves its public access change. Using the already-public production hostname
does not modify that access boundary.

No core changes, dependency additions, unrelated refactors, image recaptures,
package renaming, or PyPI publishing. Build-only constraints may pin the existing
Hatchling backend. The Tell changes are limited to the existing CodeQL findings:
linear-time sentence/Markdown recognition and safe server-generated consent cookies.
The site checker must parse inline scripts as HTML instead of using a tag-filter regex.

## Evidence

Run the required full tests, Ruff, JavaScript syntax, static-site, privacy/history,
secret and dependency audits, distribution checks, and clean-environment wheel
installation. Test long adversarial text without expensive stress loops, cookie
rotation and consent rejection, malformed script closing tags, release package
completeness, metadata versions, and checksum generation. Verify hosted CI and
CodeQL for the final main commit, then public asset downloads and the installed
version. Keep full local suite output in untracked TEST_STDOUT.log.

## Publication ownership

Grok implements and leaves a dirty diff. The user-appointed Codex orchestrator
reviews, commits, submits and integrates the release PR, tags main, creates the
GitHub release, uploads verified assets, and deploys the existing static website.
Announcements are drafts only. Preserve the original dirty private-archive checkout.
