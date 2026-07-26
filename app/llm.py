"""Text generation (OpenAI) + the shared Gemini client (TTS / transcription).

Two providers live here on purpose:

- **Text** goes to OpenAI's Responses API. Each production task uses the explicit
  Luna/Sol route in `config.TEXT_TASKS`. `generate_structured` uses
  `responses.parse` with a Pydantic schema, so no node parses JSON by hand.
- **Audio** stays on Gemini: `client()` is the Gemini handle that app/tts.py
  uses for speech synthesis, and `transcribe_audio` uses Gemini's native audio
  input for the mic flow.
"""
from __future__ import annotations

import hashlib
import random
import threading
import time
from typing import TypeVar

from google import genai
from google.genai import types
from pydantic import BaseModel

from . import config, model_cache

T = TypeVar("T", bound=BaseModel)

_client: genai.Client | None = None
_openai_client = None  # type: ignore[var-annotated]
_client_lock = threading.Lock()
_model_slots = threading.BoundedSemaphore(config.MODEL_MAX_CONCURRENCY)


def client() -> genai.Client:
    """Lazily create and cache the Gemini client (used for TTS + transcription)."""
    global _client
    if _client is None:
        with _client_lock:
            if _client is None:
                if not config.GEMINI_API_KEY:
                    raise RuntimeError(
                        "GEMINI_API_KEY is not set. Add it to the .env file at the "
                        "project root."
                    )
                _client = genai.Client(
                    api_key=config.GEMINI_API_KEY,
                    http_options=types.HttpOptions(timeout=config.MODEL_TIMEOUT_MS),
                )
    return _client


def openai_client():
    """Lazily create and cache the OpenAI client (used for all text generation)."""
    global _openai_client
    if _openai_client is None:
        with _client_lock:
            if _openai_client is None:
                if not config.OPENAI_API_KEY:
                    raise RuntimeError(
                        "OPENAI_API_KEY is not set. Add it to the .env file at the "
                        "project root."
                    )
                from openai import OpenAI

                _openai_client = OpenAI(
                    api_key=config.OPENAI_API_KEY,
                    timeout=config.TEXT_TIMEOUT_MS / 1000,
                    max_retries=0,   # app-level _request owns retry/backoff
                )
    return _openai_client


def _model_for(thinking: str) -> str:
    """Backward-compatible model selection for un-routed utility calls."""
    return (config.TEXT_MODEL_HARD if thinking in (config.THINK_HIGH, config.THINK_MEDIUM)
            else config.TEXT_MODEL_EASY)


def _route(task: str | None, thinking: str) -> tuple[str, str, int | None]:
    """Resolve an explicit production task to model, effort, and output cap."""
    if not task:
        return _model_for(thinking), thinking, None
    try:
        route = config.TEXT_TASKS[task]
    except KeyError as exc:
        raise ValueError(f"unknown text-generation task: {task}") from exc
    return str(route["model"]), str(route["effort"]), int(route["max_output_tokens"])


def _messages(prompt: str, system: str | None) -> list[dict[str, str]]:
    messages = [{"role": "system", "content": system}] if system else []
    messages.append({"role": "user", "content": prompt})
    return messages


def _is_retryable(err: Exception) -> bool:
    # Match on the SDK's exception types first: OpenAI's APITimeoutError
    # stringifies as "Request timed out." and APIConnectionError as
    # "Connection error.", so neither is caught by the substring check below.
    try:
        from openai import APIConnectionError, APITimeoutError, RateLimitError

        if isinstance(err, (APITimeoutError, APIConnectionError, RateLimitError)):
            return True
    except ImportError:
        pass

    text = str(err).lower()
    return any(code in text for code in (
        "429", "resource_exhausted", "rate limit", "500", "503",
        "unavailable", "overloaded", "deadline", "timeout", "timed out",
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
    model = _model_for(thinking)
    cache_key = model_cache.key("openai-text", {
        "model": model,
        "effort": thinking,
        "system": system or "",
        "prompt": prompt,
    })
    with model_cache.locked(cache_key):
        cached = model_cache.load_json(cache_key)
        if isinstance(cached, str):
            return cached
        resp = _request(lambda: openai_client().responses.create(
            model=model,
            input=_messages(prompt, system),
            reasoning={"effort": thinking},
            prompt_cache_key=cache_key,
            store=False,
        ))
        result = (resp.output_text or "").strip()
        model_cache.save_json(cache_key, result)
        return result


def generate_structured(prompt: str, schema: type[T], *,
                        thinking: str = config.THINK_HIGH,
                        system: str | None = None,
                        task: str | None = None) -> T:
    """Generate JSON constrained to `schema` and return a validated instance.

    Uses the Responses API's native structured-output mode, so the model is
    forced to emit schema-conforming JSON and the SDK hands back a parsed
    Pydantic instance.
    """
    model, effort, max_output_tokens = _route(task, thinking)
    cache_key = model_cache.key("openai-structured", {
        "model": model,
        "effort": effort,
        "max_output_tokens": max_output_tokens,
        "verbosity": "low",
        "task": task or "",
        "system": system or "",
        "prompt": prompt,
        "schema": schema.model_json_schema(),
    })
    request = {
        "model": model,
        "input": _messages(prompt, system),
        "text_format": schema,
        "reasoning": {"effort": effort},
        "prompt_cache_key": cache_key,
        "store": False,
        # Structured fields already define the desired detail; low verbosity
        # avoids needless prose inside string fields.  The Responses API moved
        # this setting under `text`; the SDK still accepts the former top-level
        # kwarg but the live endpoint rejects it.
        "text": {"verbosity": "low"},
    }
    if max_output_tokens is not None:
        request["max_output_tokens"] = max_output_tokens
    with model_cache.locked(cache_key):
        cached = model_cache.load_json(cache_key)
        if cached is not None:
            try:
                return schema.model_validate(cached)
            except ValueError:
                pass
        resp = _request(lambda: openai_client().responses.parse(**request))
        parsed = resp.output_parsed
        if parsed is None:
            raise RuntimeError(f"{model} returned no parsable output")
        model_cache.save_json(cache_key, parsed.model_dump(mode="json"))
        return parsed


def transcribe_audio(data: bytes, mime_type: str = "audio/webm") -> str:
    """Transcribe a recording verbatim using Gemini's native audio input.

    Used by the mic flow: the creator speaks their story idea and we turn it into
    the plain text the pipeline expects. No separate STT model required.
    """
    instruction = (
        "Transcribe this recording verbatim. Return ONLY the spoken words as "
        "plain prose — no timestamps, no speaker labels, no commentary. Fix "
        "obvious disfluencies (um, uh, false starts) but change nothing else."
    )
    cache_key = model_cache.key("gemini-transcription", {
        "model": config.TRANSCRIPTION_MODEL,
        "mime_type": mime_type,
        "audio_sha256": hashlib.sha256(data).hexdigest(),
        "instruction": instruction,
    })
    with model_cache.locked(cache_key):
        cached = model_cache.load_json(cache_key)
        if isinstance(cached, str):
            return cached
        resp = _request(lambda: client().models.generate_content(
            model=config.TRANSCRIPTION_MODEL,
            contents=[
                types.Part.from_bytes(data=data, mime_type=mime_type),
                instruction,
            ],
            config=types.GenerateContentConfig(),
        ))
        result = (resp.text or "").strip()
        model_cache.save_json(cache_key, result)
        return result
