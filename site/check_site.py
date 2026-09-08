#!/usr/bin/env python3
"""Run the static-site release checks without third-party packages."""

from __future__ import annotations

import base64
import hashlib
import json
import re
import struct
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse
from xml.etree import ElementTree


SITE_DIR = Path(__file__).resolve().parent
REPO_ROOT = SITE_DIR.parent
ORIGIN = "https://fde-tools.vercel.app"

REQUIRED_HEADERS = {
    "Permissions-Policy": "camera=(), geolocation=(), microphone=()",
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
}


def _expected_csp() -> str:
    hashes: list[str] = []
    pattern = re.compile(
        rb"<script\b(?=[^>]*\btype=[\"']application/ld\+json[\"'])[^>]*>(.*?)</script\s*>",
        re.IGNORECASE | re.DOTALL,
    )
    for relative in sorted(PAGE_RULES):
        for body in pattern.findall((SITE_DIR / relative).read_bytes()):
            digest = base64.b64encode(hashlib.sha256(body).digest()).decode("ascii")
            hashes.append(f"'sha256-{digest}'")

    script_sources = " ".join(["'self'", *hashes])
    return (
        "default-src 'self'; "
        f"script-src {script_sources}; "
        "style-src 'self'; img-src 'self' data:; font-src 'self'; connect-src 'none'; "
        "object-src 'none'; base-uri 'self'; form-action 'none'; frame-ancestors 'none'; "
        "upgrade-insecure-requests"
    )

PAGE_RULES = {
    "index.html": f"{ORIGIN}/",
    "docs/index.html": f"{ORIGIN}/docs/index.html",
    "docs/xray.html": f"{ORIGIN}/docs/xray.html",
    "docs/scrub.html": f"{ORIGIN}/docs/scrub.html",
    "docs/mimic.html": f"{ORIGIN}/docs/mimic.html",
    "docs/datadiff.html": f"{ORIGIN}/docs/datadiff.html",
    "docs/debrief.html": f"{ORIGIN}/docs/debrief.html",
    "docs/tell.html": f"{ORIGIN}/docs/tell.html",
    "docs/netwatch.html": f"{ORIGIN}/docs/netwatch.html",
    "docs/plugins.html": f"{ORIGIN}/docs/plugins.html",
    "privacy.html": f"{ORIGIN}/privacy.html",
    "terms.html": f"{ORIGIN}/terms.html",
}

# external links are a short allowlist on purpose; everything else on the site is local
ALLOWED_EXTERNAL_LINKS = {
    "https://github.com/myrrazor/fde-fieldkit",
    "https://github.com/myrrazor",
    "https://github.com/myrrazor/fde-fieldkit/issues",
    "https://docs.astral.sh/uv/",
}

# The plugin-add flavor is the product story. Fieldkit examples stay README-verbatim;
# AWCP is a separate repository, so its published block is pinned here and checked locally.
INSTALL_BLOCKS = {
    "xray-install": ("fieldkit plugin add xray\nfieldkit xray customers.csv"),
    "scrub-install": (
        "fieldkit plugin add scrub\nfieldkit scrub customers.csv -o customers_safe.csv"
    ),
    "mimic-install": ("fieldkit plugin add mimic\nfieldkit mimic learn customers.csv -o spec.yaml"),
    "datadiff-install": (
        "fieldkit plugin add datadiff\nfieldkit datadiff customers.csv customers_v2.csv"
    ),
    "debrief-install": ("fieldkit plugin add debrief\nfieldkit debrief report"),
    "tell-install": ("fieldkit plugin add tell\nfieldkit tell check draft.md"),
    "netwatch-install": ("fieldkit plugin add netwatch\nfieldkit netwatch run -- codex"),
    "awcp-install": (
        "make bootstrap\n"
        "PYTHONPATH=src python3 -m awcp.cli validate "
        "examples/workloads/support-ticket-triage.yaml"
    ),
}

