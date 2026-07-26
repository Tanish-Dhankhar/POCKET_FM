"""Synchronise the curated licensed audio library from its manifest.

This command intentionally never synthesises placeholder sounds.  Every catalog
entry must name a local destination and an auditable direct download URL.

Run:  python -m tools.build_assets [--force]
"""
from __future__ import annotations

import argparse
import json
import shutil
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
MANIFEST = ASSETS / "sound_manifest.json"
MIN_BYTES = {"music": 1_000, "sfx": 500}


def _download(url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".download")
    request = urllib.request.Request(url, headers={"User-Agent": "StorywaveAssetSync/2"})
    try:
        with urllib.request.urlopen(request, timeout=120) as response, \
                temporary.open("wb") as output:
            shutil.copyfileobj(response, output)
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--force", action="store_true",
        help="download again even when the local licensed file already exists",
    )
    args = parser.parse_args()

    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    downloaded = 0
    verified = 0
    for kind in ("music", "sfx"):
        for key, entry in data.get(kind, {}).items():
            destination = ASSETS / entry["file"]
            if args.force or not destination.is_file():
                url = entry.get("download_url")
                if not url:
                    raise ValueError(f"{kind}.{key} has no download_url")
                print(f"Downloading {kind}.{key}: {entry.get('title', key)}")
                _download(url, destination)
                downloaded += 1
            if destination.stat().st_size <= MIN_BYTES[kind]:
                raise ValueError(f"downloaded asset is too small: {destination}")
            verified += 1

    print(
        f"Licensed audio library v{data.get('library_version', '?')}: "
        f"{verified} verified, {downloaded} downloaded"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
