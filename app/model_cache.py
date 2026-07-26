"""Small, content-addressed cache shared by all model providers.

Only hashes are used as filenames; prompts and creator data never appear in
paths or logs. Writes are atomic, corrupt/stale entries are treated as misses,
and striped locks collapse concurrent identical requests into one provider call.
"""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
import time
import threading
import uuid
from pathlib import Path
from typing import Any, Iterator

from . import config

_LOCKS = [threading.Lock() for _ in range(64)]


def key(namespace: str, payload: Any) -> str:
    rendered = json.dumps(
        {
            "version": config.MODEL_CACHE_VERSION,
            "namespace": namespace,
            "payload": payload,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(rendered).hexdigest()


@contextmanager
def locked(cache_key: str) -> Iterator[None]:
    lock = _LOCKS[int(cache_key[:8], 16) % len(_LOCKS)]
    with lock:
        yield


def _path(cache_key: str, suffix: str) -> Path:
    return config.MODEL_CACHE_DIR / cache_key[:2] / f"{cache_key[2:]}.{suffix}"


def _fresh(path: Path) -> bool:
    if not config.MODEL_CACHE_ENABLED or not path.is_file():
        return False
    ttl = config.MODEL_CACHE_TTL_SEC
    return ttl == 0 or time.time() - path.stat().st_mtime <= ttl


def load_json(cache_key: str) -> Any | None:
    path = _path(cache_key, "json")
    try:
        if not _fresh(path):
            return None
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def save_json(cache_key: str, value: Any) -> None:
    if not config.MODEL_CACHE_ENABLED:
        return
    path = _path(cache_key, "json")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        tmp.write_text(
            json.dumps(value, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )
        tmp.replace(path)
    except OSError:
        # Caching is an optimization and must never break generation.
        return


def load_bytes(cache_key: str) -> bytes | None:
    path = _path(cache_key, "bin")
    try:
        return path.read_bytes() if _fresh(path) else None
    except OSError:
        return None


def save_bytes(cache_key: str, value: bytes) -> None:
    if not config.MODEL_CACHE_ENABLED:
        return
    path = _path(cache_key, "bin")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        tmp.write_bytes(value)
        tmp.replace(path)
    except OSError:
        return
