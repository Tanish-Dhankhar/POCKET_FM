"""Access to the licensed sound library described by assets/sound_manifest.json."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from . import config


@lru_cache(maxsize=4)
def _read_manifest(path: str, modified_ns: int) -> dict:
    """Cache one immutable manifest revision while allowing live replacements."""
    del modified_ns  # its value is the cache-busting revision key
    return json.loads(Path(path).read_text(encoding="utf-8"))


def manifest() -> dict:
    path = config.SOUND_MANIFEST
    if not path.exists():
        return {"music": {}, "sfx": {}}
    return _read_manifest(str(path), path.stat().st_mtime_ns)


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
