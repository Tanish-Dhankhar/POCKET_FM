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
import uuid
import wave
from pathlib import Path

from google.genai import types

from . import config
from .llm import client

# Calls reserve their rate-limit slot under a short lock, then wait and make the
# network request outside it. This preserves free-tier spacing while allowing a
# paid tier to opt into bounded parallel synthesis.
_rate_lock = threading.Lock()
_last_call_at = 0.0
_tts_slots = threading.BoundedSemaphore(config.TTS_MAX_CONCURRENCY)
_cache_locks = [threading.Lock() for _ in range(64)]


def _throttle() -> None:
    """Block until at least TTS_MIN_INTERVAL_SEC has passed since the last call."""
    global _last_call_at
    if config.TTS_MIN_INTERVAL_SEC <= 0:
        return
    with _rate_lock:
        now = time.monotonic()
        wait = max(0.0, _last_call_at + config.TTS_MIN_INTERVAL_SEC - now)
        # Reserve the next slot before sleeping so concurrent callers cannot
        # all wake and burst through the provider quota together.
        _last_call_at = now + wait
    if wait > 0:
        time.sleep(wait)


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
        _throttle()
        try:
            with _tts_slots:
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


def _cache_lock(key: str) -> threading.Lock:
    return _cache_locks[int(key[:8], 16) % len(_cache_locks)]


def _copy_cached(cached: Path, out_path: Path) -> bool:
    if not cached.exists():
        return False
    out_path.write_bytes(cached.read_bytes())
    return True


def _store_cached(source: Path, cached: Path) -> None:
    tmp = cached.with_name(f".{cached.name}.{uuid.uuid4().hex}.tmp")
    tmp.write_bytes(source.read_bytes())
    tmp.replace(cached)


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

    if cache_dir is None:
        _write_wav(out_path, _synthesize(text, voice_id))
        return out_path

    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    key = _cache_key(text, voice_id)
    cached = cache_dir / f"{key}.wav"
    # The per-key lock prevents duplicate billable synthesis for the same line.
    with _cache_lock(key):
        if _copy_cached(cached, out_path):
            return out_path
        _write_wav(out_path, _synthesize(text, voice_id))
        _store_cached(out_path, cached)
    return out_path
