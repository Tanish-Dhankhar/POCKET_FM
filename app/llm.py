"""Gemini Flash-Lite text client + structured-output helper.

Every generative node calls `generate_structured(...)` with a Pydantic schema and
gets back a validated model instance — no manual JSON parsing anywhere else.
"""
from __future__ import annotations

import json
import random
import threading
import time
from typing import TypeVar

from google import genai
from google.genai import types
from pydantic import BaseModel

from . import config

T = TypeVar("T", bound=BaseModel)

_client: genai.Client | None = None
_model_slots = threading.BoundedSemaphore(config.MODEL_MAX_CONCURRENCY)


def client() -> genai.Client:
    """Lazily create and cache the Gemini client."""
    global _client
    if _client is None:
        if not config.GEMINI_API_KEY:
            raise RuntimeError(
                "GEMINI_API_KEY is not set. Add it to the .env file at the project root."
            )
        _client = genai.Client(
            api_key=config.GEMINI_API_KEY,
            http_options=types.HttpOptions(timeout=config.MODEL_TIMEOUT_MS),
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
    for attempt in range(config.MODEL_MAX_RETRIES):
        try:
            with _model_slots:
                return call()
        except Exception as err:  # noqa: BLE001 - provider SDK has varied error types
            if not _is_retryable(err) or attempt == config.MODEL_MAX_RETRIES - 1:
                raise
            last = err
        time.sleep(min(8.0, 0.5 * (2 ** attempt)) + random.uniform(0, 0.25))
    raise RuntimeError(f"model request failed after retries: {last}") from last


def generate_text(prompt: str, *, thinking: str = config.THINK_LOW,
                  system: str | None = None) -> str:
    """Free-form text generation (rarely needed; nodes prefer structured output)."""
    cfg = types.GenerateContentConfig(
        thinking_config=types.ThinkingConfig(thinking_level=thinking),
        system_instruction=system,
    )
    resp = _request(lambda: client().models.generate_content(
        model=config.TEXT_MODEL, contents=prompt, config=cfg,
    ))
    return (resp.text or "").strip()


def transcribe_audio(data: bytes, mime_type: str = "audio/webm") -> str:
    """Transcribe a recording verbatim using the text model's audio input.

    Used by the mic flow: the creator speaks their story idea and we turn it into
    the plain text the pipeline expects. No separate STT model required.
    """
    resp = _request(lambda: client().models.generate_content(
        model=config.TEXT_MODEL,
        contents=[
            types.Part.from_bytes(data=data, mime_type=mime_type),
            "Transcribe this recording verbatim. Return ONLY the spoken words as "
            "plain prose — no timestamps, no speaker labels, no commentary. Fix "
            "obvious disfluencies (um, uh, false starts) but change nothing else.",
        ],
        config=types.GenerateContentConfig(
            thinking_config=types.ThinkingConfig(thinking_level=config.THINK_LOW),
        ),
    ))
    return (resp.text or "").strip()


def generate_structured(prompt: str, schema: type[T], *,
                        thinking: str = config.THINK_HIGH,
                        system: str | None = None) -> T:
    """Generate JSON constrained to `schema` and return a validated instance.

    Uses Gemini's native structured-output mode (response_schema) so the model is
    forced to emit schema-conforming JSON.
    """
    cfg = types.GenerateContentConfig(
        thinking_config=types.ThinkingConfig(thinking_level=thinking),
        response_mime_type="application/json",
        response_schema=schema,
        system_instruction=system,
    )
    resp = _request(lambda: client().models.generate_content(
        model=config.TEXT_MODEL, contents=prompt, config=cfg,
    ))
    # Prefer the SDK's parsed object; fall back to manual validation of .text.
    parsed = getattr(resp, "parsed", None)
    if isinstance(parsed, schema):
        return parsed
    if parsed is not None:
        return schema.model_validate(parsed)
    return schema.model_validate(json.loads(resp.text))
