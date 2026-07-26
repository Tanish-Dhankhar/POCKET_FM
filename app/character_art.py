"""Character portrait generation — one Gemini image call per character.

Mirrors the voice-sample pattern in api_store.py: the first request for a
portrait costs one image call and caches the PNG to disk; every later request
(until the character or story changes) is an instant file read. A per-character
lock stops concurrent requests from triggering duplicate, billable renders.
"""
from __future__ import annotations

import threading
from pathlib import Path

from . import images, prompts, store

_locks_guard = threading.Lock()
_locks: dict[str, threading.Lock] = {}


def _lock_for(series_id: str, key: str) -> threading.Lock:
    lock_key = f"{series_id}:{key}"
    with _locks_guard:
        return _locks.setdefault(lock_key, threading.Lock())


def ensure_portrait(series_id: str, key: str, *, force: bool = False) -> Path:
    """Return the cached portrait path, rendering it first if missing/stale/forced.

    Raises ValueError for an unknown character (-> 404 at the API layer).
    """
    character = store.load_character(series_id, key)
    if character is None:
        raise ValueError(f"unknown character '{key}'")

    portrait_path = store.character_portrait_path(series_id, key)
    with _lock_for(series_id, key):
        # Re-read inside the lock: another thread may have just finished rendering.
        character = store.load_character(series_id, key) or character
        if portrait_path.exists() and not character.get("portrait_stale") and not force:
            return portrait_path

        blueprint = store.load_blueprint(series_id)
        prompt = prompts.character_portrait(character, blueprint)
        images.render_portrait(prompt, portrait_path)
        character["portrait_generated_at"] = store._now()
        character["portrait_stale"] = False
        store.save_character(series_id, character)
    return portrait_path
