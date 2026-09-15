# fieldkit-xray

Profile tabular files and highlight schema, missing values, and possible PII.

This plugin is part of [Fieldkit](https://github.com/myrrazor/fde-fieldkit).
It is not published to PyPI yet. From a checkout of the repository:

```bash
uv sync --locked --all-packages
uv run fieldkit xray examples/customers.csv
```

See the in-repo docs at [`site/docs/xray.html`](../../site/docs/xray.html)
for command options and boundaries. A hosted copy may exist at
fde-tools.vercel.app but can be SSO-gated. Source contributions, support, and private
security reports follow the policies in the main repository.

Licensed under MIT; see `LICENSE`. Bundled third-party notices, when present,
are included in `licenses/` and in the built distribution.
