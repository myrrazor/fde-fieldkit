from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


def _isolated_site(tmp_path: Path) -> Path:
    """Copy only the files the release check is allowed to depend on."""

    repo_root = Path(__file__).resolve().parents[1]
    isolated = tmp_path / "fde-fieldkit"
    isolated.mkdir()
    shutil.copy2(repo_root / "README.md", isolated / "README.md")
    shutil.copytree(repo_root / "site", isolated / "site")
    return isolated


def _run_check(isolated: Path, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(isolated / "site" / "check_site.py")],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )


def test_site_release_check_is_self_contained(tmp_path: Path) -> None:
    """The site checker must work from an isolated copy of this repository."""

    result = _run_check(_isolated_site(tmp_path), tmp_path)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "SITE CHECK PASSED" in result.stdout


def test_site_release_check_rejects_stale_inline_script_hash(tmp_path: Path) -> None:
    """Changing inline JSON-LD must also change the deployment CSP hash."""

    isolated = _isolated_site(tmp_path)
    index = isolated / "site" / "index.html"
    html = index.read_bytes()
    index.write_bytes(html.replace(b"\n    </script>", b" \n    </script>", 1))

    result = _run_check(isolated, tmp_path)

    assert result.returncode == 1
    assert "Content-Security-Policy is missing or has a stale script hash" in result.stdout


def test_site_release_check_rejects_unconditional_scrub_safety_claim(tmp_path: Path) -> None:
    """Public copy must preserve scrub's detector-not-guarantee boundary."""

    isolated = _isolated_site(tmp_path)
    scrub = isolated / "site" / "docs" / "scrub.html"
    html = scrub.read_text(encoding="utf-8")
    scrub.write_text(
        html.replace(
            "shape-preserving copy with recognized PII replaced. Inspect it before sharing;\n"
            "          detection can miss sensitive values.",
            "copy that is safe to pass around without breaking the data's shape.",
        ),
        encoding="utf-8",
    )

    result = _run_check(isolated, tmp_path)

    assert result.returncode == 1
    assert "must not promise that detector output is safe to share" in result.stdout


def test_site_release_check_rejects_unqualified_mimic_privacy_claim(tmp_path: Path) -> None:
    """Mimic docs must disclose retained non-PII categories and distributions."""

    isolated = _isolated_site(tmp_path)
    mimic = isolated / "site" / "docs" / "mimic.html"
    html = mimic.read_text(encoding="utf-8")
    mimic.write_text(
        html.replace("non-PII source values can remain", "the output has no real values"),
        encoding="utf-8",
    )

    result = _run_check(isolated, tmp_path)

    assert result.returncode == 1
    assert "missing portable-spec disclosure 'non-pii source values can remain'" in result.stdout


def test_site_release_check_rejects_unfinished_legal_placeholders(tmp_path: Path) -> None:
    """Public legal pages cannot regress to private-launch template text."""
    isolated = _isolated_site(tmp_path)
    terms = isolated / "site" / "terms.html"
    html = terms.read_text(encoding="utf-8")
    terms.write_text(html.replace("Fieldkit is maintained", "{{LEGAL_ENTITY}} is maintained"))
    result = _run_check(isolated, tmp_path)
    assert result.returncode == 1
    assert "unexpected placeholder" in result.stdout
