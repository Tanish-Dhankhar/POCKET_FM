"""Focused coverage for the post-TTS cinematic edit-plan integration."""
from __future__ import annotations

from pathlib import Path

import pytest

from app import assets, config, schemas
from app.nodes import audio as audio_nodes
from conftest import write_tone_wav


def test_sound_plan_keeps_legacy_fields_and_accepts_overlap_alias():
    legacy = schemas.SoundPlan(
        music=[schemas.MusicCue(start_line=0, end_line=0, mood="tense")],
        sfx=[schemas.SfxCue(line=0, name="door_creak")],
    )
    assert legacy.dialogue == [] and legacy.ambience == []

    edit = schemas.DialogueEdit(line=1, overlap_ms=180, interrupt=True)
    assert edit.overlap_previous_ms == 180


def test_enforce_clamps_cinematic_controls_and_keeps_sparse_guards():
    plan = schemas.SoundPlan(
        dialogue=[
            schemas.DialogueEdit(
                line=1, pause_before_ms=-10, pause_after_ms=99_999,
                rate=9, gain_db=99, overlap_ms=99_999, interrupt=True,
            ),
            schemas.DialogueEdit(line=99),
        ],
        music=[schemas.MusicCue(
            start_line=0, end_line=0, mood=assets.music_moods()[0],
            gain_db=99, duck_db=-99, duck_attack_ms=99_999,
            duck_release_ms=99_999,
        )],
        sfx=[schemas.SfxCue(
            line=2, name=assets.sfx_keys()[0], offset_ms=99_999,
            gain_db=99, pan=9,
        )],
        ambience=[schemas.AmbienceCue(
            start_line=1, end_line=2, name=assets.sfx_keys()[0],
            gain_db=9, fade_in_ms=99_999,
        )],
    )

    kept = audio_nodes._enforce(
        plan, [0, 1_000, 3_000], 10_000,
        line_durations_ms=[700, 700, 700], line_indices=[0, 1, 2],
    )

    edit = kept["dialogue"][0]
    assert edit == {
        "line": 1, "pause_before_ms": 0, "pause_after_ms": 2_500,
        "rate": 1.1, "gain_db": 4.0, "overlap_previous_ms": 600,
        "interrupt": True,
    }
    assert kept["music"][0]["gain_db"] == -3.0
    assert kept["music"][0]["duck_db"] == -24.0
    assert kept["music"][0]["duck_attack_ms"] == 500
    assert kept["music"][0]["duck_release_ms"] == 2_000
    assert kept["sfx"][0]["at_ms"] == 8_000
    assert kept["sfx"][0]["gain_db"] == 6.0
    assert kept["sfx"][0]["pan"] == 1.0
    assert kept["ambience"][0]["gain_db"] == -12.0


def _render_two_lines(tmp_path: Path, monkeypatch):
    calls: list[str] = []

    def fake_render(text, voice, out, cache_dir=None):
        calls.append(text)
        return write_tone_wav(Path(out), 420 if text == "first" else 730)

    monkeypatch.setattr(config, "OUTPUT_DIR", tmp_path / "output")
    monkeypatch.setattr(audio_nodes, "render_line", fake_render)
    monkeypatch.setattr(audio_nodes.config, "TTS_PARALLEL_WORKERS", 1)
    state = {
        "series_id": "cinematic",
        "voice_cast": {"A": "Kore", "B": "Leda"},
        "scripts": {"1": [
            {"id": "line-a", "speaker": "A", "text": "first"},
            {"id": "line-b", "speaker": "B", "text": "second"},
        ]},
    }
    return state, audio_nodes.render_episode_audio(state, 1), calls


def test_manifest_records_source_line_durations(tmp_path, monkeypatch):
    _, manifest, calls = _render_two_lines(tmp_path, monkeypatch)

    assert calls == ["first", "second"]
    assert manifest["line_durations_ms"] == pytest.approx([420, 730], abs=3)
    assert [segment["duration_ms"] for segment in manifest["segments"]] \
        == pytest.approx([420, 730], abs=3)
    assert manifest["segments"][0]["end_ms"] == pytest.approx(420, abs=3)


def test_mix_reuses_immutable_takes_and_realises_voiced_overlap(tmp_path, monkeypatch):
    state, manifest, _ = _render_two_lines(tmp_path, monkeypatch)
    before = [Path(path).read_bytes() for path in manifest["line_files"]]
    monkeypatch.setattr(
        audio_nodes, "render_line",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("TTS called during mix")),
    )
    state["audio_manifest"] = {"1": manifest}
    state["sound_plans"] = {"1": schemas.SoundPlan(dialogue=[
        schemas.DialogueEdit(line=0, pause_after_ms=350),
        schemas.DialogueEdit(
            line=1, pause_before_ms=500, pause_after_ms=0,
            overlap_previous_ms=200, interrupt=True,
        ),
    ]).model_dump()}

    mixed = audio_nodes.mix_episode(state, 1)

    first, second = mixed["segments"]
    assert second["start_ms"] == first["end_ms"] - 200
    assert second["overlap_previous_ms"] == 200
    assert Path(mixed["final"]).exists()
    assert [Path(path).read_bytes() for path in manifest["line_files"]] == before
    assert mixed["line_durations_ms"] == manifest["line_durations_ms"]
