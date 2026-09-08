# WP5 — debrief: engagement log → weekly stakeholder status

Read AGENTS.md. Core is frozen (you'll only use core.report's jinja env). Everything is
template-driven — zero LLM, zero network. stdlib sqlite3, no ORM.

## Files you may create/edit

```
src/fieldkit/debrief/__init__.py
src/fieldkit/debrief/cli.py       # replace the stub
src/fieldkit/debrief/store.py
src/fieldkit/debrief/report.py
src/fieldkit/debrief/templates/report.md.j2
src/fieldkit/debrief/templates/report.html.j2
tests/test_debrief.py
```

## store.py

```python
class Tag(StrEnum): WIN; BLOCKER; DECISION; NOTE; NEXT

@dataclass
class Entry:
    id: int; ts: str; tag: Tag; text: str        # ts ISO datetime, local time

DEFAULT_DB = Path.home() / ".fieldkit" / "debrief.db"

class Store:
    def __init__(self, db_path: Path = DEFAULT_DB): ...   # mkdir parent, create table
    def add(self, text: str, tag: Tag, ts: datetime | None = None) -> Entry
    def list(self, *, week: str | None = None, tag: Tag | None = None) -> list[Entry]
    def delete(self, entry_id: int) -> bool
```

- Schema: `entries(id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, tag TEXT NOT NULL, text TEXT NOT NULL)`.
- `week` is ISO like `"2026-W29"` — match `datetime.fromisoformat(ts).isocalendar()`.
  Handles year boundaries correctly (that's what isocalendar is for).
- Tests always pass a tmp_path db. Never touch the real home in tests.

## report.py

```python
@dataclass
class ReportData:
    title: str; week: str; date_range: str      # "Jul 13 – Jul 19, 2026"
    sections: list[tuple[str, list[Entry]]]     # fixed order, may be empty

def build_report(entries: list[Entry], week: str, *, title: str = "Weekly Status") -> ReportData
def render_markdown(r: ReportData) -> str
def render_html(r: ReportData) -> str
```

Section order (always all five, "Nothing logged." placeholder when empty):
Wins ← WIN · Decisions ← DECISION · In Progress ← NOTE · Blockers & Asks ← BLOCKER ·
Next Steps ← NEXT. Entries within a section in chronological order, rendered as
bullets (markdown) / list items (HTML). Markdown output must be byte-stable for fixed
inputs — no timestamps-of-generation, no randomness. HTML via core.report.render_page
using a template that extends base.html, tone: something you'd actually send a VP.

## cli.py

```
fieldkit debrief add "TEXT" --tag win|blocker|decision|note|next [--db PATH]
fieldkit debrief list [--week 2026-W29] [--tag win] [--db PATH]
fieldkit debrief report [--week 2026-W29] [-o status.md] [--html status.html] [--db PATH]
```
- `add` prints the created entry id + tag. `list` prints a rich table (id, ts, tag, text).
- `report` defaults to the current ISO week; no `-o`/`--html` → markdown to stdout.
- `delete` subcommand: `fieldkit debrief delete ID` → "deleted" or "no entry ID", exit 1
  on missing.

## Acceptance

- CRUD round-trip on tmp db; delete returns False/exit 1 for missing ids.
- Week filtering: entries planted across two ISO weeks including a Dec 29–Jan 4 style
  year boundary — list(week=…) picks exactly the right ones.
- build_report routes all five tags to the right sections; empty sections present with
  placeholder.
- render_markdown byte-stable: same entries → identical string twice; contains all five
  section headers.
- CLI: add → list shows it → report contains its text; --tag filter works.
- pytest green, ruff clean.
