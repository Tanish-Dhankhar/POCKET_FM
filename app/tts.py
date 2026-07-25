"""Gemini TTS with content caching, multi-key lanes, and safe retries.

Each configured API key gets an independent client, throttle clock, and lock. Episode
rendering can therefore synthesize one line per key concurrently without sending bursts
through the same quota lane.
"""
from __future__ import annotations

import hashlib
import random
import shutil
import threading
import time
import wave
from dataclasses import dataclass, field
from pathlib import Path

from google import genai
from google.genai import types

from . import config
from .llm import client

# Single-key compatibility lane. This is also useful for SDK-boundary tests that
# monkeypatch app.llm.client.
_rate_lock = threading.Lock()
_last_call_at = 0.0


@dataclass
class _KeyLane:
    """An independent client and rate-limit clock for one secret key."""

    api_key: str
    lock: threading.Lock = field(default_factory=threading.Lock)
    last_call_at: float = 0.0
    sdk_client: object | None = None
    disabled: bool = False

    def get_client(self):
        if self.sdk_client is None:
            self.sdk_client = genai.Client(api_key=self.api_key)
        return self.sdk_client


_lanes_guard = threading.Lock()
_lanes: list[_KeyLane] = []
_lanes_signature: tuple[str, ...] = ()
_next_lane = 0

# Repeated lines can reach the same cache file from different workers. A path lock
# prevents duplicate billing and partial-file copies.
_cache_locks_guard = threading.Lock()
_cache_locks: dict[str, threading.Lock] = {}


def _throttle() -> None:
    """Single-key throttle retained for backwards compatibility."""
    global _last_call_at
    if config.TTS_MIN_INTERVAL_SEC <= 0:
        return
    wait = config.TTS_MIN_INTERVAL_SEC - (time.monotonic() - _last_call_at)
    if wait > 0:
        time.sleep(wait)
    _last_call_at = time.monotonic()


def _configured_lanes() -> list[_KeyLane]:
    global _lanes, _lanes_signature
    signature = tuple(config.GEMINI_API_KEYS)
    with _lanes_guard:
        if signature != _lanes_signature:
            _lanes = [_KeyLane(key) for key in signature]
            _lanes_signature = signature
        return _lanes


def _take_lane() -> _KeyLane:
    global _next_lane
    lanes = _configured_lanes()
    active = [lane for lane in lanes if not lane.disabled]
    if not active:
        raise RuntimeError("No usable Gemini API key remains in the TTS pool")
    with _lanes_guard:
        lane = active[_next_lane % len(active)]
        _next_lane += 1
    return lane


def _throttle_lane(lane: _KeyLane) -> None:
    if config.TTS_MIN_INTERVAL_SEC <= 0:
        return
    wait = config.TTS_MIN_INTERVAL_SEC - (time.monotonic() - lane.last_call_at)
    if wait > 0:
        time.sleep(wait)
    lane.last_call_at = time.monotonic()


def _is_retryable(err: Exception) -> bool:
    text = str(err).lower()
    return any(marker in text for marker in (
        "429", "resource_exhausted", "rate limit",
        "503", "unavailable", "500", "internal", "overloaded", "high demand",
    ))


def _is_key_error(err: Exception) -> bool:
    """Errors isolated to one credential; another lane may still succeed."""
    text = str(err).lower()
    return any(marker in text for marker in (
        "api_key_invalid", "api key not valid", "invalid api key",
        "401", "unauthenticated", "403", "permission_denied",
    ))


def _speech_config(voice_id: str) -> types.GenerateContentConfig:
    return types.GenerateContentConfig(
        response_modalities=["AUDIO"],
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice_id)
            )
        ),
    )


def _pcm_from_response(response) -> bytes:
    return response.candidates[0].content.parts[0].inline_data.data


def _synthesize_single_key(text: str, cfg: types.GenerateContentConfig) -> bytes:
    last: Exception | None = None
    for attempt in range(config.TTS_MAX_RETRIES):
        with _rate_lock:
            _throttle()
            try:
                response = client().models.generate_content(
                    model=config.TTS_MODEL, contents=text, config=cfg,
                )
                return _pcm_from_response(response)
            except Exception as err:  # noqa: BLE001
                if not _is_retryable(err):
                    raise
                last = err
        time.sleep(min(60.0, 2 ** attempt * (config.TTS_MIN_INTERVAL_SEC or 2.0))
                   + random.uniform(0, 1))
    raise RuntimeError(
        f"TTS failed after {config.TTS_MAX_RETRIES} attempts "
        f"(rate-limited or model unavailable): {last}"
    ) from last


def _synthesize_multi_key(text: str, cfg: types.GenerateContentConfig) -> bytes:
    last: Exception | None = None
    attempts = max(config.TTS_MAX_RETRIES, len(config.GEMINI_API_KEYS) * 2)
    for attempt in range(attempts):
        # Retries rotate to another lane. Every lane still independently enforces
        # its own minimum interval.
        lane = _take_lane()
        with lane.lock:
            _throttle_lane(lane)
            try:
                response = lane.get_client().models.generate_content(
                    model=config.TTS_MODEL, contents=text, config=cfg,
                )
                return _pcm_from_response(response)
            except Exception as err:  # noqa: BLE001
                if _is_key_error(err):
                    lane.disabled = True
                    last = err
                    continue
                if not _is_retryable(err):
                    raise
                last = err
        time.sleep(min(8.0, 0.5 * (2 ** attempt)) + random.uniform(0, 0.4))
    raise RuntimeError(
        f"TTS failed after {attempts} attempts across the key pool "
        f"(rate-limited or model unavailable): {last}"
    ) from last


def _synthesize(text: str, voice_id: str) -> bytes:
    cfg = _speech_config(voice_id)
    if len(config.GEMINI_API_KEYS) <= 1:
        return _synthesize_single_key(text, cfg)
    return _synthesize_multi_key(text, cfg)


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
    """Render one line, copying from the content cache when possible."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    cached: Path | None = None
    if cache_dir is not None:
        cache_dir = Path(cache_dir)
        cache_dir.mkdir(parents=True, exist_ok=True)
        cached = cache_dir / f"{_cache_key(text, voice_id)}.wav"
        if cached.exists():
            shutil.copyfile(cached, out_path)
            return out_path

    lock_key = str(cached or out_path.resolve())
    with _cache_locks_guard:
        cache_lock = _cache_locks.setdefault(lock_key, threading.Lock())

    with cache_lock:
        if cached is not None and cached.exists():
            shutil.copyfile(cached, out_path)
            return out_path
        pcm = _synthesize(text, voice_id)
        _write_wav(out_path, pcm)
        if cached is not None:
            shutil.copyfile(out_path, cached)
    return out_path
