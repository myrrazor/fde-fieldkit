#!/usr/bin/env python3
"""Build the GitHub Release assets for the current workspace versions.

Standard-library only. Invokes `uv build --all-packages` with the Hatchling pin
in build-constraints.txt, then the existing artifact checker. Does not delete
unknown files in the output directory.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import subprocess
import sys
import tarfile
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONSTRAINTS = ROOT / "build-constraints.txt"
WHEEL_PACKAGES = (
    "fieldkit",
    "fieldkit-xray",
    "fieldkit-scrub",
    "fieldkit-mimic",
    "fieldkit-datadiff",
    "fieldkit-debrief",
    "fieldkit-tell",
    "fieldkit-netwatch",
    "fieldkit-awcp",
)


def workspace_projects(root: Path = ROOT) -> list[dict[str, str]]:
    """Name and version for the core and every plugin package."""

    projects = []
    for path in (root / "pyproject.toml", *sorted((root / "plugins").glob("*/pyproject.toml"))):
        project = tomllib.loads(path.read_text(encoding="utf-8"))["project"]
        projects.append({"name": project["name"], "version": project["version"]})
    return projects


def artifact_stem(name: str, version: str) -> str:
    return f"{name.replace('-', '_')}-{version}"


def expected_distribution_names(projects: list[dict[str, str]]) -> list[str]:
    names = []
    for project in projects:
        stem = artifact_stem(project["name"], project["version"])
        names.append(f"{stem}-py3-none-any.whl")
        names.append(f"{stem}.tar.gz")
    return names


def release_version(projects: list[dict[str, str]]) -> str:
    versions = {project["version"] for project in projects}
    names = {project["name"] for project in projects}
    if names != set(WHEEL_PACKAGES):
        missing = set(WHEEL_PACKAGES) - names
        extra = names - set(WHEEL_PACKAGES)
        raise ValueError(f"workspace packages drifted (missing={sorted(missing)} extra={sorted(extra)})")
    if len(versions) != 1:
        raise ValueError(f"workspace package versions do not match: {sorted(versions)}")
    return versions.pop()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def source_commit(root: Path = ROOT) -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


RELEASE_SIDECARS = frozenset({"SHA256SUMS", "release-manifest.json"})


def unexpected_distribution_names(
    directory: Path, expected: set[str], bundle_name: str
) -> list[str]:
    """Wheel/sdist names that are not the current 18 distributions or wheel bundle."""

    allowed = expected | {bundle_name} | set(RELEASE_SIDECARS)
    unexpected = []
    if not directory.is_dir():
        return unexpected
    for path in directory.iterdir():
        if not path.is_file():
            continue
        name = path.name
        if name in allowed:
            continue
        if name.endswith(".whl") or name.endswith(".tar.gz"):
            unexpected.append(name)
    return sorted(unexpected)


def write_sha256sums(paths: list[Path], dest: Path) -> None:
    lines = []
    for path in paths:
        if path.name == "SHA256SUMS":
            raise ValueError("SHA256SUMS must not checksum itself")
        lines.append(f"{sha256_file(path)}  {path.name}\n")
    dest.write_text("".join(lines), encoding="utf-8")


def write_manifest(
    *,
    version: str,
    commit: str,
    paths: list[Path],
    dest: Path,
) -> None:
    assets = [{"filename": path.name, "sha256": sha256_file(path)} for path in paths]
    payload = {
        "name": "fieldkit",
        "version": version,
        "source_commit": commit,
        "assets": assets,
    }
    dest.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _tarinfo(name: str, size: int) -> tarfile.TarInfo:
    info = tarfile.TarInfo(name)
    info.size = size
    info.mtime = 0
    info.mode = 0o644
    info.uid = 0
    info.gid = 0
    info.uname = ""
    info.gname = ""
    return info


def write_wheels_bundle(
    *,
    version: str,
    wheel_paths: list[Path],
    dest: Path,
    examples: dict[str, bytes] | None = None,
) -> None:
    members: list[tuple[str, bytes]] = []
    for wheel in wheel_paths:
        members.append((f"wheels/{wheel.name}", wheel.read_bytes()))
    members.append((f"INSTALL-{version}.txt", _install_notes(version).encode("utf-8")))
    if examples:
        for relative, data in sorted(examples.items()):
            members.append((relative, data))
    members.sort(key=lambda item: item[0])

    dest.parent.mkdir(parents=True, exist_ok=True)
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w", format=tarfile.USTAR_FORMAT) as archive:
        for name, data in members:
            archive.addfile(_tarinfo(name, len(data)), io.BytesIO(data))
    dest.write_bytes(gzip.compress(raw.getvalue(), compresslevel=9, mtime=0))


def _install_notes(version: str) -> str:
    return (
        f"Fieldkit {version} wheel bundle\n"
        "\n"
        "Python 3.12 or newer. These wheels are GitHub Release assets, not PyPI.\n"
        "The PyPI project named fieldkit is unrelated; do not pip install fieldkit\n"
        "from a package index.\n"
        "\n"
        "In this directory, install every Fieldkit wheel by explicit local path:\n"
        "\n"
        "  uv venv --seed --python 3.12 fresh\n"
        "  uv pip install --python fresh/bin/python wheels/*.whl\n"
        "\n"
        "wheels/*.whl expands to the nine Fieldkit paths, including the core.\n"
        "Later plugin adds/updates from this same directory:\n"
        "\n"
        "  fresh/bin/fieldkit plugin add xray --wheelhouse wheels\n"
        "\n"
        "A pinned source checkout remains supported:\n"
        "\n"
        f"  git clone --branch v{version} https://github.com/myrrazor/fde-fieldkit.git\n"
        "  cd fde-fieldkit && uv sync --locked --all-packages\n"
        "\n"
        "This archive is not a complete offline dependency bundle. pandas and other\n"
        "third-party requirements still come from a package index unless you prepare\n"
        "those wheels separately.\n"
    )


def example_payloads(root: Path = ROOT) -> dict[str, bytes]:
    customers = root / "examples" / "customers.csv"
    if not customers.is_file():
        return {}
    return {"examples/customers.csv": customers.read_bytes()}


def run_uv_build(output: Path, *, root: Path = ROOT) -> None:
    if not CONSTRAINTS.is_file():
        raise FileNotFoundError(f"missing build constraints: {CONSTRAINTS}")
    output.mkdir(parents=True, exist_ok=True)
    command = [
        "uv",
        "build",
        "--all-packages",
        "--build-constraint",
        str(CONSTRAINTS),
        "-o",
        str(output),
    ]
    completed = subprocess.run(command, cwd=root, check=False)
    if completed.returncode != 0:
        raise RuntimeError("uv build --all-packages failed")


def check_distributions(output: Path) -> None:
    scripts = Path(__file__).resolve().parent
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    from check_release_artifacts import check_distributions as _check

    errors = _check(output)
    if errors:
        raise RuntimeError("\n".join(errors))


def build_release(output: Path, *, root: Path = ROOT, run_build: bool = True) -> list[Path]:
    projects = workspace_projects(root)
    version = release_version(projects)
    expected = expected_distribution_names(projects)
    expected_set = set(expected)
    bundle_name = f"fieldkit-{version}-wheels.tar.gz"
    unexpected = unexpected_distribution_names(output, expected_set, bundle_name)
    if unexpected:
        raise RuntimeError(
            "refusing to ship unexpected distributions; remove them first: "
            + ", ".join(unexpected)
        )

    if run_build:
        run_uv_build(output, root=root)

    unexpected = unexpected_distribution_names(output, expected_set, bundle_name)
    if unexpected:
        raise RuntimeError(
            "refusing to ship unexpected distributions; remove them first: "
            + ", ".join(unexpected)
        )
    missing = [name for name in expected if not (output / name).is_file()]
    if missing:
        raise RuntimeError("incomplete distributions: " + ", ".join(missing))

    check_distributions(output)

    dist_paths = [output / name for name in expected]
    wheels = [output / name for name in expected if name.endswith(".whl")]
    bundle = output / bundle_name
    write_wheels_bundle(
        version=version,
        wheel_paths=wheels,
        dest=bundle,
        examples=example_payloads(root),
    )

    packaged = [*dist_paths, bundle]
    manifest = output / "release-manifest.json"
    write_manifest(
        version=version,
        commit=source_commit(root),
        paths=packaged,
        dest=manifest,
    )
    checksummed = [*packaged, manifest]
    write_sha256sums(checksummed, output / "SHA256SUMS")
    return checksummed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "directory",
        nargs="?",
        type=Path,
        default=ROOT / "dist",
        help="output directory (created if needed; unknown files are left in place)",
    )
    args = parser.parse_args()
    try:
        hashed = build_release(args.directory)
    except (RuntimeError, ValueError, FileNotFoundError, subprocess.CalledProcessError) as exc:
        print(exc, file=sys.stderr)
        return 1
    print(f"RELEASE BUILD PASSED: {len(hashed)} checksummed assets in {args.directory}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
