# fieldkit-scrub

Replace detected PII with deterministic synthetic values. Inspect output before sharing; detection can miss sensitive data.

This plugin is part of [Fieldkit](https://github.com/myrrazor/fde-fieldkit).
It is not published to PyPI yet. From a checkout of the repository:

```bash
uv sync --locked --all-packages
uv run fieldkit scrub examples/customers.csv -o customers_safe.csv
```

See the in-repo docs at [`site/docs/scrub.html`](../../site/docs/scrub.html)
for command options and boundaries. A hosted copy may exist at
fde-tools.vercel.app but can be SSO-gated. Source contributions, support, and private
security reports follow the policies in the main repository.

Licensed under MIT; see `LICENSE`. Bundled third-party notices, when present,
are included in `licenses/` and in the built distribution.
