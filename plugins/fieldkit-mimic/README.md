# fieldkit-mimic

Learn an editable YAML spec and generate seeded synthetic rows.

This plugin is part of [Field Kit](https://github.com/myrrazor/fde-fieldkit).
It is not on PyPI; the PyPI project named `fieldkit` is unrelated. Install the
GitHub Release wheels by explicit path (see the repository README), then
`fieldkit plugin add mimic --wheelhouse <wheels-dir>`. A pinned `v0.2.0`
checkout also works:

```bash
uv sync --locked --all-packages
uv run fieldkit mimic learn examples/customers.csv -o spec.yaml
```

Docs: in-repo [`site/docs/mimic.html`](../../site/docs/mimic.html) and
https://fde-fieldkit.vercel.app/docs/mimic.html. If the hosted page is
unreachable, use the in-repo copy. Non-PII source values can remain in a
learned spec. Source contributions, support, and private security reports
follow the policies in the main repository.

Licensed under MIT; see `LICENSE`. Bundled third-party notices, when present,
are included in `licenses/` and in the built distribution.
