"""Access to the prebuilt sound library described by assets/sound_manifest.json."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from . import config


@lru_cache(maxsize=1)
def manifest() -> dict:
    if not config.SOUND_MANIFEST.exists():
        return {"music": {}, "sfx": {}}
    return json.loads(config.SOUND_MANIFEST.read_text())


def music_moods() -> list[str]:
    return list(manifest().get("music", {}).keys())


def sfx_keys() -> list[str]:
    return list(manifest().get("sfx", {}).keys())


def music_path(mood: str) -> Path | None:
    entry = manifest().get("music", {}).get(mood)
    return config.ASSETS_DIR / entry["file"] if entry else None


def sfx_path(name: str) -> Path | None:
    entry = manifest().get("sfx", {}).get(name)
    return config.ASSETS_DIR / entry["file"] if entry else None
