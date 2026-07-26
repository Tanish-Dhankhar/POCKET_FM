"""Focused tests for the fast, deterministic cinematic editor backend."""
from __future__ import annotations

from pydub import AudioSegment
from pydub.generators import Sine

from app import audio_engine


def _tone(ms: int, frequency: int = 440, gain_db: float = -18.0) -> AudioSegment:
    return Sine(frequency).to_audio_segment(duration=ms).apply_gain(gain_db)


def _write(path, segment: AudioSegment):
    segment.export(path, format="wav")
    return path


def test_trim_edge_silence_is_light_and_bounded():
    clip = AudioSegment.silent(150) + _tone(400) + AudioSegment.silent(150)
    trimmed = audio_engine.trim_edge_silence(clip, {
        "silence_threshold_dbfs": -45,
        "max_trim_ms": 100,
        "keep_ms": 10,
        "chunk_ms": 5,
    })

    assert 510 <= len(trimmed) <= 530
    assert trimmed.dBFS > float("-inf")
    silent = AudioSegment.silent(300)
    assert audio_engine.trim_edge_silence(silent) is silent


def test_clip_edits_bound_rate_and_apply_gain_and_fades():
    clip = _tone(1_000, gain_db=-30)
    faster = audio_engine.apply_clip_edits(clip, {"rate": 99})
    assert len(faster) == 909  # rate is capped at 1.10

    louder = audio_engine.apply_clip_edits(clip, {"gain_db": 3})
    assert abs(louder.dBFS - (clip.dBFS + 3)) < 0.02

    faded = audio_engine.apply_clip_edits(clip, {
        "fade_in_ms": 200,
        "fade_out_ms": 200,
    })
    assert faded[:25].dBFS < faded[400:600].dBFS - 8
    assert faded[-25:].dBFS < faded[400:600].dBFS - 8


def test_assemble_dialogue_uses_true_clip_ends_and_overlap(tmp_path):
    paths = [
        _write(tmp_path / f"line-{index}.wav", _tone(500, 300 + index * 100))
        for index in range(3)
    ]
    items = [
        {"line_index": index, "line_id": f"line-{index}", "path": path,
         "speaker": f"speaker-{index}"}
        for index, path in enumerate(paths)
    ]
    edits = [
        {"line": 0, "trim_tail_ms": 100, "pause_after_ms": 250,
         "trim_edge_silence": False},
        {"line": 1, "pause_before_ms": 100, "overlap_previous_ms": 100,
         "interrupt": True,
         "pause_after_ms": 50, "trim_edge_silence": False},
        {"line": 2, "pause_before_ms": 150, "trim_edge_silence": False},
    ]

    track, segments, offsets = audio_engine.assemble_dialogue(items, edits)

    assert offsets == [0, 300, 1_000]
    assert [(row["start_ms"], row["end_ms"]) for row in segments] == [
        (0, 400), (300, 800), (1_000, 1_500),
    ]
    assert segments[1]["interrupt"] is True
    assert segments[1]["overlap_previous_ms"] == 100
    assert len(track) == 1_500


def test_assemble_dialogue_can_preserve_legacy_default_gap(tmp_path):
    paths = [_write(tmp_path / f"{index}.wav", _tone(200)) for index in range(2)]
    items = [
        {"line_index": index, "line_id": str(index), "path": path, "speaker": "A"}
        for index, path in enumerate(paths)
    ]

    track, segments, offsets = audio_engine.assemble_dialogue(
        items, default_pause_ms=350,
    )

    assert offsets == [0, 550]
    assert segments[0]["end_ms"] == 200
    assert len(track) == 750


def test_place_looped_ambience_repeats_only_inside_cue(tmp_path):
    ambience_path = _write(tmp_path / "room.wav", _tone(180, frequency=160))
    base = AudioSegment.silent(1_500)
    mixed = audio_engine.place_looped_ambience(base, {
        "path": ambience_path,
        "start_ms": 200,
        "end_ms": 1_200,
        "gain_db": -12,
        "fade_in_ms": 0,
        "fade_out_ms": 0,
    })

    assert len(mixed) == len(base)
    assert mixed[300:450].dBFS > float("-inf")
    assert mixed[1_250:1_400].dBFS == float("-inf")


def test_place_music_ducked_lowers_dialogue_region(tmp_path):
    music_path = _write(tmp_path / "music.wav", _tone(250, frequency=220, gain_db=-6))
    base = AudioSegment.silent(2_000)
    mixed = audio_engine.place_music_ducked(base, {
        "path": music_path,
        "start_ms": 0,
        "end_ms": 2_000,
        "gain_db": -12,
        "duck_db": -12,
        "attack_ms": 0,
        "hold_ms": 0,
        "release_ms": 0,
        "fade_ms": 0,
    }, [{"start_ms": 700, "end_ms": 1_200}])

    normal = mixed[300:600].dBFS
    ducked = mixed[800:1_100].dBFS
    assert normal > ducked + 10
    assert len(mixed) == len(base)


def test_mix_and_master_preserves_tails_and_respects_targets():
    first = _tone(1_000, frequency=300, gain_db=-8)
    second = _tone(500, frequency=500, gain_db=-8)
    mastered = audio_engine.mix_and_master([
        {"audio": first, "position_ms": 0},
        {"audio": second, "position_ms": 800, "gain_db": 2},
    ], {
        "headroom_db": 6,
        "target_dbfs": -18,
        "peak_ceiling_dbfs": -1,
    })

    assert len(mastered) == 1_300
    assert -18.1 <= mastered.dBFS <= -17.9
    assert mastered.max_dBFS <= -1.0
