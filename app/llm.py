"""Gemini Flash-Lite text client + structured-output helper.

Every generative node calls `generate_structured(...)` with a Pydantic schema and
gets back a validated model instance — no manual JSON parsing anywhere else.
"""
from __future__ import annotations

import json
from typing import TypeVar

from google import genai
from google.genai import types
from pydantic import BaseModel

from . import config

T = TypeVar("T", bound=BaseModel)

_client: genai.Client | None = None


def client() -> genai.Client:
    """Lazily create and cache the Gemini client."""
    global _client
    if _client is None:
        if not config.GEMINI_API_KEY:
            raise RuntimeError(
                "GEMINI_API_KEY is not set. Add it to the .env file at the project root."
            )
        _client = genai.Client(api_key=config.GEMINI_API_KEY)
    return _client


def generate_text(prompt: str, *, thinking: str = config.THINK_LOW,
                  system: str | None = None) -> str:
    """Free-form text generation (rarely needed; nodes prefer structured output)."""
    cfg = types.GenerateContentConfig(
        thinking_config=types.ThinkingConfig(thinking_level=thinking),
        system_instruction=system,
    )
    resp = client().models.generate_content(
        model=config.TEXT_MODEL, contents=prompt, config=cfg,
    )
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
    resp = client().models.generate_content(
        model=config.TEXT_MODEL, contents=prompt, config=cfg,
    )
    # Prefer the SDK's parsed object; fall back to manual validation of .text.
    parsed = getattr(resp, "parsed", None)
    if isinstance(parsed, schema):
        return parsed
    if parsed is not None:
        return schema.model_validate(parsed)
    return schema.model_validate(json.loads(resp.text))
