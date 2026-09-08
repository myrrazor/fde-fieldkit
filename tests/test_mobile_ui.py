from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from fieldkit.web import create_app


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    with TestClient(
        create_app(debrief_db=tmp_path / "debrief.db"), base_url="http://localhost"
    ) as test_client:
        yield test_client


@pytest.mark.parametrize(
    "path",
    ["/", "/xray/", "/scrub/", "/mimic/", "/datadiff/", "/debrief/", "/tell/"],
)
def test_every_app_page_declares_a_phone_viewport(client: TestClient, path: str) -> None:
    response = client.get(path)

    assert response.status_code == 200
    assert '<meta name="viewport" content="width=device-width, initial-scale=1">' in response.text


def test_app_phone_styles_cover_overflow_zoom_and_touch_targets(client: TestClient) -> None:
    css = client.get("/fieldkit.css").text

    assert "@media (max-width: 720px)" in css
    assert ".drop-row, .kit-grid { grid-template-columns: minmax(0, 1fr); }" in css
    assert ".controls > .field { flex: 1 1 100%; min-width: 0; }" in css
    assert "min-height: 44px; font-size: 16px;" in css
    assert ".btn, .check-pill, .signal-card { min-height: 44px; }" in css
    assert ".file-chip button { flex: 0 0 44px; width: 44px; height: 44px; }" in css
    assert ".report-head .actions { width: 100%; margin-left: 0; flex-wrap: wrap; }" in css


SITE = Path(__file__).resolve().parents[1] / "site"
PUBLIC_PAGES = {
    "index.html": ("#tools", "data-active-section"),
    "docs/index.html": ("index.html", "aria-current"),
    "docs/xray.html": ("index.html", "data-active-section"),
    "docs/scrub.html": ("index.html", "data-active-section"),
    "docs/mimic.html": ("index.html", "data-active-section"),
    "docs/datadiff.html": ("index.html", "data-active-section"),
    "docs/debrief.html": ("index.html", "data-active-section"),
    "docs/tell.html": ("index.html", "data-active-section"),
    "docs/plugins.html": ("plugins.html", "aria-current"),
    "privacy.html": ("privacy.html", "aria-current"),
    "terms.html": ("terms.html", "aria-current"),
}


@pytest.mark.parametrize(
    ("relative", "active"), PUBLIC_PAGES.items(), ids=PUBLIC_PAGES
)
def test_public_mobile_navigation_keeps_internal_links_and_current_page(
    relative: str, active: tuple[str, str]
) -> None:
    html = (SITE / relative).read_text(encoding="utf-8")
    match = re.search(r'<nav class="site-nav".*?</nav>', html, re.DOTALL)

    assert match is not None
    nav = match.group()
    internal_links = re.findall(r'<a href="(?!https?://)([^"]+)"', nav)
    assert len(internal_links) >= 2
    href, state = active
    attribute = 'aria-current="page"' if state == "aria-current" else 'data-active-section="true"'
    assert f'<a href="{href}" {attribute}>' in nav
    if state == "data-active-section":
        assert f'<a href="{href}" aria-current="page">' not in nav


def test_public_phone_navigation_is_scrollable_and_touch_sized() -> None:
    css = (SITE / "styles.css").read_text(encoding="utf-8")

    assert ".site-nav a:not(.site-nav__github)" not in css
    assert "overflow-x: auto;" in css
    assert "flex: 0 0 auto;" in css
    assert "min-height: 2.75rem;" in css
    assert '.site-nav a[aria-current="page"]' in css
    assert '.site-nav a[data-active-section="true"]' in css
