"""Render the no-narrator emotional-fight demo with one TTS take per line.

The script creates a normal Storywave series/episode on disk, renders each line
only when its immutable WAV is missing, and then performs every dramatic change
in the post-TTS editor.  Re-running it remixes the existing takes unless
``--force-voices`` is supplied.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from pydub import AudioSegment

from app import assets, audio_engine, config, store
from app.nodes import audio as audio_nodes


SERIES_ID = "emotional-fight-demo"
EPISODE_NUMBER = 1

SCRIPT = [
    {
        "id": "line-0001", "speaker": "Maya", "emotion": "Trembling",
        "text": "You packed the blue mug.",
    },
    {
        "id": "line-0002", "speaker": "Daniel", "emotion": "Cold",
        "text": "Maya... it's a mug.",
    },
    {
        "id": "line-0003", "speaker": "Maya", "emotion": "Trembling",
        "text": (
            "No. My mother gave us that. You said you were taking clothes, "
            "not... not pieces of us."
        ),
    },
    {
        "id": "line-0004", "speaker": "Daniel", "emotion": "Cold",
        "text": "There hasn't been an us in months.",
    },
    {
        "id": "line-0005", "speaker": "Maya", "emotion": "Anger",
        "text": "Because every time I reached for you, you vanished into that phone.",
    },
    {
        "id": "line-0006", "speaker": "Daniel", "emotion": "Anger",
        "text": "Because every conversation became a trial!",
    },
    {
        "id": "line-0007", "speaker": "Maya", "emotion": "Pleading",
        "text": (
            "I wasn't putting you on trial. I was begging you to look at me, "
            "and if you'd just let me finish for once—"
        ),
    },
    {
        "id": "line-0008", "speaker": "Daniel", "emotion": "Shouting",
        "text": "Enough! Stop making me the monster!",
    },
    {
        "id": "line-0009", "speaker": "Daniel", "emotion": "Trembling",
        "text": "I don't know how to stay without hurting you.",
    },
    {
        "id": "line-0010", "speaker": "Maya", "emotion": "Sad",
        "text": "You already did.",
    },
]

MUSIC_PATH = assets.music_path("emotional")
ROOM_TONE_PATH = assets.sfx_path("room_tone")
SNIFF_PATH = assets.sfx_path("post_crying_sniff")
CUP_PATH = assets.sfx_path("tea_cup_clank")


def _sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _conform(segment: AudioSegment, *, channels: int = 2) -> AudioSegment:
    return (segment.set_frame_rate(config.TTS_SAMPLE_RATE)
            .set_sample_width(config.TTS_SAMPLE_WIDTH)
            .set_channels(channels))


def _blank(duration_ms: int) -> AudioSegment:
    return (AudioSegment.silent(duration=duration_ms, frame_rate=config.TTS_SAMPLE_RATE)
            .set_sample_width(config.TTS_SAMPLE_WIDTH)
            .set_channels(2))


def _overlay_span(track: AudioSegment, source: AudioSegment, start_ms: int,
                  end_ms: int, *, gain_db: float, fade_in_ms: int = 0,
                  fade_out_ms: int = 0) -> AudioSegment:
    span = max(0, end_ms - start_ms)
    if span == 0:
        return track
    bed = audio_engine._loop_to(_conform(source), span) + gain_db
    if fade_in_ms:
        bed = bed.fade_in(min(span, fade_in_ms))
    if fade_out_ms:
        bed = bed.fade_out(min(span, fade_out_ms))
    return track.overlay(bed, position=start_ms)


def _write_project() -> None:
    idea = (
        "A couple in their apartment confronts the end of their relationship over "
        "one packed blue mug. No narrator: only an intimate, escalating argument."
    )
    store.save_idea(SERIES_ID, idea)
    store.save_blueprint(SERIES_ID, {
        "logline": "A packed mug turns a breakup into the confession neither partner can escape.",
        "story_world": "A nearly empty small apartment late at night.",
        "main_storyline": (
            "Maya realizes Daniel is leaving for good. Their controlled exchange "
            "escalates into crosstalk, a shouted interruption, and a devastating quiet truth."
        ),
        "theme": "The violence of not being heard by the person who knows you best.",
        "tone": "Intimate, raw, restrained, emotionally volatile.",
        "story_beats": [
            "The blue mug reveals Daniel's departure is final.",
            "Old accusations collide in overlapping speech.",
            "Daniel shouts across Maya and cuts her sentence short.",
            "After absolute silence, both admit the relationship has already caused harm.",
        ],
        "characters": [
            {
                "name": "Maya", "role": "Lead", "gender": "Woman",
                "description": "Trying to remain composed while grief turns into anger.",
                "personality": "Direct, wounded, emotionally honest.",
                "vocal_direction": "Soft adult voice; tears held back, then openly pleading.",
                "voice_id": "Achernar", "is_narrator": False,
            },
            {
                "name": "Daniel", "role": "Lead", "gender": "Man",
                "description": "Defensive and exhausted; anger breaks into remorse.",
                "personality": "Guarded, avoidant, capable of sudden intensity.",
                "vocal_direction": "Low adult voice; contained until one uncontrolled shout.",
                "voice_id": "Algenib", "is_narrator": False,
            },
        ],
    }, meta={
        "genre": "Relationship Drama", "setting": "Small apartment, late night",
        "language": "English", "theme": "Being unheard", "tone": "Raw and intimate",
    })
    store.save_voice_cast(SERIES_ID, {"Maya": "Achernar", "Daniel": "Algenib"})
    store.save_episode_outline(SERIES_ID, {
        "number": EPISODE_NUMBER,
        "title": "The Blue Mug",
        "summary": (
            "While Daniel packs to leave, Maya notices he has taken the mug her mother "
            "gave them. The small object detonates months of silence between them."
        ),
        "main_events": [
            "Maya notices the packed mug.",
            "Their explanations collapse into overlapping accusations.",
            "Daniel's shout cuts Maya off and kills the score.",
            "A long silence exposes what anger was hiding.",
        ],
        "emotional_arc": "disbelief → grief → crosstalk → rupture → remorse",
        "cliffhanger": "Maya quietly confirms that Daniel has already hurt her.",
    })
    store.save_episode_script(SERIES_ID, EPISODE_NUMBER, SCRIPT)
    store.save_episode_evaluation(SERIES_ID, EPISODE_NUMBER, {
        "points": [
            {
                "category": "Escalation",
                "assessment": "The argument tightens from an ordinary object into mutual blame.",
                "suggestion": "Protect the early restraint so the single shout remains shocking.",
            },
            {
                "category": "Audio staging",
                "assessment": "Crosstalk is limited to moments where both characters stop listening.",
                "suggestion": "Keep the post-shout silence completely free of score and effects.",
            },
            {
                "category": "Character voices",
                "assessment": "Maya pursues connection while Daniel retreats, then erupts.",
                "suggestion": "Let the final two lines fall below the energy of the argument.",
            },
        ],
        "stale": False,
    })
    store.save_index(
        SERIES_ID, title="The Blue Mug", genre="Relationship Drama",
        include_narrator=False, ep_count=1, ep_minutes=1, stage="scripted",
    )


def _usable_manifest(info: dict[str, Any]) -> bool:
    line_files = list(info.get("line_files") or [])
    return (
        len(line_files) == len(SCRIPT)
        and all(Path(path).is_file() for path in line_files)
        and all(int(value) > 0 for value in (info.get("line_durations_ms") or []))
    )


def _render_voices(force: bool) -> tuple[dict[str, Any], bool]:
    existing = store.load_episode(SERIES_ID, EPISODE_NUMBER)["audio"]
    if not force and _usable_manifest(existing):
        print("VOICE_STAGE=reused immutable line WAVs")
        return existing, False

    state = store.hydrate(SERIES_ID)

    def progress(done: int, total: int) -> None:
        print(f"VOICE_PROGRESS={done}/{total}", flush=True)

    manifest = audio_nodes.render_episode_audio(
        state, EPISODE_NUMBER, progress=progress,
    )
    print("VOICE_STAGE=generated each dialogue line once")
    return manifest, True


def _editor_plan(source_durations: list[int]) -> list[dict[str, Any]]:
    # Remove approximately the audible “-ish for once” tail, leaving Maya's
    # final word visibly/audibly unfinished. It is derived from the real take so
    # the same plan works if TTS pacing changes slightly.
    maya_cut_tail = max(600, min(1_100, round(source_durations[6] * 0.11)))
    return [
        {"line": 0, "pause_before_ms": 750, "pause_after_ms": 420,
         "rate": 0.94, "gain_db": -2.0, "fade_in_ms": 10},
        {"line": 1, "pause_after_ms": 300, "rate": 0.98, "gain_db": -1.0},
        {"line": 2, "pause_after_ms": 0, "rate": 0.92, "gain_db": 0.0},
        {"line": 3, "overlap_previous_ms": 430, "pause_after_ms": 0,
         "rate": 1.02, "gain_db": 0.8},
        {"line": 4, "overlap_previous_ms": 220, "pause_after_ms": 0,
         "rate": 0.98, "gain_db": 0.4},
        {"line": 5, "overlap_previous_ms": 500, "pause_after_ms": 420,
         "rate": 1.06, "gain_db": 1.5},
        {"line": 6, "pause_before_ms": 0, "pause_after_ms": 0,
         "rate": 0.92, "gain_db": 0.5, "trim_tail_ms": maya_cut_tail,
         "fade_out_ms": 8},
        {"line": 7, "overlap_previous_ms": 180, "interrupt": True,
         "pause_after_ms": 2_100, "rate": 1.03, "gain_db": 3.0,
         "fade_in_ms": 5},
        {"line": 8, "pause_before_ms": 0, "pause_after_ms": 850,
         "rate": 0.90, "gain_db": -3.0},
        {"line": 9, "pause_before_ms": 0, "pause_after_ms": 1_200,
         "rate": 0.90, "gain_db": -3.5, "fade_out_ms": 25},
    ]


def _mix(manifest: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    source_segments = manifest["segments"]
    items = [
        {
            "line_index": int(segment["line_index"]),
            "line_id": segment["line_id"],
            "speaker": segment["speaker"],
            "path": path,
        }
        for segment, path in zip(source_segments, manifest["line_files"])
    ]
    edits = _editor_plan([int(value) for value in manifest["line_durations_ms"]])
    dialogue, segments, offsets = audio_engine.assemble_dialogue(
        items, edits, default_pause_ms=0,
    )
    dialogue = _conform(dialogue)
    duration_ms = len(dialogue)
    episode_dir = store.episode_dir(SERIES_ID, EPISODE_NUMBER)

    # The score begins almost imperceptibly, grows as turn-taking breaks down,
    # ducks beneath every voice, then ends 25 ms before/at Daniel's shout.
    shout_start = int(segments[7]["start_ms"])
    score_start = max(0, int(segments[0]["start_ms"]) - 100)
    score_span = max(0, shout_start - score_start)
    score = audio_engine._loop_to(_conform(audio_engine.load(MUSIC_PATH)), score_span)
    if score_span:
        score = score + -12.0
        score = score.fade(
            from_gain=-8.0, to_gain=0.0, start=0,
            end=max(1, score_span - 250),
        ).fade_in(min(1_400, score_span)).fade_out(min(25, score_span))
        local_regions = audio_engine._dialogue_regions(
            segments, score_start, score_span, hold_ms=120,
        )
        score = audio_engine._apply_duck_envelope(
            score, local_regions, duck_db=-10.0,
            attack_ms=55, release_ms=240,
        )
    music_stem = _blank(duration_ms).overlay(score, position=score_start)

    # Room tone disappears after the shout, leaving genuine digital silence;
    # it returns very faintly only when Daniel finally speaks again.
    room_source = audio_engine.load(ROOM_TONE_PATH)
    ambience_stem = _blank(duration_ms)
    ambience_stem = _overlay_span(
        ambience_stem, room_source, 0, int(segments[7]["end_ms"]),
        gain_db=10.0, fade_in_ms=350, fade_out_ms=25,
    )
    ambience_stem = _overlay_span(
        ambience_stem, room_source, int(segments[8]["start_ms"]), duration_ms,
        gain_db=8.0, fade_in_ms=180, fade_out_ms=450,
    )

    # One motivated object sound and one tiny post-crying breath detail. The
    # vocal performance—not a canned crying loop—carries Maya's grief.
    sfx_stem = _blank(duration_ms)
    cup_at = max(0, int(segments[0]["start_ms"]) - 380)
    cup = _conform(audio_engine.load(CUP_PATH))[:700].fade_out(120) - 10.0
    sfx_stem = sfx_stem.overlay(cup, position=cup_at)
    sniff_at = max(int(segments[5]["end_ms"]) + 40,
                   int(segments[6]["start_ms"]) - 300)
    sniff_source = audio_engine.trim_edge_silence(audio_engine.load(SNIFF_PATH), {
        "silence_threshold_dbfs": -48, "max_trim_ms": 2_000,
        "keep_ms": 20, "chunk_ms": 5,
    })
    sniff = _conform(sniff_source)[:1_400].fade_in(15).fade_out(90) - 3.0
    sfx_stem = sfx_stem.overlay(sniff, position=sniff_at)

    dialogue_path = episode_dir / "ep01_dialogue_edit.wav"
    music_path = episode_dir / "ep01_music_stem.wav"
    ambience_path = episode_dir / "ep01_ambience_stem.wav"
    sfx_path = episode_dir / "ep01_sfx_stem.wav"
    final_path = episode_dir / "ep01_final.wav"
    audio_engine.export(dialogue, dialogue_path)
    audio_engine.export(music_stem, music_path)
    audio_engine.export(ambience_stem, ambience_path)
    audio_engine.export(sfx_stem, sfx_path)

    final = audio_engine.mix_and_master([
        {"audio": dialogue},
        {"audio": music_stem},
        {"audio": ambience_stem},
        {"audio": sfx_stem},
    ], {
        "duration_ms": duration_ms,
        "headroom_db": 3.0,
        "target_dbfs": -17.5,
        "peak_ceiling_dbfs": -1.0,
    })
    audio_engine.export(final, final_path)

    silence_start = int(segments[7]["end_ms"])
    silence_end = int(segments[8]["start_ms"])
    silence_probe = final[min(silence_end, silence_start + 100):max(
        silence_start + 100, silence_end - 100,
    )]
    metrics = {
        "duration_ms": duration_ms,
        "source_dialogue_calls": len(SCRIPT),
        "maya_cut_at_ms": int(segments[6]["end_ms"]),
        "shout_start_ms": shout_start,
        "shout_overlap_ms": int(segments[7]["overlap_previous_ms"]),
        "score_hard_stop_ms": shout_start,
        "absolute_silence_start_ms": silence_start,
        "absolute_silence_end_ms": silence_end,
        "absolute_silence_ms": max(0, silence_end - silence_start),
        "absolute_silence_dbfs": (
            None if not silence_probe or silence_probe.dBFS == float("-inf")
            else round(silence_probe.dBFS, 2)
        ),
        "final_dbfs": round(final.dBFS, 2),
        "final_peak_dbfs": round(final.max_dBFS, 2),
    }
    plan = {
        "dialogue": edits,
        "music": [{
            "title": assets.manifest()["music"]["emotional"]["title"],
            "mood": "emotional",
            "start_ms": score_start, "end_ms": shout_start,
            "gain_db": -12.0, "duck_db": -10.0,
            "fade_in_ms": 1_400, "fade_out_ms": 25,
            "hard_stop_reason": "Daniel's shouted interruption",
        }],
        "sfx": [
            {"name": "tea_cup_clank", "at_ms": cup_at, "gain_db": -10.0},
            {"name": "post_crying_sniff", "at_ms": sniff_at, "gain_db": -3.0},
        ],
        "ambience": [
            {"name": "room_tone", "start_ms": 0,
             "end_ms": int(segments[7]["end_ms"]), "gain_db": 10.0},
            {"name": "room_tone", "start_ms": int(segments[8]["start_ms"]),
             "end_ms": duration_ms, "gain_db": 8.0},
        ],
        "editor_notes": [
            "No narrator and no generated sound cues inside the dialogue text.",
            "Lines 4–6 use controlled crosstalk; line 8 is the single dominant interruption.",
            "Maya's line 7 is physically trimmed and anti-click faded, not regenerated.",
            "The score stops at the shout; all sound stops after it for a 2.1-second void.",
            "No canned sob loop, riser, boom, thunder, heartbeat, or door slam.",
        ],
        "metrics": metrics,
    }
    store.save_episode_sound_plan(SERIES_ID, EPISODE_NUMBER, plan)

    updated = dict(manifest)
    updated.update({
        "offsets": offsets,
        "segments": segments,
        "total_ms": duration_ms,
        "edited_line_durations_ms": [int(row["duration_ms"]) for row in segments],
        "dialogue_edit": str(dialogue_path),
        "music_stem": str(music_path),
        "ambience_stem": str(ambience_path),
        "sfx_stem": str(sfx_path),
        "final": str(final_path),
        "final_sha256": _sha256(final_path),
        "stale": False,
        "cinematic_editor": metrics,
    })
    store.save_episode_audio(SERIES_ID, EPISODE_NUMBER, updated)
    store.save_index(SERIES_ID, stage="episode_ready")
    return updated, plan


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--force-voices", action="store_true",
        help="regenerate TTS instead of reusing the immutable line WAVs",
    )
    args = parser.parse_args()
    missing = [path for path in (MUSIC_PATH, ROOM_TONE_PATH, SNIFF_PATH, CUP_PATH)
               if path is None or not path.is_file()]
    if missing:
        raise FileNotFoundError("Missing licensed assets: " + ", ".join(map(str, missing)))

    _write_project()
    manifest, generated = _render_voices(args.force_voices)
    updated, plan = _mix(manifest)
    result = {
        "series_id": SERIES_ID,
        "episode": EPISODE_NUMBER,
        "voices_generated_now": generated,
        "line_count": len(SCRIPT),
        "final": updated["final"],
        "sound_plan": str(
            store.episode_dir(SERIES_ID, EPISODE_NUMBER) / "sound_plan.json"
        ),
        "metrics": plan["metrics"],
    }
    print("RESULT=" + json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
