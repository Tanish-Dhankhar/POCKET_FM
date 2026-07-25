"""Audio-production nodes: TTS render, sound design, mix, deliver.

Pipeline order (see graph.CHAIN): audio (auto) -> sound_design (review) ->
mix (auto) -> deliver. gen_audio lays down the voice timeline; gen_sound_design
picks sparse cues against it; gen_mix realises them; gen_deliver snapshots state.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

from .. import assets, audio_engine, config, prompts, schemas, store
from ..llm import generate_structured
from ..tts import render_line
from ..state import SeriesState

_DEFAULT_NARRATOR_VOICE = "Charon"
_SAFE = re.compile(r"[^A-Za-z0-9]+")


def _ep_dir(state: SeriesState, num: int) -> Path:
    return store.episode_dir(state["series_id"], num)


def _voice_for(state: SeriesState, speaker: str) -> str:
    cast = state.get("voice_cast", {})
    if speaker in cast:
        return cast[speaker]
    if speaker.lower() == "narrator":
        return cast.get("Narrator", _DEFAULT_NARRATOR_VOICE)
    # Deterministic fallback so an uncast character keeps the same voice across
    # episodes and server restarts. Uses a content hash, not builtin hash(),
    # which is randomly salted per process (PYTHONHASHSEED).
    digest = hashlib.sha256(speaker.encode("utf-8")).hexdigest()
    return config.VOICE_NAMES[int(digest, 16) % len(config.VOICE_NAMES)]


# --------------------------------------------------------------------------- #
# Stage 8 — Audio generation (TTS per line, concatenated)
# --------------------------------------------------------------------------- #
def render_episode_audio(state: SeriesState, number: int, progress=None,
                         cancelled=None) -> dict[str, Any]:
    """TTS every line of ONE episode, stitch it, and persist audio.json.

    `progress(done, total)` is called after each line so a job runner can report
    real progress (TTS is the slow part — often rate-limited to ~3 lines/minute).
    """
    sid = state["series_id"]
    lines = state.get("scripts", {}).get(str(number), [])
    if not lines:
        raise ValueError(f"episode {number} has no script yet")

    cache_dir = config.TTS_CACHE_DIR
    ldir = store.lines_dir(sid, number)
    speakable = [(i, ln) for i, ln in enumerate(lines) if (ln.get("text") or "").strip()]

    line_files: list[str] = []
    for done, (i, ln) in enumerate(speakable, start=1):
        if cancelled and cancelled():
            raise InterruptedError("episode generation cancelled")
        voice = _voice_for(state, ln.get("speaker", "Narrator"))
        safe = _SAFE.sub("_", ln.get("speaker", "x"))[:20]
        out = ldir / f"{i:04d}_{safe}.wav"
        render_line(ln["text"].strip(), voice, out, cache_dir=cache_dir)
        line_files.append(str(out))
        if progress:
            progress(done, len(speakable))

    if cancelled and cancelled():
        raise InterruptedError("episode generation cancelled")

    track, offsets = audio_engine.concat_lines(line_files)
    voices_path = _ep_dir(state, number) / f"ep{int(number):02d}_voices.wav"
    audio_engine.export(track, voices_path)

    manifest = {
        "voices": str(voices_path),
        "offsets": offsets,
        "total_ms": len(track),
        "line_files": line_files,
    }
    store.save_episode_audio(sid, number, manifest)
    return manifest


def gen_audio(state: SeriesState) -> dict[str, Any]:
    manifest: dict[str, Any] = dict(state.get("audio_manifest", {}))
    for num in state.get("scripts", {}):
        manifest[str(num)] = render_episode_audio(state, int(num))
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


def design_episode_sound(state: SeriesState, number: int) -> dict[str, Any]:
    """Pick + persist sparse sound cues for ONE episode."""
    lines = state.get("scripts", {}).get(str(number), [])
    info = state.get("audio_manifest", {}).get(str(number)) or \
        store.load_episode(state["series_id"], number)["audio"]
    if not lines or not info:
        raise ValueError(f"episode {number} needs a script and rendered audio first")
    raw = generate_structured(
        prompts.sound_design(lines, assets.music_moods(), assets.sfx_keys(),
                            state.get("feedback", "")),
        schemas.SoundPlan, thinking=config.THINK_LOW, system=prompts.SYSTEM,
    )
    plan = _enforce(raw, info["offsets"], info["total_ms"])
    store.save_episode_sound_plan(state["series_id"], number, plan)
    return plan


def gen_sound_design(state: SeriesState) -> dict[str, Any]:
    plans: dict[str, Any] = dict(state.get("sound_plans", {}))
    audio_manifest = state.get("audio_manifest", {})
    for num in state.get("scripts", {}):
        if audio_manifest.get(str(num)):
            plans[str(num)] = design_episode_sound(state, int(num))
    return {"sound_plans": plans, "stage": "sound_design"}


# --------------------------------------------------------------------------- #
# Stage 9b — Mix (realise the sound plan over the voice timeline)
# --------------------------------------------------------------------------- #
def mix_episode(state: SeriesState, number: int) -> dict[str, Any]:
    """Overlay music + SFX for ONE episode and persist the final wav."""
    sid = state["series_id"]
    info = dict(state.get("audio_manifest", {}).get(str(number))
                or store.load_episode(sid, number)["audio"])
    if not info.get("voices"):
        raise ValueError(f"episode {number} has no rendered voices yet")

    track = audio_engine.load(info["voices"])
    plan = (state.get("sound_plans", {}).get(str(number))
            or store.load_episode(sid, number)["sound_plan"]
            or {"music": [], "sfx": []})

    for cue in plan.get("music", []):
        path = assets.music_path(cue["mood"])
        if path and path.exists():
            track = audio_engine.place_music(track, path, cue["start_ms"], cue["end_ms"])
    for cue in plan.get("sfx", []):
        path = assets.sfx_path(cue["name"])
        if path and path.exists():
            track = audio_engine.place_sfx(track, path, cue["at_ms"])

    final = _ep_dir(state, number) / f"ep{int(number):02d}_final.wav"
    audio_engine.export(track, final)
    info["final"] = str(final)
    store.save_episode_audio(sid, number, info)
    return info


def gen_mix(state: SeriesState) -> dict[str, Any]:
    manifest: dict[str, Any] = dict(state.get("audio_manifest", {}))
    for num, info in list(manifest.items()):
        if info.get("voices"):
            manifest[str(num)] = mix_episode(state, int(num))
    return {"audio_manifest": manifest, "stage": "mix"}


# --------------------------------------------------------------------------- #
# Deliver — snapshot the index card
# --------------------------------------------------------------------------- #
def gen_deliver(state: SeriesState) -> dict[str, Any]:
    store.save_index(state["series_id"], stage="deliver",
                     ep_count=state.get("ep_count"),
                     ep_minutes=state.get("ep_minutes"))
    return {"stage": "deliver"}
