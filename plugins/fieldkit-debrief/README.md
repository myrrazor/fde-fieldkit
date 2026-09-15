# fieldkit-debrief

Keep local work notes and turn them into weekly Markdown or HTML reports.

This plugin is part of [Fieldkit](https://github.com/myrrazor/fde-fieldkit).
It is not on PyPI; the PyPI project named `fieldkit` is unrelated. Install the
GitHub Release wheels by explicit path (see the repository README), then
`fieldkit plugin add debrief --wheelhouse <wheels-dir>`. A pinned `v0.2.0`
checkout also works:

```bash
uv sync --locked --all-packages
uv run fieldkit debrief report
```

Docs: in-repo [`site/docs/debrief.html`](../../site/docs/debrief.html) and
https://fde-tools-review.vercel.app/docs/debrief.html. If the hosted page is
unreachable, use the in-repo copy. Source contributions, support, and private
security reports follow the policies in the main repository.

Licensed under MIT; see `LICENSE`. Bundled third-party notices, when present,
are included in `licenses/` and in the built distribution.
