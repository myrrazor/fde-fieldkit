# fieldkit-datadiff

Explain schema and keyed-row changes between two dumps.

This plugin is part of [Field Kit](https://github.com/myrrazor/fde-fieldkit).
It is not on PyPI; the PyPI project named `fieldkit` is unrelated. Install the
GitHub Release wheels by explicit path (see the repository README), then
`fieldkit plugin add datadiff --wheelhouse <wheels-dir>`. A pinned `v0.2.0`
checkout also works:

```bash
uv sync --locked --all-packages
uv run fieldkit datadiff examples/customers.csv examples/customers_v2.csv
```

Docs: in-repo [`site/docs/datadiff.html`](../../site/docs/datadiff.html) and
https://fde-fieldkit.vercel.app/docs/datadiff.html. If the hosted page is
unreachable, use the in-repo copy. Source contributions, support, and private
security reports follow the policies in the main repository.

Licensed under MIT; see `LICENSE`. Bundled third-party notices, when present,
are included in `licenses/` and in the built distribution.
