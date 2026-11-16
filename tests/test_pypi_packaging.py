from __future__ import annotations

import importlib.util
import tomllib
from pathlib import Path

from fieldkit import plugins

ROOT = Path(__file__).resolve().parents[1]


def test_distribution_rename_preserves_entry_points():
    config = tomllib.loads((ROOT / "pyproject.toml").read_text())
    assert config["project"]["name"] == "fde-fieldkit"
    assert config["project"]["scripts"] == {"fieldkit": "fieldkit.cli:main"}
    for path in (ROOT / "plugins").glob("*/pyproject.toml"):
        plugin = tomllib.loads(path.read_text())
        assert "fde-fieldkit>=0.2.2" in plugin["project"]["dependencies"]
        assert "fieldkit" not in plugin["project"]["dependencies"]
        assert plugin["tool"]["uv"]["sources"]["fde-fieldkit"] == {"workspace": True}


def test_git_install_pins_renamed_core(monkeypatch):
    seen = []

    def version(name):
        seen.append(name)
        return "0.2.2"

    monkeypatch.setattr(plugins.metadata, "version", version)
    path = plugins._core_constraint(["x @ git+https://example.invalid/repo"])
    try:
        assert seen == ["fde-fieldkit"]
        assert path.read_text() == "fde-fieldkit==0.2.2\n"
    finally:
        path.unlink()


def test_pypi_upload_rejects_bundle_and_missing_files(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location(
        "check_pypi_release", ROOT / "scripts/check_pypi_release.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "check_distributions", lambda _: [])
    projects = module.workspace_projects()
    for name in module.expected_distribution_names(projects):
        (tmp_path / name).touch()
    assert module.check(tmp_path) == []
    (tmp_path / "fieldkit-0.2.2-wheels.tar.gz").touch()
    assert "extra=" in module.check(tmp_path)[0]
    (tmp_path / "fde_fieldkit-0.2.2.tar.gz").unlink()
    assert "fde_fieldkit-0.2.2.tar.gz" in module.check(tmp_path)[0]
