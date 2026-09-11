# fieldkit-awcp

Check AI workload specs, diff two versions, and score recorded golden suites.

This plugin is part of [Fieldkit](https://github.com/myrrazor/fde-fieldkit).
It is not published to PyPI yet. From a checkout of the repository:

```bash
uv sync --locked --all-packages
uv run fieldkit awcp check examples/awcp/support-ticket-triage.yaml
```

See the in-repo docs at [`site/docs/awcp.html`](../../site/docs/awcp.html) for command options and boundaries. A hosted copy may exist at fde-tools.vercel.app but can be SSO-gated. Scoring uses recorded cases; it does not
call a model or a control plane. Source contributions, support, and private
security reports follow the policies in the main repository.

Licensed under MIT; see `LICENSE`. Bundled third-party notices, when present,
are included in `licenses/` and in the built distribution.
