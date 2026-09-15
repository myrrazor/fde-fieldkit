from __future__ import annotations

import shutil
import struct
import subprocess
import sys
from pathlib import Path

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def _png_bytes(width: int, height: int) -> bytes:
    return PNG_MAGIC + struct.pack(">I", 13) + b"IHDR" + struct.pack(">II", width, height)


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


def test_site_release_check_rejects_missing_tool_screenshot(tmp_path: Path) -> None:
    """Each selected tool panel must keep its local UI capture."""

    isolated = _isolated_site(tmp_path)
    index = isolated / "site" / "index.html"
    html = index.read_text(encoding="utf-8")
    index.write_text(
        html.replace("assets/screenshots/xray.png", "assets/screenshots/missing.png"),
        encoding="utf-8",
    )

    result = _run_check(isolated, tmp_path)

    assert result.returncode == 1
    assert "missing screenshot assets/screenshots/xray.png" in result.stdout


def test_site_release_check_rejects_deleted_screenshot_file(tmp_path: Path) -> None:
    """A referenced screenshot file that is not on disk must fail the release check."""

    isolated = _isolated_site(tmp_path)
    shot = isolated / "site" / "assets" / "screenshots" / "xray.png"
    shot.parent.mkdir(parents=True, exist_ok=True)
    shot.write_bytes(_png_bytes(1280, 900))
    shot.unlink()

    result = _run_check(isolated, tmp_path)

    assert result.returncode == 1
    assert "xray.png" in result.stdout
    assert "missing required file: assets/screenshots/xray.png" in result.stdout
    assert "broken local link" in result.stdout
    assert "missing image file" in result.stdout


def test_site_release_check_rejects_invalid_screenshot_bytes(tmp_path: Path) -> None:
    """Screenshot files must be PNGs, not arbitrary bytes."""

    isolated = _isolated_site(tmp_path)
    shot = isolated / "site" / "assets" / "screenshots" / "hub.png"
    shot.parent.mkdir(parents=True, exist_ok=True)
    shot.write_bytes(b"this is not a png file")

    result = _run_check(isolated, tmp_path)

    assert result.returncode == 1
    assert "hub.png is not a PNG" in result.stdout


def test_site_release_check_rejects_truncated_screenshot(tmp_path: Path) -> None:
    """A PNG signature without an IHDR is still a failed screenshot asset."""

    isolated = _isolated_site(tmp_path)
    shot = isolated / "site" / "assets" / "screenshots" / "scrub.png"
    shot.parent.mkdir(parents=True, exist_ok=True)
    shot.write_bytes(PNG_MAGIC + b"\x00\x00")

    result = _run_check(isolated, tmp_path)

    assert result.returncode == 1
    assert "scrub.png is a truncated PNG" in result.stdout


def test_site_release_check_rejects_wrong_screenshot_dimensions(tmp_path: Path) -> None:
    """Marketing captures are contracted at 1280x900."""

    isolated = _isolated_site(tmp_path)
    shot = isolated / "site" / "assets" / "screenshots" / "tell.png"
    shot.parent.mkdir(parents=True, exist_ok=True)
    shot.write_bytes(_png_bytes(64, 64))

    result = _run_check(isolated, tmp_path)

    assert result.returncode == 1
    assert "assets/screenshots/tell.png: expected 1280x900, got 64x64" in result.stdout


def test_site_release_check_rejects_donation_and_personal_credit(tmp_path: Path) -> None:
    """Public copy may star the project repo, not ask for coffee or personal credit."""

    isolated = _isolated_site(tmp_path)
    privacy = isolated / "site" / "privacy.html"
    html = privacy.read_text(encoding="utf-8")
    privacy.write_text(
        html.replace("Star on GitHub", "buy me a coffee")
        + "\n<p>Maintained by @reviewer</p>\n",
        encoding="utf-8",
    )
    readme = isolated / "README.md"
    readme.write_text(
        readme.read_text(encoding="utf-8") + "\nMaintained by [@reviewer](https://example.invalid)\n",
        encoding="utf-8",
    )

    result = _run_check(isolated, tmp_path)

    assert result.returncode == 1
    assert "donation or coffee copy is not allowed" in result.stdout
    assert "personal maintainer credit is not allowed" in result.stdout
    assert "privacy.html: missing Star on GitHub action" in result.stdout
