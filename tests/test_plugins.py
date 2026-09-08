from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from fieldkit import plugins


def test_registry_names_and_packages_line_up():
    for name, known in plugins.REGISTRY.items():
        assert known.name == name
        assert known.package == f"fieldkit-{name}"
        assert known.summary


def test_resolve_prefers_local_checkout_in_monorepo():
    # running from the repo, every registered plugin should resolve to plugins/
    req = plugins.resolve_requirement("xray")
    assert req.endswith(f"plugins{Path('/').joinpath('fieldkit-xray').as_posix().replace('/', '/')}" ) or "fieldkit-xray" in req
    assert "git+" not in req


def test_resolve_git_source_builds_subdirectory_url():
    req = plugins.resolve_requirement("scrub", source="git")
    assert req.startswith("fieldkit-scrub @ git+")
    assert req.endswith("#subdirectory=plugins/fieldkit-scrub")


def test_resolve_extras_ride_along():
    req = plugins.resolve_requirement("tell", source="git", extras=["ml"])
    assert "fieldkit-tell[ml] @ git+" in req


def test_netwatch_resolves_from_the_workspace_and_loads_both_entry_points():
    req = plugins.resolve_requirement("netwatch")
    installed = plugins.installed_plugins()
    web = plugins.web_modules()

    assert "plugins/fieldkit-netwatch" in req
    assert "netwatch" in installed
    assert installed["netwatch"].load().info.name == "netwatch"
    assert web["netwatch"].load().STATIC_DIR.is_dir()


def test_resolve_unknown_tool_raises():
    with pytest.raises(KeyError):
        plugins.resolve_requirement("nope")
    with pytest.raises(ValueError):
        plugins.resolve_requirement("xray", source="carrier-pigeon")


def test_resolve_local_without_checkout_fails_loudly():
    with patch.object(plugins, "_monorepo_plugin_dir", return_value=None):
        with pytest.raises(FileNotFoundError):
            plugins.resolve_requirement("xray", source="local")


def test_installer_argv_prefers_uv_then_pip():
    with patch.object(plugins.shutil, "which", return_value="/opt/homebrew/bin/uv"):
        argv = plugins.installer_argv()
    assert argv[:2] == ["/opt/homebrew/bin/uv", "pip"]
    assert sys.executable in argv

    with patch.object(plugins.shutil, "which", return_value=None):
        argv = plugins.installer_argv()
    assert argv[:3] == [sys.executable, "-m", "pip"]


def test_cli_hints_at_plugin_add_for_missing_tools(capsys):
    from fieldkit import cli

    with patch.object(cli, "installed_plugins", return_value={}), patch.object(
        sys, "argv", ["fieldkit", "xray"]
    ):
        with pytest.raises(SystemExit) as exc:
            cli.main()
    assert exc.value.code == 2
    err = capsys.readouterr().err
    assert "fieldkit plugin add xray" in err


def test_web_app_serves_plugin_listing():
    from fastapi.testclient import TestClient

    from fieldkit.web import create_app

    client = TestClient(create_app(), base_url="http://localhost")
    payload = client.get("/api/plugins").json()
    names = {row["name"] for row in payload["plugins"]}
    assert set(plugins.REGISTRY) <= names


def test_wheelhouse_requirements_stay_bare():
    assert plugins.package_requirement("xray") == "fieldkit-xray"
    assert plugins.package_requirement("tell", extras=["ml"]) == "fieldkit-tell[ml]"


def test_update_with_uv_never_upgrades_the_core(monkeypatch):
    seen = {}

    def fake_run(argv, check):
        seen["argv"] = argv

        class Done:
            returncode = 0

        return Done()

    monkeypatch.setattr(plugins.subprocess, "run", fake_run)
    monkeypatch.setattr(plugins.shutil, "which", lambda name: "/opt/homebrew/bin/uv")
    plugins.run_installer(
        ["fieldkit-netwatch", "fieldkit-tell[ml] @ git+https://example.invalid/r.git#subdirectory=x"],
        upgrade=True,
        find_links="/tmp/wheels",
    )
    argv = seen["argv"]

    # PyPI has an unrelated `fieldkit`; a bare --upgrade would swap our core for it
    assert "--upgrade" not in argv
    assert argv[argv.index("--upgrade-package") + 1] in {"fieldkit-netwatch", "fieldkit-tell"}
    assert argv.count("--upgrade-package") == 2
    assert argv.count("--reinstall-package") == 2
    assert "fieldkit" not in argv


def test_update_with_pip_keeps_plain_upgrade(monkeypatch):
    seen = {}

    def fake_run(argv, check):
        seen["argv"] = argv

        class Done:
            returncode = 0

        return Done()

    monkeypatch.setattr(plugins.subprocess, "run", fake_run)
    monkeypatch.setattr(plugins.shutil, "which", lambda name: None)
    plugins.run_installer(["fieldkit-xray"], upgrade=True)
    assert "--upgrade" in seen["argv"]
    assert "--upgrade-package" not in seen["argv"]


def test_run_installer_threads_find_links_through(monkeypatch):
    seen = {}

    def fake_run(argv, check):
        seen["argv"] = argv

        class Done:
            returncode = 0

        return Done()

    monkeypatch.setattr(plugins.subprocess, "run", fake_run)
    plugins.run_installer(["fieldkit-xray"], find_links="/tmp/wheels")
    assert "--find-links" in seen["argv"]
    assert "/tmp/wheels" in seen["argv"]
    assert seen["argv"][-1] == "fieldkit-xray"
