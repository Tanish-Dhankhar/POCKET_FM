"""Audio-production nodes: TTS render, sound design, mix, deliver.

Pipeline order (see graph.CHAIN): audio (auto) -> sound_design (review) ->
mix (auto) -> deliver. gen_audio lays down the voice timeline; gen_sound_design
picks sparse cues against it; gen_mix realises them; gen_deliver snapshots state.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .. import assets, audio_engine, config, prompts, schemas
from ..llm import generate_structured
from ..tts import render_line
from ..state import SeriesState

_DEFAULT_NARRATOR_VOICE = "Charon"
_SAFE = re.compile(r"[^A-Za-z0-9]+")


def _ep_dir(state: SeriesState, num: int) -> Path:
    return config.OUTPUT_DIR / state["series_id"] / f"ep{int(num):02d}"


def _voice_for(state: SeriesState, speaker: str) -> str:
    cast = state.get("voice_cast", {})
    if speaker in cast:
        return cast[speaker]
    if speaker.lower() == "narrator":
        return cast.get("Narrator", _DEFAULT_NARRATOR_VOICE)
    # deterministic fallback so an uncast character still gets a stable voice
    idx = abs(hash(speaker)) % len(config.VOICE_NAMES)
    return config.VOICE_NAMES[idx]


# --------------------------------------------------------------------------- #
# Stage 8 — Audio generation (TTS per line, concatenated)
# --------------------------------------------------------------------------- #
def gen_audio(state: SeriesState) -> dict[str, Any]:
    manifest: dict[str, Any] = dict(state.get("audio_manifest", {}))
    cache_dir = config.OUTPUT_DIR / state["series_id"] / "tts_cache"

    for num, lines in state.get("scripts", {}).items():
        ep_dir = _ep_dir(state, int(num))
        lines_dir = ep_dir / "lines"
        line_files: list[str] = []
        for i, ln in enumerate(lines):
            text = (ln.get("text") or "").strip()
            if not text:
                continue
            voice = _voice_for(state, ln.get("speaker", "Narrator"))
            safe = _SAFE.sub("_", ln.get("speaker", "x"))[:20]
            out = lines_dir / f"{i:04d}_{safe}.wav"
            render_line(text, voice, out, cache_dir=cache_dir)
            line_files.append(str(out))

        if not line_files:
            continue
        track, offsets = audio_engine.concat_lines(line_files)
        voices_path = ep_dir / f"ep{int(num):02d}_voices.wav"
        audio_engine.export(track, voices_path)
        manifest[str(num)] = {
            "voices": str(voices_path),
            "offsets": offsets,
            "total_ms": len(track),
            "line_files": line_files,
        }
    return {"audio_manifest": manifest, "stage": "audio"}


# --------------------------------------------------------------------------- #
# Stage 9a — Sound design (LLM picks sparse cues, then we enforce restraint)
# --------------------------------------------------------------------------- #
def _enforce(plan: schemas.SoundPlan, offsets: list[int], total_ms: int
             ) -> dict[str, Any]:
    n = len(offsets)
    moods, sfx_keys = set(assets.music_moods()), set(assets.sfx_keys())

    def line_start(i: int) -> int:
        return offsets[i] if 0 <= i < n else 0

    def line_end(i: int) -> int:
        return offsets[i + 1] if i + 1 < n else total_ms

    # --- SFX: valid key, in range, spaced out, de-duplicated -----------------
    kept_sfx, last_t = [], -1e9
    for cue in sorted(plan.sfx, key=lambda c: c.line):
        if cue.name not in sfx_keys or not (0 <= cue.line < n):
            continue
        t = line_start(cue.line)
        if (t - last_t) / 1000.0 < config.MIN_SECONDS_BETWEEN_SFX:
            continue
        kept_sfx.append({"line": cue.line, "name": cue.name, "at_ms": t})
        last_t = t

    # --- Music: valid mood, spaced, non-overlapping, coverage-capped ---------
    kept_music, covered, last_end = [], 0, -1e9
    budget = config.MAX_MUSIC_COVERAGE * max(1, total_ms)
    for cue in sorted(plan.music, key=lambda c: c.start_line):
        if cue.mood not in moods:
            continue
        s, e = max(0, cue.start_line), min(n - 1, cue.end_line)
        if e < s:
            continue
        start_ms, end_ms = line_start(s), line_end(e)
        if start_ms - last_end < config.MIN_SECONDS_BETWEEN_MUSIC_CUES * 1000:
            continue
        span = end_ms - start_ms
        if covered + span > budget:
            continue
        kept_music.append({"start_line": s, "end_line": e, "mood": cue.mood,
                           "start_ms": start_ms, "end_ms": end_ms})
        covered += span
        last_end = end_ms

    return {"music": kept_music, "sfx": kept_sfx}


def gen_sound_design(state: SeriesState) -> dict[str, Any]:
    plans: dict[str, Any] = dict(state.get("sound_plans", {}))
    audio_manifest = state.get("audio_manifest", {})
    for num, lines in state.get("scripts", {}).items():
        info = audio_manifest.get(str(num))
        if not info:
            continue
        raw = generate_structured(
            prompts.sound_design(lines, assets.music_moods(), assets.sfx_keys(),
                                state.get("feedback", "")),
            schemas.SoundPlan, thinking=config.THINK_LOW, system=prompts.SYSTEM,
        )
        plans[str(num)] = _enforce(raw, info["offsets"], info["total_ms"])
    return {"sound_plans": plans, "stage": "sound_design"}


# --------------------------------------------------------------------------- #
# Stage 9b — Mix (realise the sound plan over the voice timeline)
# --------------------------------------------------------------------------- #
def gen_mix(state: SeriesState) -> dict[str, Any]:
    manifest: dict[str, Any] = dict(state.get("audio_manifest", {}))
    for num, info in list(manifest.items()):
        if "voices" not in info:
            continue
        track = audio_engine.load(info["voices"])
        plan = state.get("sound_plans", {}).get(str(num), {"music": [], "sfx": []})

        for cue in plan.get("music", []):
            path = assets.music_path(cue["mood"])
            if path and path.exists():
                track = audio_engine.place_music(track, path, cue["start_ms"], cue["end_ms"])
        for cue in plan.get("sfx", []):
            path = assets.sfx_path(cue["name"])
            if path and path.exists():
                track = audio_engine.place_sfx(track, path, cue["at_ms"])

        final = _ep_dir(state, int(num)) / f"ep{int(num):02d}_final.wav"
        audio_engine.export(track, final)
        info["final"] = str(final)
        manifest[str(num)] = info
    return {"audio_manifest": manifest, "stage": "mix"}


# --------------------------------------------------------------------------- #
# Deliver — snapshot the full series state to disk
# --------------------------------------------------------------------------- #
def gen_deliver(state: SeriesState) -> dict[str, Any]:
    out = config.OUTPUT_DIR / state["series_id"]
    out.mkdir(parents=True, exist_ok=True)
    (out / "series.json").write_text(json.dumps(state, indent=2, default=str))
    return {"stage": "deliver"}
