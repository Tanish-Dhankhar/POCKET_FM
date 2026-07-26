"""Audio engine + sound-design enforcement tests.

These use real WAVs through pydub, so they verify actual sample data, not mocks.
"""
from __future__ import annotations

from pathlib import Path
import time

import pytest
from pydub import AudioSegment

from app import assets, audio_engine, config, schemas
from app.nodes import audio as audio_nodes
from app.nodes.audio import _enforce, _voice_for

from conftest import write_tone_wav


# --------------------------------------------------------------------------- #
# audio_engine
# --------------------------------------------------------------------------- #
def test_concat_lines_offsets_match_real_timeline(tmp_path):
    paths = [write_tone_wav(tmp_path / f"{i}.wav", ms) for i, ms in enumerate((500, 800, 300))]
    track, offsets = audio_engine.concat_lines([str(p) for p in paths])

    assert offsets[0] == 0
    # Each offset is the previous line's length plus one inter-line pause.
    assert offsets[1] == pytest.approx(500 + config.PAUSE_BETWEEN_LINES_MS, abs=5)
    assert offsets[2] == pytest.approx(500 + 800 + 2 * config.PAUSE_BETWEEN_LINES_MS, abs=5)
    # No trailing pause after the final line.
    expected = 500 + 800 + 300 + 2 * config.PAUSE_BETWEEN_LINES_MS
    assert len(track) == pytest.approx(expected, abs=10)


def test_concat_lines_handles_a_single_line(tmp_path):
    p = write_tone_wav(tmp_path / "only.wav", 400)
    track, offsets = audio_engine.concat_lines([str(p)])
    assert offsets == [0]
    assert len(track) == pytest.approx(400, abs=5), "no pause should be appended"


def test_place_music_ducks_under_voice_and_preserves_length(tmp_path):
    base = AudioSegment.silent(duration=4000, frame_rate=config.TTS_SAMPLE_RATE)
    bed = assets.music_path("tense")
    mixed = audio_engine.place_music(base, bed, 500, 3000)

    assert len(mixed) == len(base), "overlay must not extend the timeline"
    # The music-covered window has signal; the uncovered tail stays silent.
    assert mixed[1000:2000].dBFS > -60
    assert mixed[3200:3900].dBFS < -60
    # And it is genuinely quieter than the raw bed.
    raw = AudioSegment.from_file(str(bed))
    assert mixed[1000:2000].dBFS < raw[0:1000].dBFS


def test_place_music_loops_a_short_bed_over_a_long_span(tmp_path):
    short = write_tone_wav(tmp_path / "short.wav", 500)
    base = AudioSegment.silent(duration=6000, frame_rate=config.TTS_SAMPLE_RATE)
    mixed = audio_engine.place_music(base, short, 0, 6000)
    assert len(mixed) == 6000
    assert mixed[4500:5500].dBFS > -60, "bed should still be playing after looping"


def test_place_music_with_empty_span_is_a_noop():
    base = AudioSegment.silent(duration=1000, frame_rate=config.TTS_SAMPLE_RATE)
    assert audio_engine.place_music(base, assets.music_path("tense"), 500, 500) is base


def test_place_sfx_overlays_at_position_without_extending(tmp_path):
    base = AudioSegment.silent(duration=5000, frame_rate=config.TTS_SAMPLE_RATE)
    mixed = audio_engine.place_sfx(base, assets.sfx_path("door_creak"), 1000)
    assert len(mixed) == len(base)
    assert mixed[1100:1400].dBFS > -60
    assert mixed[100:400].dBFS < -60


def test_export_creates_parent_dirs_and_readable_wav(tmp_path):
    seg = AudioSegment.silent(duration=250, frame_rate=config.TTS_SAMPLE_RATE)
    out = audio_engine.export(seg, tmp_path / "deep" / "nested" / "o.wav")
    assert out.exists()
    assert len(audio_engine.load(out)) == pytest.approx(250, abs=5)