EXAMPLE_BLOCKS = {
    "xray-examples": (
        "uv sync\n"
        "uv run fieldkit xray examples/customers.csv\n"
        "uv run fieldkit xray examples/customers.csv --html profile.html"
    ),
    "scrub-examples": (
        "uv sync\n"
        "uv run fieldkit scrub examples/customers.csv -o customers_safe.csv\n"
        "uv run fieldkit scrub examples/app.log -o app_safe.log --text"
    ),
    "mimic-examples": (
        "uv sync\n"
        "uv run fieldkit mimic learn examples/customers.csv -o spec.yaml\n"
        "uv run fieldkit mimic generate spec.yaml -n 10000 --seed 42 -o demo.csv\n"
        "uv run fieldkit mimic generate examples/customers.csv -n 500 -o demo.csv"
    ),
    "datadiff-examples": (
        "uv sync\nuv run fieldkit datadiff examples/customers.csv examples/customers_v2.csv"
    ),
    "debrief-examples": (
        "uv sync\n"
        'uv run fieldkit debrief add "shipped ingestion pipeline to prod" --tag win\n'
        'uv run fieldkit debrief add "waiting on VPN access for staging" --tag blocker\n'
        "uv run fieldkit debrief report"
    ),
    "tell-examples": (
        "uv sync\nuv run fieldkit tell check draft.md\nuv run fieldkit tell adapters"
    ),
    "netwatch-examples": (
        "uv sync\n"
        "uv run fieldkit netwatch doctor\n"
        "uv run fieldkit netwatch run -- codex\n"
        "uv run fieldkit netwatch run -- claude"
    ),
    "awcp-examples": (
        "PYTHONPATH=src python3 -m awcp.cli validate "
        "examples/workloads/support-ticket-triage.yaml\n"
        "PYTHONPATH=src python3 -m awcp.cli validate "
        "examples/workloads/support-ticket-triage.yaml --dry-run --json\n"
        "PYTHONPATH=src python3 -m awcp.cli diff "
        "examples/workloads/support-ticket-triage.yaml "
        "examples/templates/support-ticket-triage.yaml --json\n"
        "PYTHONPATH=src python3 -m awcp.cli eval run "
        "examples/workloads/support-ticket-triage.yaml --suite "
        "examples/eval-suites/support-triage-golden-v1.yaml --json"
    ),
}


# printed by src/fieldkit/cli.py when a registry tool isn't installed; exit code 2
PLUGIN_HINT = (
    "$ fieldkit xray\n"
    "'xray' is a Fieldkit tool that isn't installed yet.\n"
    "  fieldkit plugin add xray"
)

TOOL_DOC_PAGES = ("xray", "scrub", "mimic", "datadiff", "debrief", "tell", "netwatch")


class PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.attrs: list[tuple[str, dict[str, str]]] = []
        self.ids: set[str] = set()
        self.headings: list[int] = []
        self.title = ""
        self._in_title = False
        self.h1_count = 0
        self.meta: dict[str, str] = {}
        self.canonical = ""
        self.code: dict[str, str] = {}
        self._code_id: str | None = None
        self._code_parts: list[str] = []
        self.json_ld: list[str] = []
        self._in_json_ld = False
        self._json_parts: list[str] = []
        self.copy_targets: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        data = {key: value or "" for key, value in attrs}
        self.attrs.append((tag, data))
        if element_id := data.get("id"):
            self.ids.add(element_id)
        if tag == "title":
            self._in_title = True
        if re.fullmatch(r"h[1-6]", tag):
            level = int(tag[1])
            self.headings.append(level)
            if level == 1:
                self.h1_count += 1
        if tag == "meta":
            key = data.get("name") or data.get("property")
            if key:
                self.meta[key] = data.get("content", "")
        if tag == "link" and data.get("rel") == "canonical":
            self.canonical = data.get("href", "")
        if tag == "code" and data.get("id"):
            self._code_id = data["id"]
            self._code_parts = []
        if tag == "script" and data.get("type") == "application/ld+json":
            self._in_json_ld = True
            self._json_parts = []
        if target := data.get("data-copy-target"):
            self.copy_targets.add(target)

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False
        if tag == "code" and self._code_id:
            self.code[self._code_id] = "".join(self._code_parts).strip()
            self._code_id = None
            self._code_parts = []
        if tag == "script" and self._in_json_ld:
            self.json_ld.append("".join(self._json_parts))
            self._in_json_ld = False
            self._json_parts = []

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title += data
        if self._code_id:
            self._code_parts.append(data)
        if self._in_json_ld:
            self._json_parts.append(data)


