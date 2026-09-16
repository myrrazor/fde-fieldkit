# Releasing Field Kit

Manual GitHub Release for the current workspace versions. There is no publish
workflow. Do this from a clean, reviewed `main` after the repository checks
below have passed.

Field Kit is **not** uploaded to PyPI. The PyPI project named `fieldkit` is
unrelated. Every Field Kit wheel must be installed by explicit local path.

## Preconditions

- Working tree is the reviewed public `main` commit you intend to tag.
- Python 3.12+, `uv` 0.10.3 (CI pin), and `gh` auth for `myrrazor/fde-fieldkit`.
- `dist/` has no extra `.whl` / `.tar.gz` files beyond the current 18
  distributions and the generated wheel bundle.

## Checks

Record the transcript in untracked `TEST_STDOUT.log`.

```bash
uv lock --check
uv sync --locked --all-packages
uv run --locked ruff check .
uv run --locked pytest -q
uv run --locked python site/check_site.py
find src plugins site -type f -name '*.js' -print0 | xargs -0 -n1 node --check
bash scripts/check-public-privacy.sh
gitleaks git . --log-opts='--all --full-history' --redact
bash scripts/check-placeholders.sh docs README.md CHANGELOG.md SECURITY.md CONTRIBUTING.md LAUNCH_CHECKLIST.md site
```

## Build assets

```bash
uv run --locked python scripts/build_release.py dist
```

That command runs `uv build --all-packages` with `build-constraints.txt`
(`hatchling==1.32.0`), then `scripts/check_release_artifacts.py`. It must
produce:

- nine wheels and nine sdists (underscore sdist names, e.g. `fieldkit_xray-0.2.0.tar.gz`)
- `fieldkit-0.2.0-wheels.tar.gz`
- `release-manifest.json` (18 distributions + the bundle)
- `SHA256SUMS` covering those 19 files plus the manifest (20 entries; does
  not list itself)

If the packager refuses unexpected distributions, remove the extra archive
files by name. Do not `rm -rf dist` if it contains unrelated notes.

## Verify the bundle locally

Stay at the repository root. Use a throwaway directory:

```bash
(
  smoke=$(mktemp -d)
  trap 'rm -rf "$smoke"' EXIT
  tar -xzf dist/fieldkit-0.2.0-wheels.tar.gz -C "$smoke"
  cd "$smoke"
  uv venv --seed --python 3.12 fresh
  uv pip install --python fresh/bin/python wheels/*.whl
  fresh/bin/fieldkit --version
  fresh/bin/fieldkit plugin list
)
(cd dist && shasum -a 256 -c SHA256SUMS)
```

`wheels/*.whl` selects every Field Kit wheel by path, including the core.
Do not `pip install fieldkit` from an index. Later plugin operations use
`--wheelhouse wheels`.

Confirm `release-manifest.json` `source_commit` equals `git rev-parse HEAD`.
If you downloaded only the bundle plus `SHA256SUMS`, verify that one file:

```bash
shasum -a 256 --ignore-missing --strict -c SHA256SUMS
```

That must print `fieldkit-0.2.0-wheels.tar.gz: OK` and fail if the bundle
hash is wrong or missing.

## Tag and draft

Upload only the validated archives, the bundle, the manifest, and
`SHA256SUMS` — never `dist/*`.

```bash
git tag -a v0.2.0 -m "v0.2.0"
git push origin v0.2.0
gh release create v0.2.0 --draft --verify-tag --title "v0.2.0" \
  --notes-file docs/releases/v0.2.0.md \
  dist/fieldkit-0.2.0-py3-none-any.whl \
  dist/fieldkit-0.2.0.tar.gz \
  dist/fieldkit_xray-0.2.0-py3-none-any.whl \
  dist/fieldkit_xray-0.2.0.tar.gz \
  dist/fieldkit_scrub-0.2.0-py3-none-any.whl \
  dist/fieldkit_scrub-0.2.0.tar.gz \
  dist/fieldkit_mimic-0.2.0-py3-none-any.whl \
  dist/fieldkit_mimic-0.2.0.tar.gz \
  dist/fieldkit_datadiff-0.2.0-py3-none-any.whl \
  dist/fieldkit_datadiff-0.2.0.tar.gz \
  dist/fieldkit_debrief-0.2.0-py3-none-any.whl \
  dist/fieldkit_debrief-0.2.0.tar.gz \
  dist/fieldkit_tell-0.2.0-py3-none-any.whl \
  dist/fieldkit_tell-0.2.0.tar.gz \
  dist/fieldkit_netwatch-0.2.0-py3-none-any.whl \
  dist/fieldkit_netwatch-0.2.0.tar.gz \
  dist/fieldkit_awcp-0.2.0-py3-none-any.whl \
  dist/fieldkit_awcp-0.2.0.tar.gz \
  dist/fieldkit-0.2.0-wheels.tar.gz \
  dist/release-manifest.json \
  dist/SHA256SUMS
```

## Publish

1. Confirm hosted CI and CodeQL on the tagged commit.
2. Confirm https://fde-tools-review.vercel.app is serving the static site.
   In-repo `site/` remains the fallback. Do not change the protected
   `fde-tools.vercel.app` alias here.
3. Download each GitHub asset and re-check `SHA256SUMS`.
4. Repeat the fresh-venv wheel install from the downloaded bundle.
5. `gh release edit v0.2.0 --draft=false`
6. Confirm https://github.com/myrrazor/fde-fieldkit/releases/latest returns the
   0.2.0 notes and that
   `.../releases/latest/download/fieldkit-0.2.0-wheels.tar.gz` is 200.

Announcement drafts live in `docs/launch/announcements.md`. Do not claim suite
results in the release notes until those checks are recorded.