# --------------------------------------------------------------------------- #
# restraint enforcement (_enforce)
# --------------------------------------------------------------------------- #
def _offsets(n: int, step: int = 2000) -> list[int]:
    return [i * step for i in range(n)]


def test_enforce_drops_sfx_with_unknown_key():
    plan = schemas.SoundPlan(sfx=[schemas.SfxCue(line=0, name="not_a_real_sfx")])
    assert _enforce(plan, _offsets(5), 10_000)["sfx"] == []


def test_enforce_drops_sfx_with_out_of_range_line():
    plan = schemas.SoundPlan(sfx=[schemas.SfxCue(line=99, name=assets.sfx_keys()[0])])
    assert _enforce(plan, _offsets(5), 10_000)["sfx"] == []


def test_enforce_spaces_out_clustered_sfx():
    key = assets.sfx_keys()[0]
    # Lines 1s apart; the guardrail demands >= MIN_SECONDS_BETWEEN_SFX.
    offsets = _offsets(6, step=1000)
    plan = schemas.SoundPlan(sfx=[schemas.SfxCue(line=i, name=key) for i in range(6)])
    kept = _enforce(plan, offsets, 6000)["sfx"]

    assert len(kept) < 6, "clustered SFX must be thinned"
    times = [c["at_ms"] for c in kept]
    for a, b in zip(times, times[1:]):
        assert (b - a) / 1000 >= config.MIN_SECONDS_BETWEEN_SFX


def test_enforce_caps_total_music_coverage():
    mood = assets.music_moods()[0]
    total = 100_000
    offsets = _offsets(50, step=2000)
    # Ask for the entire episode to be covered.
    plan = schemas.SoundPlan(music=[schemas.MusicCue(start_line=0, end_line=49, mood=mood)])
    kept = _enforce(plan, offsets, total)["music"]

    covered = sum(c["end_ms"] - c["start_ms"] for c in kept)
    assert covered <= config.MAX_MUSIC_COVERAGE * total


def test_enforce_drops_music_with_unknown_mood():
    plan = schemas.SoundPlan(music=[schemas.MusicCue(start_line=0, end_line=2, mood="disco")])
    assert _enforce(plan, _offsets(5), 10_000)["music"] == []


def test_enforce_drops_inverted_music_range():
    mood = assets.music_moods()[0]
    plan = schemas.SoundPlan(music=[schemas.MusicCue(start_line=4, end_line=1, mood=mood)])
    assert _enforce(plan, _offsets(5), 10_000)["music"] == []


def test_enforce_clamps_music_end_line_into_range():
    mood = assets.music_moods()[0]
    # A late, short cue so the coverage cap doesn't independently reject it.
    offsets = _offsets(20, step=2000)
    plan = schemas.MusicCue(start_line=17, end_line=999, mood=mood)
    kept = _enforce(schemas.SoundPlan(music=[plan]), offsets, 40_000)["music"]
    assert kept and kept[0]["end_line"] == 19, "end_line must clamp to the last line"


def test_enforce_rejects_a_bed_covering_the_whole_episode():
    """The coverage cap is what stops wall-to-wall music."""
    mood = assets.music_moods()[0]
    plan = schemas.SoundPlan(music=[schemas.MusicCue(start_line=0, end_line=4, mood=mood)])
    assert _enforce(plan, _offsets(5), 10_000)["music"] == []


def test_enforce_produces_non_overlapping_music_cues():
    mood = assets.music_moods()[0]
    offsets = _offsets(40, step=3000)
    plan = schemas.SoundPlan(music=[
        schemas.MusicCue(start_line=i, end_line=i + 3, mood=mood) for i in range(0, 36, 2)
    ])
    kept = _enforce(plan, offsets, 120_000)["music"]
    for a, b in zip(kept, kept[1:]):
        assert b["start_ms"] >= a["end_ms"], "music beds must not overlap"


