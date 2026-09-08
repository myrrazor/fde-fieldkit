# Contributing

Fieldkit is a local toolkit for the messy parts of field engineering. Small,
reproducible fixes are welcome. For a new tool or a change to the network boundary,
open an issue with the use case before investing in a large implementation.

## Set up

Install Python 3.12 or newer and [uv](https://docs.astral.sh/uv/), then:

```bash
git clone https://github.com/myrrazor/fde-fieldkit.git
cd fde-fieldkit
uv sync --locked --all-packages
uv run fieldkit --help
```

The checkout installs the core and all seven plugins in editable mode. No
production credentials are needed for development or the default test suite.
Optional machine-level Netwatch checks need permission to inspect processes or
bind loopback sockets. Never use customer files or a live credential as a fixture.

## Make a change

Create a feature branch from `dev`, keep the change focused, and open a pull
request against `testing`. Maintainers promote accepted changes to `main`.
Use a conventional commit subject with the issue number when there is one;
`(#0)` is the convention for maintenance without an issue.

Core code lives in `src/fieldkit`. Plugins live in `plugins/fieldkit-<tool>` and
import the shared core, not one another. Public functions need type hints and
useful API documentation. If behavior or a command changes, update its tests,
README or tool docs, and the Unreleased changelog entry in the same pull request.
See [AGENTS.md](AGENTS.md) for the runtime boundaries and work-package conventions.

## Check the result

Run the same checks as CI before asking for review:

```bash
uv lock --check
uv sync --locked --all-packages
uv run --locked ruff check .
uv run --locked pytest -q
python3 site/check_site.py
find src plugins site -type f -name '*.js' -print0 | xargs -0 -n1 node --check
bash scripts/check-public-privacy.sh
gitleaks git . --log-opts='--all --full-history' --redact
uv build --all-packages
python3 scripts/check_release_artifacts.py dist
```

JavaScript syntax checks need Node.js. Secret checks use Gitleaks; CI downloads
an exact upstream release and verifies its SHA-256 digest. There is no JavaScript
build step. Keep test output local or attach a sanitized excerpt to the pull
request. `TEST_STDOUT.log`, databases, mappings, caches, and credentials must stay
untracked.

The privacy check inspects current files and every stored Git object, including
unreachable history. Maintainers may supply a private newline-delimited blocklist
as `PUBLIC_PRIVACY_BLOCKLIST_B64`; keep its contents outside the repository and
never echo it to a log. Base64 is only an encoding. Generic privacy checks run
without that optional value.

Dependency advisories run in the separate `dep-audit` workflow. To reproduce it:

```bash
uv export --locked --all-packages --all-extras --no-dev \
  --no-emit-workspace --no-hashes --no-annotate --no-header \
  --output-file requirements-audit.txt
uv tool run --from pip-audit==2.10.1 pip-audit \
  --requirement requirements-audit.txt --no-deps --disable-pip
```

## Bugs and security

Use [issues](https://github.com/myrrazor/fde-fieldkit/issues) for ordinary bugs.
Include the command, platform, package version, expected result, actual result,
and a minimal synthetic input. Remove file contents, personal paths, hostnames,
and credentials that are not needed to reproduce the problem.

Use [private security reporting](SECURITY.md) for vulnerabilities. Participation
is covered by the [code of conduct](CODE_OF_CONDUCT.md). By submitting a
contribution, you agree that it may be distributed under the project's
[MIT License](LICENSE); retain notices for third-party work.
