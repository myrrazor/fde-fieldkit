# fieldkit-xray

Profile tabular files and highlight schema, missing values, and possible PII.

This plugin is part of [Field Kit](https://github.com/myrrazor/fde-fieldkit).
It is not on PyPI; the PyPI project named `fieldkit` is unrelated. Install the
GitHub Release wheels by explicit path (see the repository README), then
`fieldkit plugin add xray --wheelhouse <wheels-dir>`. Use the v0.3.0 GitHub
bundle `fieldkit-0.3.0-wheels.tar.gz` (core distribution `fde-fieldkit`, wheel
`fde_fieldkit-0.3.0-py3-none-any.whl`) or a pinned v0.3.0 checkout. v0.3.0 is
not on PyPI:

```bash
uv sync --locked --all-packages
uv run fieldkit xray examples/customers.csv
```

Docs: in-repo [`site/docs/xray.html`](../../site/docs/xray.html) and
https://fde-fieldkit.vercel.app/docs/xray.html. If the hosted page is
unreachable, use the in-repo copy. Source contributions, support, and private
security reports follow the policies in the main repository.

Licensed under MIT; see `LICENSE`. Bundled third-party notices, when present,
are included in `licenses/` and in the built distribution.
