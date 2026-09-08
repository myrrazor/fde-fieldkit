#!/usr/bin/env python3
"""Fail closed when a Git repository contains publication-sensitive identifiers."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Iterable


CONSUMER_EMAIL = re.compile(
    rb"(?<![a-z0-9.!#$%&'*+/=?^_`{|}~-])"
    rb"[a-z0-9.!#$%&'*+/=?^_`{|}~-]+@(?:[a-z0-9-]+\.)*"
    rb"(?:aol|fastmail|gmail|gmx|hotmail|icloud|live|mac|mail|me|msn|outlook|"
    rb"proton|protonmail|yahoo)\.[a-z]{2,}",
    re.IGNORECASE,
)
HOME_PATHS = (
    re.compile(rb"/Users/[A-Za-z0-9._-]+(?:/|$)"),
    re.compile(rb"/home/[A-Za-z0-9._-]+(?:/|$)"),
    re.compile(rb"[A-Za-z]:\\Users\\[A-Za-z0-9._-]+(?:\\|$)", re.IGNORECASE),
)


def run_git(repo: Path, *args: str, input_data: bytes | None = None) -> bytes:
    """Run Git without a pager and return stdout, raising a redacted error."""
    completed = subprocess.run(
        ["git", "-C", str(repo), *args],
        input=input_data,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", "replace").splitlines()
        message = detail[0] if detail else "unknown Git error"
        raise RuntimeError(f"git {args[0]} failed: {message}")
    return completed.stdout


def fingerprint(value: bytes) -> str:
    """Return a short case-insensitive fingerprint without disclosing the value."""
    return hashlib.sha256(value.lower()).hexdigest()[:16]


def load_blocklist(path: Path | None) -> list[bytes]:
    """Load newline-delimited private identifiers from an external file."""
    if path is None:
        return []
    values = []
    for line in path.read_bytes().splitlines():
        value = line.strip()
        if value and not value.startswith(b"#"):
            values.append(value.lower())
    return values


def inspect_bytes(
    scope: str,
    location: bytes,
    payload: bytes,
    blocked: Iterable[bytes],
) -> list[dict[str, str]]:
    """Find sensitive values in one payload and report fingerprints only."""
    findings: list[dict[str, str]] = []
    location_id = fingerprint(location)

    for match in CONSUMER_EMAIL.finditer(payload):
        findings.append(
            {
                "scope": scope,
                "location": location_id,
                "reason": "consumer_mailbox",
                "match": fingerprint(match.group(0)),
            }
        )
    for pattern in HOME_PATHS:
        for match in pattern.finditer(payload):
            findings.append(
                {
                    "scope": scope,
                    "location": location_id,
                    "reason": "concrete_home_path",
                    "match": fingerprint(match.group(0)),
                }
            )

    lowered = payload.lower()
    for value in blocked:
        if value in lowered:
            findings.append(
                {
                    "scope": scope,
                    "location": location_id,
                    "reason": "blocked_identifier",
                    "match": fingerprint(value),
                }
            )

    unique = {tuple(sorted(item.items())): item for item in findings}
    return list(unique.values())


def scan_objects(repo: Path, blocked: list[bytes]) -> tuple[list[dict[str, str]], int]:
    """Scan all stored blob, commit, and tag objects, including unreachable ones."""
    rows = run_git(
        repo,
        "cat-file",
        "--batch-all-objects",
        "--batch-check=%(objectname) %(objecttype) %(objectsize)",
    ).splitlines()
    objects = []
    for row in rows:
        oid, kind, _size = row.split(b" ", 2)
        if kind in {b"blob", b"commit", b"tag"}:
            objects.append((oid, kind))

    findings: list[dict[str, str]] = []
    process = subprocess.Popen(
        ["git", "-C", str(repo), "cat-file", "--batch"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert process.stdin is not None
    assert process.stdout is not None
    for oid, kind in objects:
        process.stdin.write(oid + b"\n")
        process.stdin.flush()
        header = process.stdout.readline().rstrip(b"\n")
        _actual_oid, actual_kind, size_text = header.split(b" ", 2)
        size = int(size_text)
        data = process.stdout.read(size)
        process.stdout.read(1)
        if actual_kind != kind:
            raise RuntimeError("git cat-file returned an unexpected object type")
        findings.extend(inspect_bytes("object", oid, data, blocked))

    process.stdin.close()
    stderr = process.stderr.read() if process.stderr is not None else b""
    returncode = process.wait()
    process.stdout.close()
    if process.stderr is not None:
        process.stderr.close()
    if returncode != 0:
        detail = stderr.decode("utf-8", "replace").splitlines()
        raise RuntimeError(detail[0] if detail else "git cat-file failed")
    return findings, len(rows)


def scan_worktree(repo: Path, blocked: list[bytes]) -> tuple[list[dict[str, str]], int]:
    """Scan tracked and untracked nonignored paths in the current worktree."""
    paths = run_git(
        repo, "ls-files", "-z", "--cached", "--others", "--exclude-standard"
    ).split(b"\0")
    findings: list[dict[str, str]] = []
    count = 0
    for raw_path in paths:
        if not raw_path:
            continue
        count += 1
        findings.extend(inspect_bytes("filename", raw_path, raw_path, blocked))
        path = repo / os.fsdecode(raw_path)
        try:
            data = os.readlink(path).encode() if path.is_symlink() else path.read_bytes()
        except (FileNotFoundError, IsADirectoryError, PermissionError):
            continue
        findings.extend(inspect_bytes("worktree", raw_path, data, blocked))
    return findings, count


def scan_git_state(repo: Path, blocked: list[bytes]) -> list[dict[str, str]]:
    """Scan repository identity, config, remotes, refs, and reflogs."""
    findings: list[dict[str, str]] = []
    commands = (
        ("config", "config", "--local", "--list", "--show-origin", "-z"),
        ("effective_identity", "config", "--get-regexp", r"^user\.(name|email)$"),
        ("refs", "for-each-ref", "--format=%(refname)%00%(contents)%00"),
        ("reflog", "reflog", "show", "--all", "--format=%H%x00%gs"),
        ("remotes", "remote", "-v"),
    )
    for scope, *args in commands:
        completed = subprocess.run(
            ["git", "-C", str(repo), *args],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if completed.returncode not in {0, 1}:
            detail = completed.stderr.decode("utf-8", "replace").splitlines()
            raise RuntimeError(detail[0] if detail else f"git {args[0]} failed")
        findings.extend(
            inspect_bytes(scope, scope.encode(), completed.stdout, blocked)
        )
    return findings


def audit(repo: Path, blocklist: Path | None) -> dict[str, object]:
    """Audit a repository and return a non-disclosing structured result."""
    repo = Path(run_git(repo, "rev-parse", "--show-toplevel").decode().strip()).resolve()
    blocked = load_blocklist(blocklist)
    findings = scan_git_state(repo, blocked)
    object_findings, object_count = scan_objects(repo, blocked)
    worktree_findings, file_count = scan_worktree(repo, blocked)
    findings.extend(object_findings)
    findings.extend(worktree_findings)
    unique = {tuple(sorted(item.items())): item for item in findings}
    ordered = sorted(unique.values(), key=lambda item: tuple(item.values()))
    return {
        "ok": not ordered,
        "objects_scanned": object_count,
        "files_scanned": file_count,
        "findings": ordered,
    }


def parse_args() -> argparse.Namespace:
    """Parse command-line options."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--blocklist", type=Path)
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def main() -> int:
    """Run the command-line audit and return its documented exit status."""
    args = parse_args()
    try:
        result = audit(args.repo.resolve(), args.blocklist)
    except (OSError, RuntimeError, subprocess.SubprocessError) as error:
        print(f"public repository audit failed to run: {error}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    elif result["ok"]:
        print(
            "public repository audit passed "
            f"({result['objects_scanned']} objects, {result['files_scanned']} files)"
        )
    else:
        print("public repository audit found publication-sensitive data", file=sys.stderr)
        for item in result["findings"]:
            print(
                f"- {item['scope']}:{item['location']} {item['reason']} "
                f"({item['match']})",
                file=sys.stderr,
            )
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
