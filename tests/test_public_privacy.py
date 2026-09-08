#!/usr/bin/env python3
"""Behavior tests for audit_public_repo.py."""

from __future__ import annotations

import base64
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "audit_public_repo.py"
WRAPPER = SCRIPT.with_name("check-public-privacy.sh")
SPEC = importlib.util.spec_from_file_location("audit_public_repo", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
AUDITOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUDITOR)


def git(repo: Path, *args: str, input_data: bytes | None = None) -> bytes:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        input=input_data,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    ).stdout


def init_repo(root: Path) -> None:
    git(root, "init", "-b", "dev")
    git(root, "config", "commit.gpgsign", "false")
    git(root, "config", "user.name", "Project Maintainers")
    git(root, "config", "user.email", "maintainers@users.noreply.github.com")
    (root / "README.md").write_text("Safe public fixture.\n", encoding="utf-8")
    git(root, "add", "README.md")
    git(root, "commit", "-m", "test: add safe fixture (#0)")


class AuditPublicRepoTests(unittest.TestCase):
    def test_accepts_neutral_repository(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            init_repo(repo)
            result = AUDITOR.audit(repo, None)
            self.assertTrue(result["ok"])

    def test_accepts_large_safe_token(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            init_repo(repo)
            (repo / "generated.txt").write_bytes(b"a" * (128 * 1024))
            git(repo, "add", "generated.txt")
            git(repo, "commit", "-m", "test: add large safe fixture (#0)")
            result = AUDITOR.audit(repo, None)
            self.assertTrue(result["ok"])

    def test_detects_checkout_credential_config_until_removed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            init_repo(repo)
            runner_home = "/" + "home" + "/runner/work/"
            key = f"includeIf.gitdir:{runner_home}repo/.git.path"
            git(repo, "config", key, runner_home + "_temp/git-credentials-fixture.config")

            result = AUDITOR.audit(repo, None)
            self.assertTrue(any(
                finding["scope"] == "config" and finding["reason"] == "concrete_home_path"
                for finding in result["findings"]
            ))

            git(repo, "config", "--unset", key)
            self.assertTrue(AUDITOR.audit(repo, None)["ok"])

    def test_rejects_deleted_history_and_current_untracked_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            init_repo(repo)
            consumer = "owner" + "@" + "gmail.com"
            leaked = repo / "old.txt"
            leaked.write_text(consumer + "\n", encoding="utf-8")
            git(repo, "add", "old.txt")
            git(repo, "commit", "-m", "test: add historical fixture (#0)")
            leaked.unlink()
            git(repo, "add", "old.txt")
            git(repo, "commit", "-m", "test: remove historical fixture (#0)")
            (repo / "local.txt").write_text(
                "/" + "Users" + "/alice/project\n", encoding="utf-8"
            )
            result = AUDITOR.audit(repo, None)
            reasons = {item["reason"] for item in result["findings"]}
            self.assertIn("consumer_mailbox", reasons)
            self.assertIn("concrete_home_path", reasons)

    def test_rejects_blocked_identifier_in_unreachable_object(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            init_repo(repo)
            marker = "private" + "-handle"
            git(repo, "hash-object", "-w", "--stdin", input_data=marker.encode())
            blocklist = repo.parent / "private-blocklist.txt"
            blocklist.write_text(marker + "\n", encoding="utf-8")
            try:
                result = AUDITOR.audit(repo, blocklist)
            finally:
                blocklist.unlink(missing_ok=True)
            reasons = {item["reason"] for item in result["findings"]}
            self.assertIn("blocked_identifier", reasons)

    def test_project_wrapper_is_self_locating_and_keeps_values_out_of_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory) / "repo"
            repo.mkdir()
            init_repo(repo)
            scripts = repo / "scripts"
            scripts.mkdir()
            shutil.copy2(SCRIPT, scripts / SCRIPT.name)
            runner = scripts / WRAPPER.name
            shutil.copy2(WRAPPER, runner)
            runner.chmod(0o755)

            clean = subprocess.run(
                [str(runner)],
                cwd=repo.parent,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            self.assertEqual(clean.returncode, 0, clean.stderr.decode())

            marker = "private" + "-handle"
            (repo / "blocked.txt").write_text(marker + "\n", encoding="utf-8")
            git(repo, "add", "blocked.txt", "scripts")
            git(repo, "commit", "-m", "test: add wrapper fixture (#0)")
            env = os.environ.copy()
            env["PUBLIC_PRIVACY_BLOCKLIST_B64"] = base64.b64encode(
                (marker + "\n").encode()
            ).decode()
            blocked = subprocess.run(
                [str(runner)],
                cwd=repo.parent,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            output = blocked.stdout + blocked.stderr
            self.assertEqual(blocked.returncode, 1, output.decode())
            self.assertNotIn(marker.encode(), output)

            invalid_env = os.environ.copy()
            invalid_env["PUBLIC_PRIVACY_BLOCKLIST_B64"] = "not-base64"
            invalid = subprocess.run(
                [str(runner)],
                cwd=repo.parent,
                env=invalid_env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            self.assertEqual(invalid.returncode, 2)
            self.assertIn(b"could not decode", invalid.stderr)


if __name__ == "__main__":
    unittest.main()
