# fieldkit-tell

Inspect writing for local stylistic signals. Optional classifiers need explicit consent and are not evidence of authorship.

This plugin is part of [Fieldkit](https://github.com/myrrazor/fde-fieldkit).
It is not published to PyPI yet. From a checkout of the repository:

```bash
uv sync --locked --all-packages
uv run fieldkit tell check draft.md
```

See the in-repo docs at [`site/docs/tell.html`](../../site/docs/tell.html)
for command options and boundaries. A hosted copy may exist at
fde-tools.vercel.app but can be SSO-gated. Source contributions, support, and private
security reports follow the policies in the main repository.

Licensed under MIT; see `LICENSE`. Bundled third-party notices, when present,
are included in `licenses/` and in the built distribution.
