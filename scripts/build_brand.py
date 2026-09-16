#!/usr/bin/env python3
"""Render the committed brand SVGs and sync the website's public assets."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BRAND = ROOT / "brand"
EXPORTS = {
    "logo": (1024, 1024),
    "logo-reversed": (1024, 1024),
    "logo-mono": (1024, 1024),
    "wordmark": (1288, 256),
    "wordmark-reversed": (1288, 256),
    "github-social": (1280, 640),
    "website-social": (1200, 630),
    "portfolio": (1600, 900),
    "avatar": (1024, 1024),
    "showcase": (1440, 960),
}


def main() -> None:
    renderer = shutil.which("rsvg-convert")
    if not renderer:
        raise SystemExit("rsvg-convert is required to export PNGs; committed assets are ready to use")

    exports = [
        (BRAND / f"{name}.svg", BRAND / f"{name}.png", width, height)
        for name, (width, height) in EXPORTS.items()
    ]
    exports += [
        (BRAND / "logo.svg", BRAND / f"logo-{size}.png", size, size) for size in (16, 32, 48)
    ]
    for source, target, width, height in exports:
        subprocess.run(
            [renderer, "--width", str(width), "--height", str(height), "--output", str(target),
             str(source)],
            check=True,
        )

    for source, target in {
        "logo.svg": "mark.svg",
        "wordmark.svg": "wordmark.svg",
        "website-social.svg": "og.svg",
        "website-social.png": "og.png",
    }.items():
        shutil.copyfile(BRAND / source, ROOT / "site" / "assets" / target)

    print(f"Rendered {len(exports)} PNGs and synced four website assets")


if __name__ == "__main__":
    main()
