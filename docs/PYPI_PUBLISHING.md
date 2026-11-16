# PyPI publishing setup

Preparation only: this workflow does not publish on a push, tag, or pull request.
Do not upload until the owner approves the release and all nine publisher records
are configured. The distribution is `fde-fieldkit`; the import and CLI remain
`fieldkit`. Never install the unrelated PyPI distribution named `fieldkit`.
Version 0.2.2 is preserved here. Existing GitHub v0.2.2 assets are historical and
must not be overwritten: build the renamed packages from the reviewed new commit.

## One-time setup (owner)

At https://pypi.org/manage/account/publishing/ add a pending GitHub publisher for
each project below (or use its Publishing settings if you already own it):

- `fde-fieldkit`
- `fieldkit-xray`
- `fieldkit-scrub`
- `fieldkit-mimic`
- `fieldkit-datadiff`
- `fieldkit-debrief`
- `fieldkit-tell`
- `fieldkit-netwatch`
- `fieldkit-awcp`

Use the same fields for all nine:

| Field | Value |
| --- | --- |
| Owner | `myrrazor` |
| Repository | `fde-fieldkit` |
| Workflow filename | `publish-pypi.yml` |
| Environment | `pypi` |

A pending publisher does not reserve a project name. A 404 is not a guarantee
that a name can be registered. Check all nine names and permissions before release.
Never register a publisher on an unrelated project.

In GitHub repository Settings → Environments, create `pypi`, restrict deployment
to `main`, and require maintainer approval. Enable prevention of self-review when
a second trusted reviewer is available. Do this before enabling any upload run.
No long-lived PyPI secret is needed for Actions. The build job has no OIDC write
permission; the isolated publish job receives only validated artifacts and the
short-lived publishing permission.

## Build-only rehearsal and approved release

After review and merge, run **Build and publish PyPI distributions** on `main`.
Enter the full reviewed commit SHA as `expected_sha`; leave `publish` unchecked.
The job verifies the SHA, lockfile, tests, lint, and all 18 wheel/sdist artifacts.
It uploads an Actions artifact, not a PyPI release. Download it and smoke-test:

```bash
uv venv --python 3.12 /tmp/fieldkit-pypi-smoke
uv pip install --python /tmp/fieldkit-pypi-smoke/bin/python pypi-dist/*.whl
/tmp/fieldkit-pypi-smoke/bin/fieldkit --version
/tmp/fieldkit-pypi-smoke/bin/fieldkit plugin list
```

Use a fresh temporary path rather than an existing environment. Confirm all eight
plugins and `import fieldkit` work. After separate release approval, run again on
the same reviewed SHA with `publish` checked, then approve the environment gate.
The default publisher keeps attestations enabled. Upload is not atomic across
nine projects: on a partial failure inspect which files arrived before retrying;
do not silently skip mismatched existing versions. PyPI filenames cannot be reused.

After successful upload, verify each project, install `fde-fieldkit==0.2.2` plus
the eight plugins into a fresh environment from PyPI, then update user-facing
installation guidance. The existing CLI's explicit PyPI plugin-install guard
remains unchanged until publication is verified; source/wheelhouse installs work.

## Manual fallback if Actions cannot run

Local publishing does not consume Actions minutes. It is still a separately
approved release, not an automatic fallback. From a clean reviewed checkout:

```bash
uv lock --check
uv sync --locked --all-packages
uv run --locked ruff check .
uv run --locked pytest -q
uv build --all-packages --build-constraint build-constraints.txt --out-dir pypi-dist
uv run --locked python scripts/check_pypi_release.py pypi-dist
uvx --from twine twine check pypi-dist/*
# Only after explicit release approval, with the owner entering credentials:
uvx --from twine twine upload pypi-dist/*
```

Use a fresh output directory. The checker rejects stale wheels, release bundles,
and other extra files. Twine prompts for username `__token__` and a PyPI API token;
do not paste a token into chat, source, shell arguments, or GitHub. For first-time
projects, local upload may require an account-scoped token (broader than OIDC).
The owner should create/enter it themselves and revoke it after the upload;
prefer project-scoped tokens once projects exist. Local uploads do not inherit
GitHub OIDC or its automatic attestations. This preparation creates no tokens,
publishers, environment permissions, uploads, tags, or releases.

References: https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/
and https://docs.pypi.org/trusted-publishers/adding-a-publisher/.
