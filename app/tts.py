"""Gemini TTS client — one single-speaker call per line.

Mirrors the proven call in the repo's top-level tts.py (generate_content with
response_modalities=["AUDIO"] + SpeechConfig), adds content-hash caching so
unchanged lines are never re-billed on regeneration.
"""
from __future__ import annotations

import hashlib
import wave
from pathlib import Path

from google.genai import types

from . import config
from .llm import client


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

    resp = client().models.generate_content(
        model=config.TTS_MODEL,
        contents=text,
        config=types.GenerateContentConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name=voice_id,
                    )
                )
            ),
        ),
    )
    pcm = resp.candidates[0].content.parts[0].inline_data.data
    _write_wav(out_path, pcm)
    if cached is not None:
        cached.write_bytes(out_path.read_bytes())
    return out_path
