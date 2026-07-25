"""Gemini TTS client — one single-speaker call per line.

Mirrors the proven call in the repo's top-level tts.py (generate_content with
response_modalities=["AUDIO"] + SpeechConfig), adds content-hash caching so
unchanged lines are never re-billed on regeneration.
"""
from __future__ import annotations

import hashlib
import random
import threading
import time
import wave
from pathlib import Path

from google.genai import types

from . import config
from .llm import client

# Free-tier TTS allows only ~3 requests/min, so calls are spaced out globally and
# 429s are retried with backoff. Guarded by a lock so concurrent renders queue
# rather than burst past the limit.
_rate_lock = threading.Lock()
_last_call_at = 0.0


def _throttle() -> None:
    """Block until at least TTS_MIN_INTERVAL_SEC has passed since the last call."""
    global _last_call_at
    if config.TTS_MIN_INTERVAL_SEC <= 0:
        return
    wait = config.TTS_MIN_INTERVAL_SEC - (time.monotonic() - _last_call_at)
    if wait > 0:
        time.sleep(wait)
    _last_call_at = time.monotonic()


def _is_retryable(err: Exception) -> bool:
    """429 (quota) and 5xx (transient overload) are both worth retrying."""
    text = str(err).lower()
    return any(s in text for s in (
        "429", "resource_exhausted", "rate limit",
        "503", "unavailable", "500", "internal", "overloaded", "high demand",
    ))


def _synthesize(text: str, voice_id: str) -> bytes:
    """One TTS call, rate-limited and retried on 429. Returns raw PCM."""
    cfg = types.GenerateContentConfig(
        response_modalities=["AUDIO"],
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice_id)
            )
        ),
    )
    last: Exception | None = None
    for attempt in range(config.TTS_MAX_RETRIES):
        with _rate_lock:
            _throttle()
            try:
                resp = client().models.generate_content(
                    model=config.TTS_MODEL, contents=text, config=cfg,
                )
                return resp.candidates[0].content.parts[0].inline_data.data
            except Exception as err:  # noqa: BLE001 — re-raised below if not transient
                if not _is_retryable(err):
                    raise
                last = err
        # Exponential backoff with jitter, outside the lock so nothing else spins.
        time.sleep(min(60.0, 2 ** attempt * (config.TTS_MIN_INTERVAL_SEC or 2.0))
                   + random.uniform(0, 1))
    raise RuntimeError(
        f"TTS failed after {config.TTS_MAX_RETRIES} attempts (rate-limited or "
        f"model unavailable): {last}"
    ) from last


def _cache_key(text: str, voice_id: str) -> str:
    raw = f"{config.TTS_MODEL}|{voice_id}|{text}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]


def _write_wav(path: Path, pcm: bytes) -> None:
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(config.TTS_CHANNELS)
        wf.setsampwidth(config.TTS_SAMPLE_WIDTH)
        wf.setframerate(config.TTS_SAMPLE_RATE)
        wf.writeframes(pcm)


def render_line(text: str, voice_id: str, out_path: str | Path,
                *, cache_dir: str | Path | None = None) -> Path:
    """Render one line of text to a WAV file in the given voice.

    `text` may contain inline emotion bracket tags like ``[Whisper]`` / ``[Fear]``.
    Returns the path to the written WAV. If a cache_dir is given and a clip with
    the same (model, voice, text) already exists there, it is copied instead of
    re-synthesised.
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    cached: Path | None = None
    if cache_dir is not None:
        cache_dir = Path(cache_dir)
        cache_dir.mkdir(parents=True, exist_ok=True)
        cached = cache_dir / f"{_cache_key(text, voice_id)}.wav"
        if cached.exists():
            out_path.write_bytes(cached.read_bytes())
            return out_path

    resp_pcm = _synthesize(text, voice_id)
    _write_wav(out_path, resp_pcm)
    if cached is not None:
        cached.write_bytes(out_path.read_bytes())
    return out_path
