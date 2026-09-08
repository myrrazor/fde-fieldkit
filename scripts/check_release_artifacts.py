#!/usr/bin/env python3
"""Verify licensing and privacy in every workspace wheel and source archive."""

from __future__ import annotations

import argparse
from email.parser import BytesParser
from pathlib import Path
import sys
import tarfile
import tomllib
import zipfile

from audit_public_repo import inspect_bytes


ROOT = Path(__file__).resolve().parents[1]


def archive_files(path: Path) -> dict[str, bytes]:
    """Read regular files from a wheel or source archive without extracting it."""
    if path.suffix == ".whl":
        with zipfile.ZipFile(path) as archive:
            return {name: archive.read(name) for name in archive.namelist() if not name.endswith("/")}
    with tarfile.open(path, "r:gz") as archive:
        files = {}
        for member in archive.getmembers():
            if not member.isfile():
                continue
            handle = archive.extractfile(member)
            if handle is not None:
                files[member.name] = handle.read()
        return files


def check_archive(path: Path, expected_name: str, license_files: list[str]) -> list[str]:
    """Check one distribution's identity, notices, contents, and generic privacy rules."""
    errors = []
    files = archive_files(path)
    metadata = [data for name, data in files.items() if name.endswith(("/METADATA", "/PKG-INFO"))]
    if not metadata:
        return [f"{path.name}: missing package metadata"]
    info = BytesParser().parsebytes(metadata[0])
    if info.get("Name") != expected_name or info.get("License-Expression") != "MIT":
        errors.append(f"{path.name}: package name or MIT license metadata is missing")
    declared = set(info.get_all("License-File", []))
    for license_file in license_files:
        if license_file not in declared or not any(
            name.endswith("/" + license_file) for name in files
        ):
            errors.append(f"{path.name}: missing bundled notice {license_file}")
    for name, data in files.items():
        parts = Path(name).parts
        if any(part in {".git", ".venv", ".env", ".vercel", "__pycache__"} for part in parts):
            errors.append(f"{path.name}: local-only path {name}")
        if Path(name).name.startswith("TEST_STDOUT"):
            errors.append(f"{path.name}: local test log included")
        if inspect_bytes("artifact", name.encode(), data, []):
            errors.append(f"{path.name}: privacy check failed for {name}")
    return errors


def check_distributions(directory: Path) -> list[str]:
    """Validate the wheel and sdist for every package declared in this workspace."""
    errors = []
    projects = [ROOT / "pyproject.toml", *sorted(ROOT.glob("plugins/*/pyproject.toml"))]
    for project_file in projects:
        project = tomllib.loads(project_file.read_text())["project"]
        stem = project["name"].replace("-", "_") + "-" + project["version"]
        for pattern in (f"{stem}-*.whl", f"{stem}.tar.gz"):
            artifacts = list(directory.glob(pattern))
            if len(artifacts) != 1:
                errors.append(f"expected one current distribution matching {pattern}")
                continue
            errors.extend(check_archive(artifacts[0], project["name"], project["license-files"]))
    return errors


def main() -> int:
    """Check a build directory and return a failing status for incomplete releases."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    errors = check_distributions(args.directory)
    if errors:
        for error in errors:
            print(error)
        return 1
    print("DISTRIBUTION CHECK PASSED: every workspace wheel and sdist has its notices")
    return 0


if __name__ == "__main__":
    sys.exit(main())
