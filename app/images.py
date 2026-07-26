"""OpenAI image client for series thumbnails and character portraits.

Deliberately shaped like app/llm.py: a lazily-created singleton client, a bounded
+ retried request wrapper, and one public generator that the rest of the code
calls without knowing anything about the provider.

Artwork is decoration, never part of the story pipeline's contract. When images
are disabled (the default) `generate_image` returns None without touching the
network, so every caller degrades to "no picture" rather than failing.
"""
from __future__ import annotations

import base64
import logging
import random
import threading
import time
import uuid
from pathlib import Path

from . import config

_LOG = logging.getLogger(__name__)

_client = None  # type: ignore[var-annotated]
_client_lock = threading.Lock()
_image_slots = threading.BoundedSemaphore(config.IMAGE_MAX_CONCURRENCY)


def enabled() -> bool:
    """True only when image generation is switched on AND a key is configured."""
    return bool(config.IMAGE_ENABLED and config.OPENAI_API_KEY)


def client():
    """Lazily create and cache the OpenAI client."""
    global _client
    if _client is None:
        with _client_lock:
            if _client is None:
                if not config.OPENAI_API_KEY:
                    raise RuntimeError(
                        "OPENAI_API_KEY is not set. Add it to the .env file at the "
                        "project root, or leave IMAGE_ENABLED=false."
                    )
                from openai import OpenAI  # imported lazily so the dep stays optional

                _client = OpenAI(
                    api_key=config.OPENAI_API_KEY,
                    timeout=config.IMAGE_TIMEOUT_MS / 1000,
                )
    return _client


def _is_retryable(err: Exception) -> bool:
    text = str(err).lower()
    return any(code in text for code in (
        "429", "resource_exhausted", "rate limit", "500", "503",
        "unavailable", "overloaded", "deadline", "timeout",
    ))


def _request(call):
    """Bound and retry provider calls without logging creator prompts or output."""
    last: Exception | None = None
    for attempt in range(config.IMAGE_MAX_RETRIES):
        try:
            with _image_slots:
                return call()
        except Exception as err:  # noqa: BLE001 - provider SDK has varied error types
            if not _is_retryable(err) or attempt == config.IMAGE_MAX_RETRIES - 1:
                raise
            last = err
        time.sleep(min(8.0, 0.5 * (2 ** attempt)) + random.uniform(0, 0.25))
    raise RuntimeError(f"image request failed after retries: {last}") from last


def _write_atomic(path: Path, data: bytes) -> Path:
    """Temp file + replace, so a crash can't leave a half-written PNG."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    tmp.write_bytes(data)
    tmp.replace(path)
    return path


def generate_image(prompt: str, path: Path, *, size: str | None = None) -> Path | None:
    """Render one image to `path`, or return None when images are disabled.

    Returning None rather than raising is the whole point: callers treat missing
    artwork as a normal state, so a provider outage never blocks a series.
    """
    if not enabled():
        return None

    resp = _request(lambda: client().images.generate(
        model=config.IMAGE_MODEL,
        prompt=prompt,
        size=size or config.IMAGE_SIZE,
        quality=config.IMAGE_QUALITY,
        n=1,
    ))

    item = resp.data[0]
    # gpt-image-1 always returns base64; the url field only appears on older models.
    payload = getattr(item, "b64_json", None)
    if not payload:
        raise RuntimeError(f"{config.IMAGE_MODEL} returned no image data")

    _LOG.info("image_generated path=%s model=%s", path.name, config.IMAGE_MODEL)
    return _write_atomic(path, base64.b64decode(payload))
