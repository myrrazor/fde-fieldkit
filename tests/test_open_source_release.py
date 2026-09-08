from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess
import sys
import tomllib
import zipfile

import pytest


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture

def artifact_checker(monkeypatch: pytest.MonkeyPatch):
    """Load the standalone checker the same way the release CLI resolves imports."""
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location(
        "check_release_artifacts", ROOT / "scripts" / "check_release_artifacts.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_workspace_packages_ship_their_license_and_readme() -> None:
    """A source license is insufficient if installed packages omit its grant."""
    paths = [ROOT / "pyproject.toml", *ROOT.glob("plugins/*/pyproject.toml")]
    for path in paths:
        project = tomllib.loads(path.read_text())["project"]
        assert project["license"] == "MIT"
        assert (path.parent / project["readme"]).is_file()
        assert project["urls"]["Repository"] == "https://github.com/myrrazor/fde-fieldkit"
        for relative in project["license-files"]:
            notice = (path.parent / relative).read_text()
            assert "Permission is hereby granted" in notice
            assert "Copyright" in notice


def test_public_release_has_security_contribution_and_license_guidance() -> None:
    for relative in (
        "LICENSE", "CHANGELOG.md", "CONTRIBUTING.md", "CODE_OF_CONDUCT.md", "SECURITY.md",
        "THIRD_PARTY_NOTICES.md", "tests/fixtures/README.md", "site/fonts/OFL.txt",
    ):
        assert (ROOT / relative).is_file()
    security = (ROOT / "SECURITY.md").read_text()
    assert "https://github.com/myrrazor/fde-fieldkit/security/advisories/new" in security
    assert "Do not open a public issue" in security
    assert "No public release tag or PyPI" in (ROOT / "CHANGELOG.md").read_text()


def _wheel(path: Path, *, include_license: bool = True, payload: bytes = b"safe\n") -> Path:
    metadata = b"Name: fieldkit\nVersion: 0.2.0\nLicense-Expression: MIT\nLicense-File: LICENSE\n\n"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("fieldkit-0.2.0.dist-info/METADATA", metadata)
        archive.writestr("fieldkit/data.txt", payload)
        if include_license:
            archive.writestr("fieldkit-0.2.0.dist-info/licenses/LICENSE", b"MIT notice\n")
    return path


def test_distribution_check_accepts_notices_and_rejects_missing_license(
    tmp_path: Path, artifact_checker,
) -> None:
    good = _wheel(tmp_path / "complete.whl")
    assert artifact_checker.check_archive(good, "fieldkit", ["LICENSE"]) == []
    incomplete = _wheel(tmp_path / "missing.whl", include_license=False)
    assert any("missing bundled notice" in item for item in
               artifact_checker.check_archive(incomplete, "fieldkit", ["LICENSE"]))


def test_distribution_check_rejects_private_data_without_echoing_it(
    tmp_path: Path, artifact_checker,
) -> None:
    private = ("someone" + "@" + "gmail.com").encode()
    wheel = _wheel(tmp_path / "private.whl", payload=private)
    errors = artifact_checker.check_archive(wheel, "fieldkit", ["LICENSE"])
    assert errors and "privacy check failed" in errors[0]
    assert private.decode() not in "\n".join(errors)


def test_distribution_cli_rejects_an_incomplete_workspace_build(tmp_path: Path) -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/check_release_artifacts.py"), str(tmp_path)],
        cwd=tmp_path, capture_output=True, text=True, check=False,
    )
    assert result.returncode == 1
    assert "expected one current distribution matching fieldkit-" in result.stdout
