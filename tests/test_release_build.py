from __future__ import annotations

import importlib.util
import json
import subprocess
import tarfile
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def _load_packager():
    spec = importlib.util.spec_from_file_location(
        "build_release", ROOT / "scripts" / "build_release.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def packager():
    return _load_packager()


def _touch_expected(packager, directory: Path, version: str = "0.2.0") -> list[Path]:
    projects = packager.workspace_projects(ROOT)
    assert packager.release_version(projects) == version
    paths = []
    for name in packager.expected_distribution_names(projects):
        path = directory / name
        path.write_bytes(b"payload-" + name.encode())
        paths.append(path)
    return paths


def test_workspace_projects_cover_core_and_eight_plugins(packager) -> None:
    projects = packager.workspace_projects(ROOT)
    names = [project["name"] for project in projects]
    assert names[0] == "fieldkit"
    assert set(names) == set(packager.WHEEL_PACKAGES)
    assert packager.release_version(projects) == "0.2.0"
    expected = packager.expected_distribution_names(projects)
    assert len(expected) == 18
    assert "fieldkit-0.2.0-py3-none-any.whl" in expected
    assert "fieldkit_xray-0.2.0.tar.gz" in expected
    assert "fieldkit-xray-0.2.0.tar.gz" not in expected


def test_unexpected_distribution_names_keep_notes_and_reject_extras(packager, tmp_path: Path) -> None:
    (tmp_path / "fieldkit-0.1.0-py3-none-any.whl").write_bytes(b"old")
    (tmp_path / "fieldkit_wrong-0.2.0-py3-none-any.whl").write_bytes(b"wrong")
    (tmp_path / "unrelated-1.0-py3-none-any.whl").write_bytes(b"other")
    (tmp_path / "notes.txt").write_text("keep me\n", encoding="utf-8")
    expected = set(packager.expected_distribution_names(packager.workspace_projects(ROOT)))
    unexpected = packager.unexpected_distribution_names(
        tmp_path, expected, "fieldkit-0.2.0-wheels.tar.gz"
    )
    assert unexpected == [
        "fieldkit-0.1.0-py3-none-any.whl",
        "fieldkit_wrong-0.2.0-py3-none-any.whl",
        "unrelated-1.0-py3-none-any.whl",
    ]


def test_checksums_omit_self_and_use_basenames(packager, tmp_path: Path) -> None:
    one = tmp_path / "fieldkit-0.2.0-py3-none-any.whl"
    two = tmp_path / "fieldkit_xray-0.2.0-py3-none-any.whl"
    one.write_bytes(b"aaa")
    two.write_bytes(b"bbb")
    dest = tmp_path / "SHA256SUMS"
    packager.write_sha256sums([one, two], dest)
    text = dest.read_text(encoding="utf-8")
    assert "SHA256SUMS" not in text
    assert str(tmp_path) not in text
    assert f"{packager.sha256_file(one)}  {one.name}\n" in text
    assert f"{packager.sha256_file(two)}  {two.name}\n" in text


def test_manifest_records_version_commit_and_hashes(packager, tmp_path: Path) -> None:
    wheel = tmp_path / "fieldkit-0.2.0-py3-none-any.whl"
    wheel.write_bytes(b"core")
    dest = tmp_path / "release-manifest.json"
    packager.write_manifest(
        version="0.2.0",
        commit="abc123",
        paths=[wheel],
        dest=dest,
    )
    payload = json.loads(dest.read_text(encoding="utf-8"))
    assert payload["version"] == "0.2.0"
    assert payload["source_commit"] == "abc123"
    assert payload["assets"] == [
        {"filename": wheel.name, "sha256": packager.sha256_file(wheel)}
    ]
    assert "/" not in payload["assets"][0]["filename"]


def test_wheels_bundle_is_deterministic_and_pathless(packager, tmp_path: Path) -> None:
    wheel = tmp_path / "fieldkit-0.2.0-py3-none-any.whl"
    wheel.write_bytes(b"core-wheel")
    first = tmp_path / "a.tar.gz"
    second = tmp_path / "b.tar.gz"
    examples = {"examples/customers.csv": b"id\n1\n"}
    packager.write_wheels_bundle(
        version="0.2.0", wheel_paths=[wheel], dest=first, examples=examples
    )
    packager.write_wheels_bundle(
        version="0.2.0", wheel_paths=[wheel], dest=second, examples=examples
    )
    assert first.read_bytes() == second.read_bytes()
    with tarfile.open(first, "r:gz") as archive:
        names = archive.getnames()
        assert names == sorted(names)
        assert "wheels/fieldkit-0.2.0-py3-none-any.whl" in names
        assert "INSTALL-0.2.0.txt" in names
        assert "examples/customers.csv" in names
        install = archive.extractfile("INSTALL-0.2.0.txt").read().decode("utf-8")
        assert "wheels/*.whl" in install
        for member in archive.getmembers():
            assert member.uid == 0
            assert member.gid == 0
            assert member.uname == ""
            assert member.gname == ""
            assert member.mtime == 0
            assert not member.name.startswith("/")
            assert ".." not in member.name.split("/")


def test_build_release_keeps_unknown_files_and_rejects_incomplete(
    packager, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    notes = tmp_path / "notes.txt"
    notes.write_text("keep me\n", encoding="utf-8")
    monkeypatch.setattr(packager, "run_uv_build", lambda output, root=ROOT: None)
    monkeypatch.setattr(packager, "check_distributions", lambda output: None)
    monkeypatch.setattr(packager, "source_commit", lambda root=ROOT: "deadbeef")

    with pytest.raises(RuntimeError, match="incomplete distributions"):
        packager.build_release(tmp_path, root=ROOT, run_build=True)
    assert notes.read_text(encoding="utf-8") == "keep me\n"

    _touch_expected(packager, tmp_path)
    hashed = packager.build_release(tmp_path, root=ROOT, run_build=True)
    assert notes.is_file()
    names = {path.name for path in hashed}
    assert "fieldkit-0.2.0-py3-none-any.whl" in names
    assert "fieldkit-0.2.0-wheels.tar.gz" in names
    assert "release-manifest.json" in names
    assert len(hashed) == 20
    checksums = (tmp_path / "SHA256SUMS").read_text(encoding="utf-8")
    assert checksums.count("\n") == 20
    assert "SHA256SUMS" not in checksums
    assert "release-manifest.json" in checksums
    assert "deadbeef" in (tmp_path / "release-manifest.json").read_text(encoding="utf-8")
    manifest = json.loads((tmp_path / "release-manifest.json").read_text(encoding="utf-8"))
    assert len(manifest["assets"]) == 19


def test_build_release_refuses_unexpected_distributions(
    packager, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "fieldkit_wrong-0.2.0-py3-none-any.whl").write_bytes(b"wrong")
    monkeypatch.setattr(packager, "run_uv_build", lambda output, root=ROOT: None)
    with pytest.raises(RuntimeError, match="unexpected distributions"):
        packager.build_release(tmp_path, root=ROOT)


def test_placeholder_script_fails_on_missing_and_tokens(tmp_path: Path) -> None:
    script = ROOT / "scripts" / "check-placeholders.sh"
    missing = subprocess.run(
        ["bash", str(script), str(tmp_path / "nope.md")],
        capture_output=True,
        text=True,
        check=False,
    )
    assert missing.returncode == 2
    assert "missing target" in missing.stderr

    dirty = tmp_path / "notes.md"
    dirty.write_text("TODO(launch): sample\n", encoding="utf-8")
    todo = subprocess.run(
        ["bash", str(script), str(dirty)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert todo.returncode == 1

    token = tmp_path / "blank.md"
    token.write_text("Hello {{PRODUCT}}\n", encoding="utf-8")
    blanks = subprocess.run(
        ["bash", str(script), str(token)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert blanks.returncode == 2

    clean = tmp_path / "ok.md"
    clean.write_text("Fieldkit 0.2.0\n", encoding="utf-8")
    ok = subprocess.run(
        ["bash", str(script), str(clean)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert ok.returncode == 0

    locked = tmp_path / "locked"
    locked.mkdir()
    secret = locked / "hidden.md"
    secret.write_text("safe\n", encoding="utf-8")
    locked.chmod(0)
    try:
        denied = subprocess.run(
            ["bash", str(script), str(locked)],
            capture_output=True,
            text=True,
            check=False,
        )
    finally:
        locked.chmod(0o755)
    assert denied.returncode == 2
    assert "search error" in denied.stderr or "unreadable" in denied.stderr


def test_contributor_yaml_parses() -> None:
    import yaml

    for relative in (
        ".github/ISSUE_TEMPLATE/bug.yml",
        ".github/ISSUE_TEMPLATE/config.yml",
        ".github/workflows/ci.yml",
        ".github/workflows/dep-audit.yml",
    ):
        payload = yaml.safe_load((ROOT / relative).read_text(encoding="utf-8"))
        assert payload
