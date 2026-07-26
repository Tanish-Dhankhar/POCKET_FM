"""Gemini TTS client — one single-speaker call per line.

Mirrors the proven call in the repo's top-level tts.py (generate_content with
response_modalities=["AUDIO"] + SpeechConfig), adds content-hash caching so
unchanged lines are never re-billed on regeneration.
"""
from __future__ import annotations

import hashlib
import random
import re
import threading
import time
import uuid
import wave
from pathlib import Path

from google import genai
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
_lanes_lock = threading.Lock()
_lanes_signature: tuple[str, ...] = ()
_lanes: list[dict] = []
_next_lane = 0


def _throttle(lane: dict | None = None) -> None:
    """Block until at least TTS_MIN_INTERVAL_SEC has passed since the last call."""
    global _last_call_at
    if config.TTS_MIN_INTERVAL_SEC <= 0:
        return
    lock = lane["lock"] if lane is not None else _rate_lock
    with lock:
        now = time.monotonic()
        previous = lane["last_call_at"] if lane is not None else _last_call_at
        wait = max(0.0, previous + config.TTS_MIN_INTERVAL_SEC - now)
        # Reserve the next slot before sleeping so concurrent callers cannot
        # all wake and burst through the provider quota together.
        if lane is not None:
            lane["last_call_at"] = now + wait
        else:
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


def _is_invalid_key(err: Exception) -> bool:
    text = str(err).lower()
    return any(marker in text for marker in (
        "api_key_invalid", "invalid api key", "401", "unauthenticated",
    ))


def _configured_lanes() -> list[dict]:
    """Return per-key clients, rebuilding when configuration changes in tests."""
    global _lanes_signature, _lanes, _next_lane
    signature = tuple(config.GEMINI_API_KEYS)
    with _lanes_lock:
        if signature != _lanes_signature:
            _lanes_signature = signature
            _next_lane = 0
            _lanes = []
            if len(signature) > 1:
                _lanes = [
                    {
                        "key": key,
                        "client": genai.Client(api_key=key),
                        "disabled": False,
                        "last_call_at": 0.0,
                        "lock": threading.Lock(),
                    }
                    for key in signature
                ]
        return _lanes


def _next_available_lane() -> dict | None:
    global _next_lane
    lanes = _configured_lanes()
    if not lanes:
        return None
    with _lanes_lock:
        for _ in range(len(lanes)):
            lane = lanes[_next_lane % len(lanes)]
            _next_lane = (_next_lane + 1) % len(lanes)
            if not lane["disabled"]:
                return lane
    return None


def _generate(cfg, text: str):
    """Call one healthy key lane; invalid keys are disabled for this process."""
    lanes = _configured_lanes()
    if not lanes:
        _throttle()
        return client().models.generate_content(
            model=config.TTS_MODEL, contents=text, config=cfg,
        )

    last_invalid: Exception | None = None
    for _ in range(len(lanes)):
        lane = _next_available_lane()
        if lane is None:
            break
        _throttle(lane)
        try:
            return lane["client"].models.generate_content(
                model=config.TTS_MODEL, contents=text, config=cfg,
            )
        except Exception as err:  # provider SDK exposes several auth exceptions
            if not _is_invalid_key(err):
                raise
            lane["disabled"] = True
            last_invalid = err
    raise RuntimeError(f"all configured Gemini API keys are invalid: {last_invalid}") \
        from last_invalid


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
        try:
            with _tts_slots:
                resp = _generate(cfg, text)
                try:
                    data = resp.candidates[0].content.parts[0].inline_data.data
                except (AttributeError, IndexError, TypeError):
                    data = None
                if not data:
                    # The preview endpoint can occasionally return a candidate with
                    # no audio part under load. Treat it like a transient unavailable
                    # response so the next retry can use another configured key lane.
                    raise RuntimeError("TTS model unavailable: response contained no audio data")
                return data
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


_OPENAI_VOICES = {
    "Achernar": "coral",
    "Algenib": "onyx",
    "Gacrux": "shimmer",
    "Leda": "nova",
    "Charon": "echo",
}
_EMOTION_PREFIX = re.compile(r"^\[([^]]+)\]\s*")


def _write_openai_fallback(path: Path, text: str, voice_id: str) -> None:
    """Write a WAV through OpenAI only after the primary provider exhausts retries."""
    if not (config.TTS_OPENAI_FALLBACK_ENABLED and config.OPENAI_API_KEY):
        raise RuntimeError("OpenAI TTS fallback is disabled or not configured")
    match = _EMOTION_PREFIX.match(text)
    emotion = match.group(1) if match else "natural"
    spoken_text = text[match.end():] if match else text
    from openai import OpenAI
    response = OpenAI(
        api_key=config.OPENAI_API_KEY,
        timeout=60,
    ).audio.speech.create(
        model=config.TTS_OPENAI_FALLBACK_MODEL,
        voice=_OPENAI_VOICES.get(voice_id, "alloy"),
        input=spoken_text,
        instructions=(
            "Naturalistic cinematic audio-drama performance. "
            f"Delivery: {emotion}. Keep it intimate and emotionally truthful. "
            "Speak exactly the supplied words; do not add an introduction."
        ),
        response_format="wav",
    )
    response.write_to_file(path)


def _render_uncached(text: str, voice_id: str, out_path: Path) -> None:
    try:
        _write_wav(out_path, _synthesize(text, voice_id))
    except Exception:
        if not (config.TTS_OPENAI_FALLBACK_ENABLED and config.OPENAI_API_KEY):
            raise
        _write_openai_fallback(out_path, text, voice_id)


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
        _render_uncached(text, voice_id, out_path)
        return out_path

    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    key = _cache_key(text, voice_id)
    cached = cache_dir / f"{key}.wav"
    # The per-key lock prevents duplicate billable synthesis for the same line.
    with _cache_lock(key):
        if _copy_cached(cached, out_path):
            return out_path
        _render_uncached(text, voice_id, out_path)
        _store_cached(out_path, cached)
    return out_path
