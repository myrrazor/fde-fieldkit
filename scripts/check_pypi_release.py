#!/usr/bin/env python3
"""Reject missing, stale, or extra files before handing artifacts to PyPI."""

from __future__ import annotations

import argparse
from pathlib import Path

from build_release import expected_distribution_names, release_version, workspace_projects
from check_release_artifacts import check_distributions


def check(directory: Path) -> list[str]:
    projects = workspace_projects()
    release_version(projects)
    expected = set(expected_distribution_names(projects))
    actual = {path.name for path in directory.iterdir()} if directory.is_dir() else set()
    # uv creates this sentinel; neither the upload glob nor Actions includes it.
    actual.discard(".gitignore")
    errors = []
    if actual != expected:
        errors.append(f"upload files differ: missing={sorted(expected - actual)}, "
                      f"extra={sorted(actual - expected)}")
    errors.extend(check_distributions(directory))
    return errors


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    errors = check(parser.parse_args().directory)
    for error in errors:
        print(error)
    raise SystemExit(bool(errors))