def _parse_page(path: Path) -> PageParser:
    parser = PageParser()
    parser.feed(path.read_text(encoding="utf-8"))
    return parser


def _is_external(value: str) -> bool:
    return urlparse(value).scheme in {"http", "https"} or value.startswith("//")


def _png_size(path: Path) -> tuple[int, int]:
    with path.open("rb") as image:
        signature = image.read(24)
    if signature[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(f"{path.name} is not a PNG")
    return struct.unpack(">II", signature[16:24])


def _check_heading_order(headings: list[int]) -> bool:
    return all(current <= previous + 1 for previous, current in zip(headings, headings[1:]))


def _check_pages(errors: list[str]) -> dict[str, PageParser]:
    parsed: dict[str, PageParser] = {}
    titles: set[str] = set()

    for name, expected_canonical in PAGE_RULES.items():
        path = SITE_DIR / name
        if not path.exists():
            errors.append(f"missing page: {name}")
            continue
        page = _parse_page(path)
        parsed[name] = page

        if page.h1_count != 1:
            errors.append(f"{name}: expected one h1, found {page.h1_count}")
        if not _check_heading_order(page.headings):
            errors.append(f"{name}: heading levels skip")
        if not page.title or len(page.title) > 60:
            errors.append(f"{name}: title must be 1-60 characters")
        if page.title in titles:
            errors.append(f"{name}: duplicate title")
        titles.add(page.title)

        description = page.meta.get("description", "")
        if not 140 <= len(description) <= 160:
            errors.append(f"{name}: description is {len(description)} characters; expected 140-160")
        if page.canonical != expected_canonical:
            errors.append(f"{name}: canonical mismatch")
        if page.meta.get("og:url") != expected_canonical:
            errors.append(f"{name}: og:url mismatch")
        if page.meta.get("og:image") != f"{ORIGIN}/assets/og.png":
            errors.append(f"{name}: og:image mismatch")
        if page.meta.get("twitter:image") != f"{ORIGIN}/assets/og.png":
            errors.append(f"{name}: twitter:image mismatch")

        html_text = path.read_text(encoding="utf-8")
        if not re.search(r"<html\s+lang=[\"']en[\"']", html_text):
            errors.append(f"{name}: missing lang=en")

        for tag, attrs in page.attrs:
            resource = None
            if tag in {"img", "script", "iframe", "source", "video", "audio"}:
                resource = attrs.get("src")
            elif tag == "link" and attrs.get("rel") != "canonical":
                resource = attrs.get("href")
            if resource and _is_external(resource):
                errors.append(f"{name}: external runtime resource {resource}")

        for tag, attrs in page.attrs:
            if tag != "a" or not (href := attrs.get("href")):
                continue
            if _is_external(href):
                if href not in ALLOWED_EXTERNAL_LINKS:
                    errors.append(f"{name}: unexpected external link {href}")
                continue
            local_path, _, fragment = href.partition("#")
            # resolve relative to the page's own directory, not the site root
            page_path = SITE_DIR / name
            target_page = (page_path.parent / local_path).resolve() if local_path else page_path
            if not target_page.exists():
                errors.append(f"{name}: broken local link {href}")
                continue
            if fragment:
                try:
                    target_key = str(target_page.relative_to(SITE_DIR))
                except ValueError:
                    target_key = target_page.name
                target = parsed.get(target_key) or _parse_page(target_page)
                if fragment not in target.ids:
                    errors.append(f"{name}: missing fragment target {href}")

    return parsed


def _check_commands(index: PageParser, errors: list[str]) -> None:
    fieldkit_readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")

    for block_id, expected in {**INSTALL_BLOCKS, **EXAMPLE_BLOCKS}.items():
        actual = index.code.get(block_id)
        if actual != expected:
            errors.append(f"index.html: {block_id} does not match its expected command block")
        if block_id not in index.copy_targets:
            errors.append(f"index.html: {block_id} has no copy button")

    for block_id, commands in EXAMPLE_BLOCKS.items():
        if block_id.startswith("awcp-"):
            continue
        for command in commands.splitlines():
            if command not in fieldkit_readme:
                errors.append(f"{block_id}: source README is missing {command!r}")

    if "uv sync" not in fieldkit_readme:
        errors.append("fieldkit installs: README is missing 'uv sync'")


def _check_json_ld(index: PageParser, errors: list[str]) -> None:
    if len(index.json_ld) != 1:
        errors.append("index.html: expected one JSON-LD block")
        return
    try:
        data = json.loads(index.json_ld[0])
    except json.JSONDecodeError as exc:
        errors.append(f"index.html: invalid JSON-LD: {exc}")
        return
    if data.get("@type") != "ItemList" or data.get("numberOfItems") != 8:
        errors.append("index.html: JSON-LD must be an eight-item ItemList")
    items = data.get("itemListElement", [])
    names = [entry.get("item", {}).get("name") for entry in items]
    if names != ["xray", "scrub", "mimic", "datadiff", "debrief", "tell", "netwatch", "AWCP"]:
        errors.append("index.html: JSON-LD tool order or names do not match")


def _check_plugin_story(parsed: dict[str, PageParser], errors: list[str]) -> None:
    """The one-core-plus-plugins story must hold across docs pages and the README."""

    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")

    for tool in TOOL_DOC_PAGES:
        page = parsed.get(f"docs/{tool}.html")
        if page is None:
            continue  # the missing page is already reported
        install = page.code.get(f"{tool}-docs-install", "")
        if not install.startswith(f"fieldkit plugin add {tool}"):
            errors.append(
                f"docs/{tool}.html: install block must lead with 'fieldkit plugin add {tool}'"
            )
        if not page.code.get(f"{tool}-docs-dev", "").startswith("uv sync"):
            errors.append(f"docs/{tool}.html: dev block must lead with 'uv sync'")

    tell = parsed.get("docs/tell.html")
    if tell and "fieldkit plugin add tell --extra ml" not in "\n".join(tell.code.values()):
        errors.append(
            "docs/tell.html: ml extra must install via 'fieldkit plugin add tell --extra ml'"
        )

    scrub_copy = (SITE_DIR / "docs" / "scrub.html").read_text(encoding="utf-8")
    if "safe to pass around" in scrub_copy:
        errors.append("docs/scrub.html: must not promise that detector output is safe to share")
    if "detection can miss sensitive values" not in scrub_copy.lower():
        errors.append("docs/scrub.html: missing the residual-risk warning near sharing guidance")

    mimic_copy = " ".join(
        (SITE_DIR / "docs" / "mimic.html").read_text(encoding="utf-8").lower().split()
    )
    for overclaim in ("without a single real value", "the values are not"):
        if overclaim in mimic_copy:
            errors.append(f"docs/mimic.html: unsupported privacy claim {overclaim!r}")
    for disclosure in ("non-pii source values can remain", "exact distribution endpoints"):
        if disclosure not in mimic_copy:
            errors.append(f"docs/mimic.html: missing portable-spec disclosure {disclosure!r}")

    plugins = parsed.get("docs/plugins.html")
    if plugins is None:
        return
    if plugins.code.get("plugins-hint") != PLUGIN_HINT:
        errors.append("docs/plugins.html: not-installed hint transcript drifted")
    for line in PLUGIN_HINT.splitlines()[1:]:
        if line not in readme:
            errors.append(f"docs/plugins.html: README is missing hint line {line!r}")
    joined = "\n".join(plugins.code.values())
    for command in (
        "fieldkit plugin list",
        "fieldkit plugin list --json",
        "fieldkit plugin add xray scrub",
        "fieldkit plugin add tell --extra ml",
        "fieldkit plugin remove scrub",
        "fieldkit plugin update",
        "--wheelhouse",
    ):
        if command not in joined:
            errors.append(f"docs/plugins.html: command reference is missing {command!r}")
    text = (SITE_DIR / "docs" / "plugins.html").read_text(encoding="utf-8")
    if "not on PyPI yet" not in text:
        errors.append("docs/plugins.html: must say plainly that the packages are not on PyPI yet")


def _check_netwatch_story(errors: list[str]) -> None:
    """Keep the public dashboard claims aligned with Netwatch's local contract."""

    index = (SITE_DIR / "index.html").read_text(encoding="utf-8")
    docs = (SITE_DIR / "docs" / "netwatch.html").read_text(encoding="utf-8")

    if "Seven shipped plugins / one prototype" not in index:
        errors.append("index.html: must distinguish seven shipped plugins from the AWCP prototype")
    if 'src="assets/netwatch-dashboard.png"' not in index:
        errors.append("index.html: missing the Netwatch dashboard product capture")
    if 'src="../assets/netwatch-dashboard.png"' not in docs:
        errors.append("docs/netwatch.html: missing the Netwatch dashboard product capture")
    if "generated sample evidence" not in index or "generated sample evidence" not in docs:
        errors.append("Netwatch product captures must identify generated sample evidence")
    if "drops every command argument." not in docs or "It stores destination host" not in docs:
        errors.append("docs/netwatch.html: storage contract must separate dropped args from stored metadata")
    if "direct loopback browser" not in docs or "read-only evidence viewer" not in docs:
        errors.append("docs/netwatch.html: browser-control boundary is missing")


def _check_placeholders(errors: list[str]) -> None:
    text_files = [
        path
        for path in SITE_DIR.rglob("*")
        if path.is_file() and path.suffix in {".html", ".css", ".js", ".md", ".txt", ".xml", ".svg"}
    ]
    token_pattern = re.compile(r"\{\{[^}]+\}\}")
    bad_words = re.compile(r"\b(?:lorem ipsum|fixme|tbd)\b", re.IGNORECASE)

    for path in text_files:
        text = path.read_text(encoding="utf-8")
        for token in token_pattern.findall(text):
            errors.append(f"{path.relative_to(SITE_DIR)}: unexpected placeholder {token}")
        if bad_words.search(text):
            errors.append(f"{path.relative_to(SITE_DIR)}: placeholder copy remains")

    for name in ("privacy.html", "terms.html"):
        text = (SITE_DIR / name).read_text(encoding="utf-8")
        if "TODO(" in text:
            errors.append(f"{name}: unfinished launch copy remains")



def _check_support_files(errors: list[str]) -> None:
    required = [
        "assets/mark.svg",
        "assets/wordmark.svg",
        "assets/og.png",
        "assets/netwatch-dashboard.png",
        "fonts/ibm-plex-sans-vf.woff2",
        "fonts/ibm-plex-mono-400.woff2",
        "fonts/ibm-plex-mono-600.woff2",
        "robots.txt",
        "sitemap.xml",
        "llms.txt",
        "privacy.html",
        "terms.html",
    ]
    for relative in required:
        if not (SITE_DIR / relative).exists():
            errors.append(f"missing required file: {relative}")

    # every html page on disk is under contract — a new page must join PAGE_RULES
    html_files = {str(path.relative_to(SITE_DIR)) for path in SITE_DIR.rglob("*.html")}
    if html_files != set(PAGE_RULES):
        extra = ", ".join(sorted(html_files - set(PAGE_RULES))) or "none"
        missing = ", ".join(sorted(set(PAGE_RULES) - html_files)) or "none"
        errors.append(
            f"page inventory drifted from PAGE_RULES (extra: {extra}; missing: {missing})"
        )

    og_path = SITE_DIR / "assets" / "og.png"
    if og_path.exists():
        try:
            if _png_size(og_path) != (1200, 630):
                errors.append("assets/og.png: expected 1200x630")
        except ValueError as exc:
            errors.append(str(exc))

    dashboard_path = SITE_DIR / "assets" / "netwatch-dashboard.png"
    if dashboard_path.exists():
        try:
            _png_size(dashboard_path)
        except ValueError as exc:
            errors.append(str(exc))

    sitemap = SITE_DIR / "sitemap.xml"
    if sitemap.exists():
        try:
            root = ElementTree.parse(sitemap).getroot()
            namespace = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
            locations = [element.text for element in root.findall("s:url/s:loc", namespace)]
            expected = list(PAGE_RULES.values())
            if locations != expected:
                errors.append("sitemap.xml: locations do not match canonical pages")
        except ElementTree.ParseError as exc:
            errors.append(f"sitemap.xml: invalid XML: {exc}")

    robots = (SITE_DIR / "robots.txt").read_text(encoding="utf-8")
    if f"Sitemap: {ORIGIN}/sitemap.xml" not in robots:
        errors.append("robots.txt: sitemap origin mismatch")

    llms = (SITE_DIR / "llms.txt").read_text(encoding="utf-8")
    if f"Canonical site: {ORIGIN}/" not in llms:
        errors.append("llms.txt: canonical origin mismatch")
    if f"{ORIGIN}/docs/plugins.html" not in llms:
        errors.append("llms.txt: missing the plugins page")
    if "fieldkit plugin add" not in llms:
        errors.append("llms.txt: missing the toolkit model note")

    css = (SITE_DIR / "styles.css").read_text(encoding="utf-8")
    if "@import" in css or re.search(r"url\([\"']?https?://", css):
        errors.append("styles.css: external stylesheet or asset request found")
    script = (SITE_DIR / "script.js").read_text(encoding="utf-8")
    if re.search(r"\b(?:fetch|XMLHttpRequest|WebSocket)\s*\(", script):
        errors.append("script.js: network API found")


def _check_deployment_headers(errors: list[str]) -> None:
    path = SITE_DIR / "vercel.json"
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        errors.append("missing required file: vercel.json")
        return
    except json.JSONDecodeError as exc:
        errors.append(f"vercel.json: invalid JSON: {exc}")
        return

    wildcard = next(
        (entry for entry in config.get("headers", []) if entry.get("source") == "/(.*)"),
        None,
    )
    if wildcard is None:
        errors.append("vercel.json: missing wildcard response headers")
        return
    actual = {header.get("key"): header.get("value") for header in wildcard.get("headers", [])}
    if actual.get("Content-Security-Policy") != _expected_csp():
        errors.append("vercel.json: Content-Security-Policy is missing or has a stale script hash")
    for name, expected in REQUIRED_HEADERS.items():
        if actual.get(name) != expected:
            errors.append(f"vercel.json: {name} header is missing or drifted")


def main() -> int:
    """Run all checks and return a shell-friendly status code."""
    errors: list[str] = []
    parsed = _check_pages(errors)
    index = parsed.get("index.html")
    if index:
        _check_commands(index, errors)
        _check_json_ld(index, errors)
    _check_plugin_story(parsed, errors)
    _check_netwatch_story(errors)
    _check_placeholders(errors)
    _check_support_files(errors)
    _check_deployment_headers(errors)

    if errors:
        print(f"SITE CHECK FAILED ({len(errors)} findings)")
        for error in errors:
            print(f"- {error}")
        return 1

    print("SITE CHECK PASSED")
    print("- 12 pages: unique titles, 140-160 character descriptions, canonicals, one h1")
    print("- tool installs lead with fieldkit plugin add; local blocks are self-contained")
    print("- plugins page: manager commands, real not-installed hint, PyPI honesty")
    print("- JSON-LD ItemList has 8 SoftwareApplication entries")
    print("- OG image is 1200x630; robots, sitemap, and llms.txt agree")
    print("- Netwatch dashboard capture is local, labelled sample evidence, and coverage-aligned")
    print("- no external runtime resources or network APIs")
    print("- deployment security headers match the static site's runtime contract")
    print("- public pages contain no unfinished legal placeholders")
    return 0


if __name__ == "__main__":
    sys.exit(main())
