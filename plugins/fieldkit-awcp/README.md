# fieldkit-awcp

Check AI workload specs, diff two versions, and score recorded golden suites.

This plugin is part of [Field Kit](https://github.com/myrrazor/fde-fieldkit).
It is not on PyPI; the PyPI project named `fieldkit` is unrelated. Install the
GitHub Release wheels by explicit path (see the repository README), then
`fieldkit plugin add awcp --wheelhouse <wheels-dir>`. A pinned `v0.2.0`
checkout also works:

```bash
uv sync --locked --all-packages
uv run fieldkit awcp check examples/awcp/support-ticket-triage.yaml
```

Docs: in-repo [`site/docs/awcp.html`](../../site/docs/awcp.html) and
https://fde-tools-review.vercel.app/docs/awcp.html. If the hosted page is
unreachable, use the in-repo copy. Scoring uses recorded cases; it does not
call a model or a control plane. Source contributions, support, and private
security reports follow the policies in the main repository.

Licensed under MIT; see `LICENSE`. Bundled third-party notices, when present,
are included in `licenses/` and in the built distribution.
