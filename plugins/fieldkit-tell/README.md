# fieldkit-tell

Inspect writing for local stylistic signals. Optional classifiers need explicit consent and are not evidence of authorship.

This plugin is part of [Field Kit](https://github.com/myrrazor/fde-fieldkit).
It is not on PyPI; the PyPI project named `fieldkit` is unrelated. Install the
GitHub Release wheels by explicit path (see the repository README), then
`fieldkit plugin add tell --wheelhouse <wheels-dir>`. A pinned `v0.2.0`
checkout also works:

```bash
uv sync --locked --all-packages
uv run fieldkit tell check draft.md
```

Docs: in-repo [`site/docs/tell.html`](../../site/docs/tell.html) and
https://fde-fieldkit.vercel.app/docs/tell.html. If the hosted page is
unreachable, use the in-repo copy. Source contributions, support, and private
security reports follow the policies in the main repository.

Licensed under MIT; see `LICENSE`. Bundled third-party notices, when present,
are included in `licenses/` and in the built distribution.
