"""Plugin discovery, the registry of known tools, and install plumbing.

Fieldkit tools ship as separate packages that expose a typer app in the
``fieldkit.plugins`` entry-point group (and, optionally, a web module in
``fieldkit.web``). The core stays small; this module is how it finds the rest.
"""

from __future__ import annotations

import importlib
import shutil
import subprocess
import sys
from dataclasses import dataclass
from importlib import metadata
from pathlib import Path

GROUP_CLI = "fieldkit.plugins"
GROUP_WEB = "fieldkit.web"

REPO_GIT = "https://github.com/myrrazor/fde-fieldkit.git"

SOURCES = ("local", "git", "pypi")


@dataclass(frozen=True)
class KnownPlugin:
    name: str
    package: str
    summary: str


# the eight field tools — a new tool is one line here plus its package under plugins/
REGISTRY: dict[str, KnownPlugin] = {
    plugin.name: plugin
    for plugin in (
        KnownPlugin("xray", "fieldkit-xray", "Profile any table in seconds"),
        KnownPlugin("scrub", "fieldkit-scrub", "Find and mask PII before sharing"),
        KnownPlugin("mimic", "fieldkit-mimic", "Generate realistic fake datasets"),
        KnownPlugin("datadiff", "fieldkit-datadiff", "Explain why two tables disagree"),
        KnownPlugin("debrief", "fieldkit-debrief", "Turn field notes into reports"),
        KnownPlugin("tell", "fieldkit-tell", "Inspect a draft's writing patterns, locally"),
        KnownPlugin("netwatch", "fieldkit-netwatch", "Observe and control agent network access"),
        KnownPlugin(
            "awcp",
            "fieldkit-awcp",
            "Check AI workload specs, diff versions, and score golden evals locally",
        ),
    )
}


def installed_plugins() -> dict[str, metadata.EntryPoint]:
    """Tools present in this environment, by entry-point name."""

    return {ep.name: ep for ep in metadata.entry_points(group=GROUP_CLI)}


def web_modules() -> dict[str, metadata.EntryPoint]:
    return {ep.name: ep for ep in metadata.entry_points(group=GROUP_WEB)}


def _monorepo_plugin_dir(name: str) -> Path | None:
    # editable/dev installs run from the repo; walk up until plugins/ appears
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "plugins" / f"fieldkit-{name}"
        if (candidate / "pyproject.toml").exists():
            return candidate
    return None


def resolve_requirement(name: str, *, source: str | None = None, extras: list[str] | None = None) -> str:
    """One pip requirement string for a known plugin.

    Preference order when ``source`` is not forced: the local checkout (dev
    installs), then the git subdirectory. PyPI is only used when asked for,
    until the packages are actually published.
    """

    known = REGISTRY.get(name)
    if known is None:
        raise KeyError(name)
    if source is not None and source not in SOURCES:
        raise ValueError(f"unknown source {source!r} (expected one of {', '.join(SOURCES)})")

    suffix = f"[{','.join(extras)}]" if extras else ""

    local = _monorepo_plugin_dir(name)
    if source in (None, "local") and local is not None:
        return f"{local}{suffix}"
    if source == "local":
        raise FileNotFoundError(f"no local checkout for {name} (not running from the repo?)")
    if source in (None, "git"):
        return f"{known.package}{suffix} @ git+{REPO_GIT}#subdirectory=plugins/{known.package}"
    raise ValueError(
        "fieldkit plugins are not published to PyPI yet "
        "(the PyPI name 'fieldkit' belongs to an unrelated project). "
        "Install from a checkout with `uv sync`, use --source local or git, "
        "or pass --wheelhouse DIR with locally built Fieldkit wheels"
    )


def installer_argv() -> list[str]:
    """How to install into *this* interpreter's environment."""

    uv = shutil.which("uv")
    if uv:
        return [uv, "pip", "install", "--python", sys.executable]
    return [sys.executable, "-m", "pip", "install"]


def uninstaller_argv() -> list[str]:
    uv = shutil.which("uv")
    if uv:
        return [uv, "pip", "uninstall", "--python", sys.executable]
    return [sys.executable, "-m", "pip", "uninstall", "-y"]


def package_requirement(name: str, *, extras: list[str] | None = None) -> str:
    """Bare requirement (no source pin) — for wheelhouse and pypi installs."""

    known = REGISTRY.get(name)
    if known is None:
        raise KeyError(name)
    suffix = f"[{','.join(extras)}]" if extras else ""
    return f"{known.package}{suffix}"


def _dist_name(requirement: str) -> str:
    # "fieldkit-tell[ml] @ git+..." / "/repo/plugins/fieldkit-tell[ml]" / "fieldkit-tell" -> fieldkit-tell
    bare = requirement.split(" @ ", 1)[0].split("[", 1)[0]
    return Path(bare).name


def run_installer(requirements: list[str], *, upgrade: bool = False, find_links: str | None = None) -> int:
    argv = installer_argv()
    if upgrade:
        if Path(argv[0]).name == "uv":
            # never a bare --upgrade with uv: it walks the whole closure, and PyPI
            # has an unrelated project called `fieldkit` that would replace the core
            for name in {_dist_name(r) for r in requirements}:
                argv = [*argv, "--upgrade-package", name, "--reinstall-package", name]
        else:
            argv = [*argv, "--upgrade"]  # pip only upgrades what it must
    if find_links:
        # a wheelhouse dir wins for our packages; everything else still resolves normally
        argv = [*argv, "--find-links", find_links]
    completed = subprocess.run([*argv, *requirements], check=False)
    _refresh_metadata()
    return completed.returncode


def run_uninstaller(packages: list[str]) -> int:
    completed = subprocess.run([*uninstaller_argv(), *packages], check=False)
    _refresh_metadata()
    return completed.returncode


def _refresh_metadata() -> None:
    # entry-point scans cache path state; a just-installed dist should show up
    importlib.invalidate_caches()
