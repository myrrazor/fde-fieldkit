# WP2 — scrub: deterministic PII pseudonymization

Read AGENTS.md. Core is frozen. The one non-negotiable property here is
**determinism**: same salt + same input value → same fake, across runs, processes,
and files. That's what keeps joins alive after scrubbing.

## Files you may create/edit

```
src/fieldkit/scrub/__init__.py
src/fieldkit/scrub/cli.py         # replace the stub
src/fieldkit/scrub/salt.py
src/fieldkit/scrub/engine.py
tests/test_scrub.py
```

## salt.py

```python
DEFAULT_SALT_PATH = Path.home() / ".fieldkit" / "salt"
def load_or_create_salt(path: Path = DEFAULT_SALT_PATH) -> bytes
```
32 random bytes on first call, file mode 0600, parent dir created. Reads back verbatim
after that. Tests always pass an explicit tmp path — never touch the real home in tests.

## engine.py

```python
@dataclass
class ScrubSummary:
    replaced: dict[str, int]                  # PIIKind value -> count
    by_column: dict[str, dict[str, int]]      # df mode only

class Scrubber:
    def __init__(self, salt: bytes, *, kinds: set[PIIKind] | None = None): ...
    def scrub_value(self, value: str, kind: PIIKind) -> str
    def scrub_text(self, text: str) -> tuple[str, ScrubSummary]
    def scrub_dataframe(self, table: LoadedTable) -> tuple[pd.DataFrame, ScrubSummary]
    mapping: dict[str, str]                   # original -> fake, filled as it works
```

Derivation — this exact scheme, don't improvise:
`n = int.from_bytes(hmac.new(salt, value.encode(), hashlib.sha256).digest()[:8], "big")`

- EMAIL: `faker.seed_instance(n)` → fake local@domain; preserve the original TLD.
- NAME: `faker.seed_instance(n)` → same word-count name (1 word → first name only,
  2 words → first + last).
- PHONE/SSN/CREDIT_CARD/IP: map digits in place from the HMAC digest stream —
  non-digit characters (dashes, parens, dots, spaces) stay exactly where they were.
  CREDIT_CARD: recompute the last digit so the fake still passes Luhn. IP: map each
  octet to digest_byte % 256, render as dotted quad (keeps it a valid IP, avoids
  .0/.255 edge concerns — clamp to 1..254).
  SSN: force area/group/serial into valid ranges (area 100–665 excluding 666,
  group 01–99, serial 0001–9999) so the fake is plausible but never the original.
- SECRET: `FK_SECRET_<first 8 hex of hmac>` — secrets get tombstoned, not faked.
- Caching: `self.mapping[value]` consulted first, so identical values are guaranteed
  identical fakes even beyond determinism of the scheme itself.
- Matching is on exact string bytes; no normalization ("+1 (555) 111-2222" and
  "5551112222" are different values — document this in the CLI help).

Column mode: `scan_dataframe` decides which columns carry which kinds (confidence
≥ 0.5, intersected with `kinds` filter); every non-null value in a flagged column gets
scrubbed with that column's top kind. Unflagged columns still get per-cell span scanning,
so sparse recognized PII is replaced. Text mode: `scan_text` per line, replace spans
right-to-left. After either mode, scan again and fail closed if any selected, recognized
PII remains outside a generated replacement. This is defense in depth, not a promise
that the scanner recognizes every possible identifier.

## cli.py

```
fieldkit scrub FILE -o OUT [--kinds email,phone,ssn,credit_card,ip,name,secret]
               [--salt-file PATH] [--mapping PATH] [--text]
```
- Output written in the input's format (`core.io.write_table`); `--text` (or non-tabular
  input, e.g. .log/.txt) → line mode, plain text out.
- Prints a summary table (kind → replacements, and per-column counts in df mode).
- `--mapping` writes `{original: fake}` JSON **only when the flag is given**, with a
  stderr warning that the mapping file is as sensitive as the original data. It is an
  atomic owner-only (0600) file; examples use `customers.mapping.json`, which matches
  the repository ignore rule.
- No `-o` → error, exit 1 (we never overwrite in place).
- The browser treats `.log` and `.txt` as UTF-8 text mode; all tabular formats use
  the same column-plus-cell behavior as the CLI.

## Acceptance

- Determinism: two separate Scrubber instances, same salt → byte-identical output for
  customers.csv; a different salt → different output.
- Join preservation: email column scrubbed in customers.csv and customers_v2.csv with
  the same salt → the set of scrubbed emails shared between the two files matches the
  overlap of the originals.
- Every scrubbed credit_card passes Luhn and != original; phone keeps `(nnn) nnn-nnnn`
  shape (regex assert); ssn keeps `nnn-nn-nnnn`; ip is a valid dotted quad != original.
- app.log via --text: zero raw planted emails/IPs/keys remain; `FK_SECRET_` present;
  line count unchanged.
- Mapping file exists iff --mapping passed; contents map original → fake.
- Emails in output are valid-shaped and preserve TLD (`.com` stays `.com`).
- pytest green, ruff clean.
