# fieldkit-datadiff

Compare schemas, keyed rows, and distributions across tabular snapshots.

This plugin is part of [Fieldkit](https://github.com/myrrazor/fde-fieldkit).
It is not published to PyPI yet. From a checkout of the repository:

```bash
uv sync --locked --all-packages
uv run fieldkit datadiff examples/customers.csv examples/customers_v2.csv
```

See the [tool documentation](https://fde-tools.vercel.app/docs/datadiff.html)
for command options and boundaries. Source contributions, support, and private
security reports follow the policies in the main repository.

Licensed under MIT; see `LICENSE`. Bundled third-party notices, when present,
are included in `licenses/` and in the built distribution.
