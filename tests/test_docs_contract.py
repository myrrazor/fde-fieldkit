from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_agent_egress_rules_match_tell_interfaces() -> None:
    """The contributor contract must not reintroduce ambient-key egress."""

    guidance = (ROOT / "AGENTS.md").read_text(encoding="utf-8")

    assert "keys never authorize `tell` egress on their own" in guidance
    assert "fieldkit tell check --remote" in guidance
    assert "Python adapter helpers" in guidance
    assert "require explicit `offline=False`" in guidance
    assert "fieldkit tell check --offline" not in guidance


def test_api_spec_documents_fixed_loopback_binding() -> None:
    """The serve spec must match the intentionally non-configurable host boundary."""

    spec = (ROOT / "specs" / "wp6-api.md").read_text(encoding="utf-8")

    assert '`fieldkit serve [--port]`' in spec
    assert 'host="127.0.0.1"' in spec
    assert "The host is not configurable" in spec
    assert "--host 127.0.0.1" not in spec
    assert "prefers 8765" in spec
    assert "free port" in spec


def test_readme_documents_serve_port_fallback() -> None:
    """The README must not send people to a hard-coded 8765 that may already be taken."""

    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert "uv run fieldkit serve" in readme
    assert "Open http://127.0.0.1:8765" not in readme
    assert "free port" in readme
    assert "--port" in readme
    assert "prints the URL" in readme or "printed URL" in readme


def test_public_privacy_copy_requires_explicit_tell_egress() -> None:
    """Public privacy copy must describe all supported consent interfaces."""

    for relative in ("README.md", "site/privacy.html"):
        text = (ROOT / relative).read_text(encoding="utf-8")
        assert "--remote" in text
        assert "offline=False" in text
        assert "one-use confirmation" in text
        assert "--ml" in text
        assert "download" in text


def test_public_tell_copy_does_not_claim_authorship_detection() -> None:
    """Writing-pattern checks are not proof of who wrote a draft."""

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    site = (ROOT / "site/index.html").read_text(encoding="utf-8")
    plugins = (ROOT / "src/fieldkit/plugins.py").read_text(encoding="utf-8")
    plugins_docs = (ROOT / "site/docs/plugins.html").read_text(encoding="utf-8")
    assert "Spot AI-written text" not in readme
    assert "Spot AI-written text" not in plugins
    assert "Spot AI-written text" not in plugins_docs
    assert "do not establish who wrote" in readme
    assert "Neither establishes who wrote" in site
    assert "writing patterns" in plugins


def test_public_install_copy_does_not_claim_pypi_or_offline_wheelhouse() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    plugins_docs = (ROOT / "site/docs/plugins.html").read_text(encoding="utf-8")
    assert "Not on PyPI yet" in readme
    assert "does not disable" in readme or "does not enforce offline" in plugins_docs
    assert "works from any machine" not in plugins_docs
    assert "useful offline" not in (ROOT / "src/fieldkit/plugin_cli.py").read_text(
        encoding="utf-8"
    )
