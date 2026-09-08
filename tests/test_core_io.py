from __future__ import annotations

from io import BytesIO, StringIO
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest
from openpyxl import Workbook

from fieldkit.core import io as core_io
from fieldkit.core import private_files
from fieldkit.core.io import MAX_DATASET_BYTES, detect_format, load_table, write_table
from fieldkit.core.private_files import atomic_write_private, ensure_private_regular_file
from fieldkit.core.report import render_page


@pytest.mark.parametrize(
    ("filename", "fmt", "rows"),
    [
        ("customers.csv", "csv", 150),
        ("customers_v2.csv", "csv", 152),
        ("events.jsonl", "jsonl", 200),
        ("orders.json", "json", 80),
        ("inventory.xlsx", "xlsx", 60),
        ("messy.tsv", "tsv", 50),
    ],
)
def test_loads_every_table_fixture(fixture_dir: Path, filename: str, fmt: str, rows: int) -> None:
    loaded = load_table(fixture_dir / filename)

    assert loaded.fmt == fmt
    assert loaded.source == filename
    assert len(loaded.df) == rows
    assert all(dtype.name == "string" for dtype in loaded.df.dtypes)


def test_messy_literals_become_missing(fixture_dir: Path) -> None:
    df = load_table(fixture_dir / "messy.tsv").df

    assert df["legacy_code"].isna().all()
    assert df["score"].isna().sum() == 7
    assert df["comment"].isna().sum() == 8
    assert df.loc[0, "label"].startswith("  ")


def test_nested_json_is_flattened(fixture_dir: Path) -> None:
    df = load_table(fixture_dir / "orders.json").df

    assert "shipping.city" in df.columns
    assert "shipping.country" in df.columns


@pytest.mark.parametrize(
    ("filename", "sample", "expected"),
    [
        ("table.CSV", b"a,b\n1,2\n", "csv"),
        (None, b"a\tb\n1\t2\n", "tsv"),
        (None, b'[{"a": 1}]', "json"),
        (None, b'{"a": 1}\n{"a": 2}\n', "jsonl"),
        (None, b"PK\x03\x04junk", "xlsx"),
    ],
)
def test_detect_format(filename: str | None, sample: bytes, expected: str) -> None:
    assert detect_format(filename, sample) == expected


def test_unknown_bytes_need_explicit_format() -> None:
    with pytest.raises(ValueError, match="pass fmt="):
        detect_format(None, b"there is no delimiter here")


def test_json_object_is_not_a_table() -> None:
    with pytest.raises(ValueError, match="top-level list"):
        load_table(BytesIO(b'{"not": "records"}'), filename="data.json")


def test_xlsx_merged_cells_emit_warning(tmp_path: Path) -> None:
    path = tmp_path / "merged.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["left", "right"])
    sheet.append(["value", None])
    sheet.merge_cells("A2:B2")
    workbook.save(path)

    loaded = load_table(path)

    assert loaded.warnings == ["sheet 'Sheet' contains merged cells"]


@pytest.mark.parametrize("fmt", ["csv", "tsv", "json", "jsonl"])
def test_write_table_text_round_trip(fmt: str) -> None:
    original = pd.DataFrame({"name": ["Ada", "Grace"], "score": ["10", pd.NA]})
    buffer = StringIO()

    write_table(original, buffer, fmt)
    loaded = load_table(BytesIO(buffer.getvalue().encode()), fmt=fmt)

    assert loaded.df.to_dict(orient="records") == [
        {"name": "Ada", "score": "10"},
        {"name": "Grace", "score": None},
    ]


def test_write_table_xlsx_round_trip() -> None:
    original = pd.DataFrame({"name": ["Ada"], "active": [True]})
    buffer = BytesIO()

    write_table(original, buffer, "xlsx")
    buffer.seek(0)
    loaded = load_table(buffer, filename="table.xlsx")

    assert loaded.df.to_dict(orient="records") == [{"name": "Ada", "active": "True"}]


@pytest.mark.parametrize("fmt", ["csv", "tsv", "xlsx"])
def test_spreadsheet_exports_neutralize_formula_cells_and_headers(fmt: str) -> None:
    original = pd.DataFrame(
        {
            "=formula_header": ["=2+2", "+cmd", "@SUM(A1:A2)", "-1+2", "\tcmd", "\rcmd"],
            "safe": ["-12.5", "ordinary", "42", pd.NA, "-1e3", " text"],
        }
    )
    buffer = BytesIO() if fmt == "xlsx" else StringIO()

    write_table(original, buffer, fmt)
    raw = buffer.getvalue() if fmt == "xlsx" else buffer.getvalue().encode()
    loaded = load_table(BytesIO(raw), filename=f"table.{fmt}")

    assert list(loaded.df.columns)[0] == "'=formula_header"
    guarded = list(loaded.df.iloc[:, 0].dropna())
    assert guarded[:5] == [
        "'=2+2",
        "'+cmd",
        "'@SUM(A1:A2)",
        "'-1+2",
        "'\tcmd",
    ]
    assert guarded[5] in {"'\rcmd", "'\ncmd"}  # openpyxl normalizes CR to LF
    assert loaded.df["safe"].dropna().tolist() == [
        "-12.5",
        "ordinary",
        "42",
        "-1e3",
        " text",
    ]


def test_json_export_preserves_formula_like_strings() -> None:
    original = pd.DataFrame({"value": ["=2+2"]})
    buffer = StringIO()

    write_table(original, buffer, "json")

    assert '"=2+2"' in buffer.getvalue()


def test_xlsx_uncompressed_size_uses_dataset_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeArchive:
        def __init__(self, _source: object):
            pass

        def __enter__(self) -> FakeArchive:
            return self

        def __exit__(self, *_args: object) -> None:
            pass

        def infolist(self) -> list[SimpleNamespace]:
            return [SimpleNamespace(file_size=MAX_DATASET_BYTES + 1)]

    monkeypatch.setattr(core_io, "ZipFile", FakeArchive)

    with pytest.raises(ValueError, match="XLSX expands beyond the 50 MB"):
        core_io._validate_xlsx_archive(b"PK")


def test_atomic_private_write_is_owner_only_and_preserves_old_file_on_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "mapping.json"
    atomic_write_private(path, b"first")

    assert path.read_bytes() == b"first"
    assert path.stat().st_mode & 0o777 == 0o600

    def fail_replace(_source: object, _dest: object) -> None:
        raise OSError("synthetic replace failure")

    monkeypatch.setattr(private_files.os, "replace", fail_replace)

    with pytest.raises(OSError, match="synthetic replace failure"):
        atomic_write_private(path, b"second")

    assert path.read_bytes() == b"first"
    assert list(tmp_path.iterdir()) == [path]


def test_private_regular_file_rejects_symlinks(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.write_text("do not touch", encoding="utf-8")
    link = tmp_path / "private"
    link.symlink_to(target)

    with pytest.raises(OSError):
        ensure_private_regular_file(link)

    assert target.read_text(encoding="utf-8") == "do not touch"


def test_base_report_escapes_context() -> None:
    rendered = render_page("base.html", title="<customer>")

    assert "&lt;customer&gt;" in rendered
    assert "<style>" in rendered
