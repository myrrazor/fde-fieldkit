from __future__ import annotations

import os
import re
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from pathlib import Path

from fieldkit.core.private_files import ensure_private_regular_file


class Tag(StrEnum):
    WIN = "win"
    BLOCKER = "blocker"
    DECISION = "decision"
    NOTE = "note"
    NEXT = "next"


@dataclass
class Entry:
    """One timestamped engagement note."""

    id: int
    ts: str
    tag: Tag
    text: str


def default_db_path() -> Path:
    """Return the configured debrief database path."""

    configured = os.environ.get("FIELDKIT_DEBRIEF_DB")
    return Path(configured).expanduser() if configured else Path.home() / ".fieldkit" / "debrief.db"


# Kept for callers that imported the home default; prefer default_db_path().
DEFAULT_DB = Path.home() / ".fieldkit" / "debrief.db"

_WEEK_RE = re.compile(r"(?P<year>\d{4})-W(?P<week>\d{2})\Z")


class Store:
    """Small SQLite-backed engagement log."""

    def __init__(self, db_path: Path | None = None):
        self.db_path = db_path or default_db_path()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        if self.db_path.parent == Path.home() / ".fieldkit":
            self.db_path.parent.chmod(0o700)
        ensure_private_regular_file(self.db_path)
        with closing(self._connect()) as connection, connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS entries(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts TEXT NOT NULL,
                    tag TEXT NOT NULL,
                    text TEXT NOT NULL
                )
                """
            )

    def add(self, text: str, tag: Tag, ts: datetime | None = None) -> Entry:
        """Add an entry and return its persisted representation."""

        cleaned = text.strip()
        if not cleaned:
            raise ValueError("debrief notes can't be empty or whitespace-only")
        stamp = datetime.now() if ts is None else ts
        timestamp = stamp.isoformat()
        with closing(self._connect()) as connection, connection:
            cursor = connection.execute(
                "INSERT INTO entries(ts, tag, text) VALUES (?, ?, ?)",
                (timestamp, tag.value, cleaned),
            )
            entry_id = cursor.lastrowid
        if entry_id is None:
            raise sqlite3.DatabaseError("couldn't read the new entry id")
        return Entry(id=entry_id, ts=timestamp, tag=tag, text=cleaned)

    def list(self, *, week: str | None = None, tag: Tag | None = None) -> list[Entry]:
        """List entries in chronological order with optional week and tag filters."""

        target_week = _parse_week(week) if week is not None else None
        query = "SELECT id, ts, tag, text FROM entries"
        params: tuple[str, ...] = ()
        if tag is not None:
            query += " WHERE tag = ?"
            params = (tag.value,)
        query += " ORDER BY ts, id"

        with closing(self._connect()) as connection, connection:
            rows = connection.execute(query, params).fetchall()

        entries = [_entry_from_row(row) for row in rows]
        if target_week is None:
            return entries
        return [entry for entry in entries if _entry_week(entry) == target_week]

    def delete(self, entry_id: int) -> bool:
        """Delete an entry, returning whether it existed."""

        with closing(self._connect()) as connection, connection:
            cursor = connection.execute("DELETE FROM entries WHERE id = ?", (entry_id,))
        return cursor.rowcount > 0

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection


def _parse_week(week: str) -> tuple[int, int]:
    match = _WEEK_RE.fullmatch(week)
    if match is None:
        raise ValueError(f"invalid ISO week {week!r}; expected YYYY-WNN")
    year = int(match.group("year"))
    week_number = int(match.group("week"))
    try:
        date.fromisocalendar(year, week_number, 1)
    except ValueError as exc:
        raise ValueError(f"invalid ISO week {week!r}") from exc
    return year, week_number


def _entry_week(entry: Entry) -> tuple[int, int]:
    iso = datetime.fromisoformat(entry.ts).isocalendar()
    return iso.year, iso.week


def _entry_from_row(row: sqlite3.Row) -> Entry:
    return Entry(id=row["id"], ts=row["ts"], tag=Tag(row["tag"]), text=row["text"])
