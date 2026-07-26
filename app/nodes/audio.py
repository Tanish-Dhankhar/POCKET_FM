"""Audio-production nodes: TTS render, sound design, mix, deliver.

Pipeline order (see graph.CHAIN): audio (auto) -> sound_design (review) ->
mix (auto) -> deliver. gen_audio lays down the voice timeline; gen_sound_design
picks sparse cues against it; gen_mix realises them; gen_deliver snapshots state.
"""
from __future__ import annotations

import hashlib
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
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

    def render(item: tuple[int, dict[str, Any]]) -> tuple[int, str]:
        i, ln = item
        if cancelled and cancelled():
            raise InterruptedError("episode generation cancelled")
        voice = _voice_for(state, ln.get("speaker", "Narrator"))
        safe = _SAFE.sub("_", ln.get("speaker", "x"))[:20]
        out = ldir / f"{i:04d}_{safe}.wav"
        text = ln["text"].strip()
        emotion = str(ln.get("emotion") or "").strip()
        if emotion and not text.startswith("["):
            text = f"[{emotion}] {text}"
        render_line(text, voice, out, cache_dir=cache_dir)
        return i, str(out)

    rendered: dict[int, str] = {}
    workers = min(config.TTS_PARALLEL_WORKERS, max(1, len(speakable)))
    with ThreadPoolExecutor(max_workers=workers,
                            thread_name_prefix="pocketfm-tts") as executor:
        futures = [executor.submit(render, item) for item in speakable]
        for done, future in enumerate(as_completed(futures), start=1):
            i, path = future.result()
            rendered[i] = path
            if progress:
                progress(done, len(speakable))

    line_indices = [i for i, _ in speakable]
    line_files = [rendered[i] for i in line_indices]

    if cancelled and cancelled():
        raise InterruptedError("episode generation cancelled")

    track, offsets = audio_engine.concat_lines(line_files)
    line_durations_ms = []
    for position, path in enumerate(line_files):
        try:
            duration = len(audio_engine.load(path))
        except Exception:  # a custom renderer may supply a non-audio test artifact
            next_start = offsets[position + 1] if position + 1 < len(offsets) else len(track)
            duration = max(0, next_start - offsets[position])
        line_durations_ms.append(duration)
    segments = [
        {
            "line_index": line_index,
            "line_id": lines[line_index].get("id") or f"line-{line_index + 1:04d}",
            "speaker": lines[line_index].get("speaker", ""),
            "path": path,
            "start_ms": offsets[position],
            "end_ms": offsets[position] + line_durations_ms[position],
            "duration_ms": line_durations_ms[position],
        }
        for position, (line_index, path) in enumerate(zip(line_indices, line_files))
    ]
    voices_path = _ep_dir(state, number) / f"ep{int(number):02d}_voices.wav"
    audio_engine.export(track, voices_path)

    manifest = {
        "voices": str(voices_path),
        "offsets": offsets,
        "total_ms": len(track),
        "line_files": line_files,
        "line_indices": line_indices,
        "line_durations_ms": line_durations_ms,
        "segments": segments,
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
def _enforce(plan: schemas.SoundPlan, offsets: list[int], total_ms: int, *,
             line_durations_ms: list[int] | None = None,
             line_indices: list[int] | None = None) -> dict[str, Any]:
    n = len(offsets)
    line_indices = line_indices or list(range(n))
    position_for = {line: position for position, line in enumerate(line_indices)}
    moods, sfx_keys = set(assets.music_moods()), set(assets.sfx_keys())

    def clamp(value: Any, low: float, high: float, default: float) -> float:
        try:
            return min(high, max(low, float(value)))
        except (TypeError, ValueError):
            return default

    def line_start(i: int) -> int:
        position = position_for.get(i)
        return offsets[position] if position is not None else 0

    def line_end(i: int) -> int:
        position = position_for.get(i)
        if position is None:
            return 0
        if line_durations_ms and position < len(line_durations_ms):
            return min(total_ms, offsets[position] + max(0, int(line_durations_ms[position])))
        return offsets[position + 1] if position + 1 < n else total_ms

    # --- Dialogue: bounded, non-destructive edits on existing takes --------
    kept_dialogue = []
    for cue in sorted(plan.dialogue, key=lambda c: c.line):
        if cue.line not in position_for:
            continue
        kept_dialogue.append({
            "line": cue.line,
            "pause_before_ms": int(clamp(cue.pause_before_ms, 0, 2_500, 0)),
            "pause_after_ms": int(clamp(cue.pause_after_ms, 0, 2_500,
                                         config.PAUSE_BETWEEN_LINES_MS)),
            "rate": clamp(cue.rate, 0.9, 1.1, 1.0),
            "gain_db": clamp(cue.gain_db, -8.0, 4.0, 0.0),
            "overlap_previous_ms": int(clamp(cue.overlap_previous_ms, 0, 600, 0)),
            "interrupt": bool(cue.interrupt),
        })

    # --- SFX: valid key, in range, spaced out, de-duplicated -----------------
    kept_sfx, last_t = [], -1e9
    for cue in sorted(plan.sfx, key=lambda c: c.line):
        if cue.name not in sfx_keys or cue.line not in position_for:
            continue
        t = min(total_ms, max(0, line_start(cue.line)
                              + int(clamp(cue.offset_ms, -5_000, 5_000, 0))))
        if (t - last_t) / 1000.0 < config.MIN_SECONDS_BETWEEN_SFX:
            continue
        kept_sfx.append({
            "line": cue.line, "name": cue.name, "at_ms": t,
            "gain_db": clamp(cue.gain_db, -24.0, 6.0, config.SFX_GAIN_DB),
            "pan": clamp(cue.pan, -1.0, 1.0, 0.0),
        })
        last_t = t

    # --- Music: valid mood, spaced, non-overlapping, coverage-capped ---------
    kept_music, covered, last_end = [], 0, -1e9
    budget = config.MAX_MUSIC_COVERAGE * max(1, total_ms)
    for cue in sorted(plan.music, key=lambda c: c.start_line):
        if cue.mood not in moods:
            continue
        valid_lines = sorted(position_for)
        if not valid_lines:
            continue
        s, e = max(valid_lines[0], cue.start_line), min(valid_lines[-1], cue.end_line)
        while s not in position_for and s <= e:
            s += 1
        while e not in position_for and e >= s:
            e -= 1
        if e < s:
            continue
        start_ms, end_ms = line_start(s), line_end(e)
        if start_ms - last_end < config.MIN_SECONDS_BETWEEN_MUSIC_CUES * 1000:
            continue
        span = end_ms - start_ms
        if covered + span > budget:
            continue
        kept_music.append({
            "start_line": s, "end_line": e, "mood": cue.mood,
            "start_ms": start_ms, "end_ms": end_ms,
            "gain_db": clamp(cue.gain_db, -36.0, -3.0, config.MUSIC_DUCK_DB),
            "fade_in_ms": int(clamp(cue.fade_in_ms, 0, 2_000, config.MUSIC_FADE_MS)),
            "fade_out_ms": int(clamp(cue.fade_out_ms, 0, 2_000, config.MUSIC_FADE_MS)),
            "duck_under_dialogue": bool(cue.duck_under_dialogue),
            "duck_db": clamp(cue.duck_db, -24.0, 0.0, -10.0),
            "duck_attack_ms": int(clamp(cue.duck_attack_ms, 0, 500, 80)),
            "duck_hold_ms": int(clamp(cue.duck_hold_ms, 0, 2_000, 180)),
            "duck_release_ms": int(clamp(cue.duck_release_ms, 0, 2_000, 420)),
        })
        covered += span
        last_end = end_ms

    # --- Ambience: valid asset and range; quiet enough to preserve dialogue --
    kept_ambience = []
    for cue in sorted(plan.ambience, key=lambda c: c.start_line):
        if cue.name not in sfx_keys or cue.start_line not in position_for:
            continue
        end_line = min(max(position_for), cue.end_line)
        if end_line not in position_for or end_line < cue.start_line:
            continue
        kept_ambience.append({
            "start_line": cue.start_line, "end_line": end_line, "name": cue.name,
            "start_ms": line_start(cue.start_line), "end_ms": line_end(end_line),
            "gain_db": clamp(cue.gain_db, -48.0, -12.0, -24.0),
            "fade_in_ms": int(clamp(cue.fade_in_ms, 0, 2_000, 800)),
            "fade_out_ms": int(clamp(cue.fade_out_ms, 0, 2_000, 800)),
        })

    return {"dialogue": kept_dialogue, "music": kept_music,
            "sfx": kept_sfx, "ambience": kept_ambience}


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
        schemas.SoundPlan, task="sound_design", system=prompts.SYSTEM,
    )
    plan = _enforce(
        raw, info["offsets"], info["total_ms"],
        line_durations_ms=info.get("line_durations_ms"),
        line_indices=info.get("line_indices"),
    )
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

    plan = (state.get("sound_plans", {}).get(str(number))
            or store.load_episode(sid, number)["sound_plan"]
            or {"dialogue": [], "music": [], "sfx": [], "ambience": []})

    source_segments = info.get("segments") or []
    line_indices = info.get("line_indices") or [
        segment.get("line_index", i) for i, segment in enumerate(source_segments)
    ] or list(range(len(info.get("line_files", []))))
    items = []
    for position, path in enumerate(info.get("line_files", [])):
        line_index = line_indices[position] if position < len(line_indices) else position
        segment = source_segments[position] if position < len(source_segments) else {}
        items.append({
            "line_index": line_index,
            "line_id": segment.get("line_id") or f"line-{line_index + 1:04d}",
            "speaker": segment.get("speaker", ""),
            "path": path,
        })
    if items:
        track, segments, offsets = audio_engine.assemble_dialogue(
            items, plan.get("dialogue", []),
            default_pause_ms=config.PAUSE_BETWEEN_LINES_MS,
        )
    else:
        track = audio_engine.load(info["voices"])
        segments, offsets = source_segments, info.get("offsets", [])

    for cue in plan.get("ambience", []):
        path = assets.sfx_path(cue["name"])
        if path and path.exists():
            track = audio_engine.place_looped_ambience(track, {**cue, "path": path})

    for cue in plan.get("music", []):
        path = assets.music_path(cue["mood"])
        if path and path.exists():
            shaped = {
                **cue, "path": path,
                "attack_ms": cue.get("duck_attack_ms", 80),
                "hold_ms": cue.get("duck_hold_ms", 180),
                "release_ms": cue.get("duck_release_ms", 420),
                "duck_db": cue.get("duck_db", -10.0) if cue.get(
                    "duck_under_dialogue", True) else 0.0,
            }
            track = audio_engine.place_music_ducked(track, shaped, segments)
    for cue in plan.get("sfx", []):
        path = assets.sfx_path(cue["name"])
        if path and path.exists():
            track = audio_engine.place_sfx(
                track, path, cue["at_ms"], int(round(cue.get("gain_db", config.SFX_GAIN_DB))))

    final = _ep_dir(state, number) / f"ep{int(number):02d}_final.wav"
    audio_engine.export(track, final)
    info.update({
        "final": str(final), "offsets": offsets, "segments": segments,
        "total_ms": len(track),
    })
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