def test_enforce_keeps_a_reasonable_sparse_plan_intact():
    """A well-behaved plan should survive enforcement unchanged."""
    mood, key = assets.music_moods()[0], assets.sfx_keys()[0]
    offsets = _offsets(30, step=4000)
    plan = schemas.SoundPlan(
        music=[schemas.MusicCue(start_line=0, end_line=4, mood=mood)],
        sfx=[schemas.SfxCue(line=10, name=key), schemas.SfxCue(line=20, name=key)],
    )
    kept = _enforce(plan, offsets, 120_000)
    assert len(kept["music"]) == 1
    assert len(kept["sfx"]) == 2


# --------------------------------------------------------------------------- #
# voice resolution
# --------------------------------------------------------------------------- #
def test_voice_for_prefers_the_explicit_cast():
    state = {"voice_cast": {"Maya": "Leda"}}
    assert _voice_for(state, "Maya") == "Leda"


def test_voice_for_narrator_falls_back_to_default():
    from app.nodes.audio import _DEFAULT_NARRATOR_VOICE
    assert _voice_for({"voice_cast": {}}, "Narrator") == _DEFAULT_NARRATOR_VOICE


def test_voice_for_uncast_character_is_stable_and_valid():
    """An uncast character must get the SAME valid voice on every lookup.

    This is what keeps a character sounding like themselves across episodes and
    across server restarts — it must not depend on process-level hash seeding.
    """
    state = {"voice_cast": {}}
    voice = _voice_for(state, "Unnamed Guard")
    assert voice in config.VOICE_NAMES
    assert all(_voice_for(state, "Unnamed Guard") == voice for _ in range(5))


def test_voice_for_uncast_character_is_stable_across_processes():
    import subprocess, sys, json as _json
    root = Path(__file__).resolve().parent.parent
    code = ("import json;from app.nodes.audio import _voice_for;"
            "print(json.dumps([_voice_for({'voice_cast':{}},n) "
            "for n in ['Ravi','Meera','Guard']]))")
    runs = set()
    for _ in range(3):
        out = subprocess.run([sys.executable, "-c", code], cwd=root,
                             capture_output=True, text=True, check=True)
        runs.add(out.stdout.strip())
    assert len(runs) == 1, f"voice fallback is not deterministic across runs: {runs}"


def test_parallel_render_preserves_script_order(tmp_path, monkeypatch):
    completed = []

    def fake_render(text, voice, out, cache_dir=None):
        # Finish in reverse order to prove concatenation is not completion-ordered.
        time.sleep({"first": 0.06, "second": 0.03, "third": 0.0}[text])
        out = Path(out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"wav")
        completed.append(text)
        return out

    captured = []

    class Track:
        def __len__(self):
            return 300

    def fake_concat(paths):
        captured.extend(Path(path).name for path in paths)
        return Track(), [0, 100, 200]

    monkeypatch.setattr(audio_nodes, "render_line", fake_render)
    monkeypatch.setattr(audio_nodes.audio_engine, "concat_lines", fake_concat)
    monkeypatch.setattr(audio_nodes.audio_engine, "export", lambda track, path: None)
    monkeypatch.setattr(audio_nodes.store, "series_dir", lambda sid: tmp_path)
    monkeypatch.setattr(audio_nodes.store, "lines_dir", lambda sid, n: tmp_path / "lines")
    monkeypatch.setattr(audio_nodes.store, "episode_dir", lambda sid, n: tmp_path / "episode")
    monkeypatch.setattr(audio_nodes.store, "save_episode_audio", lambda *args: None)
    monkeypatch.setattr(audio_nodes.config, "TTS_PARALLEL_WORKERS", 3)

    state = {
        "series_id": "parallel",
        "voice_cast": {},
        "scripts": {"1": [
            {"speaker": "A", "text": "first"},
            {"speaker": "B", "text": "second"},
            {"speaker": "C", "text": "third"},
        ]},
    }
    audio_nodes.render_episode_audio(state, 1)

    assert completed != ["first", "second", "third"]
    assert [name[:4] for name in captured] == ["0000", "0001", "0002"]
