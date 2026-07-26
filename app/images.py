"""Gemini image generation for character portraits.

One call per portrait (not per line like TTS), so this stays deliberately
simpler than tts.py: a single client, basic retry on transient errors, no
multi-key lane rotation. Callers own caching to disk (see character_art.py).
"""
from __future__ import annotations

import random
import time
from pathlib import Path

from google.genai import types

from . import config
from .llm import client

_IMAGE_CONFIG = types.GenerateContentConfig(
    response_modalities=["IMAGE"],
    image_config=types.ImageConfig(aspect_ratio=config.IMAGE_ASPECT_RATIO),
)


def _is_retryable(err: Exception) -> bool:
    text = str(err).lower()
    return any(marker in text for marker in (
        "429", "resource_exhausted", "rate limit",
        "503", "unavailable", "500", "internal", "overloaded", "high demand",
    ))


def _image_bytes_from_response(response) -> bytes:
    candidates = getattr(response, "candidates", None) or []
    for candidate in candidates:
        for part in getattr(candidate.content, "parts", None) or []:
            inline = getattr(part, "inline_data", None)
            if inline is not None and inline.data:
                return inline.data
    raise RuntimeError("Gemini returned no image data for this prompt")


def generate_image(prompt: str, *, max_retries: int = config.IMAGE_MAX_RETRIES) -> bytes:
    """Generate one image from a text prompt, retrying on transient errors."""
    last: Exception | None = None
    for attempt in range(max_retries):
        try:
            response = client().models.generate_content(
                model=config.IMAGE_MODEL, contents=prompt, config=_IMAGE_CONFIG,
            )
            return _image_bytes_from_response(response)
        except Exception as err:  # noqa: BLE001
            if not _is_retryable(err):
                raise
            last = err
            time.sleep(min(20.0, 2 ** attempt) + random.uniform(0, 1))
    raise RuntimeError(
        f"Image generation failed after {max_retries} attempts: {last}"
    ) from last


def render_portrait(prompt: str, out_path: str | Path) -> Path:
    """Generate one image and write it to `out_path` (PNG bytes, as returned)."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    data = generate_image(prompt)
    out_path.write_bytes(data)
    return out_path
