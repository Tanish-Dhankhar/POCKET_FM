"""Unit tests for config, assets, schemas and prompt builders."""
from __future__ import annotations

import json

import pytest

from app import assets, config, prompts, schemas


# --------------------------------------------------------------------------- #
# config
# --------------------------------------------------------------------------- #
def test_api_key_is_configured():
    assert config.OPENAI_API_KEY, "OPENAI_API_KEY missing from .env"
    assert config.GEMINI_API_KEY, "GEMINI_API_KEY missing from .env"


def test_voice_catalogue_is_consistent():
    assert config.VOICE_NAMES == list(config.VOICES)
    assert len(config.VOICE_NAMES) == len(set(config.VOICE_NAMES)), "duplicate voice id"
    assert len(config.VOICE_NAMES) >= 20


def test_audio_tunables_are_sane():
    assert config.TTS_SAMPLE_RATE == 24_000     # Gemini TTS contract
    assert config.MUSIC_DUCK_DB < 0, "music bed must sit under the voice"
    assert config.SFX_GAIN_DB < 0
    assert 0 < config.MAX_MUSIC_COVERAGE <= 1
    assert config.EP_MINUTES_MIN < config.EP_MINUTES_MAX


# --------------------------------------------------------------------------- #
# assets
# --------------------------------------------------------------------------- #
def test_sound_manifest_exists_and_parses():
    assert config.SOUND_MANIFEST.exists(), "run: python -m tools.build_assets"
    data = json.loads(config.SOUND_MANIFEST.read_text())
    assert data["music"] and data["sfx"]


def test_sound_manifest_uses_only_documented_v2_assets():
    data = json.loads(config.SOUND_MANIFEST.read_text(encoding="utf-8"))
    assert data["library_version"] >= 2
    for kind in ("music", "sfx"):
        for entry in data[kind].values():
            assert entry["file"].startswith("library/v2/")
            assert entry.get("license") and "placeholder" not in entry["license"].lower()
            assert entry.get("license_url")
            assert entry.get("source")
            assert entry.get("download_url")


@pytest.mark.parametrize("mood", assets.music_moods())
def test_every_music_file_exists(mood):
    path = assets.music_path(mood)
    assert path is not None and path.exists(), f"missing music bed: {mood}"
    assert path.stat().st_size > 1000


@pytest.mark.parametrize("key", assets.sfx_keys())
def test_every_sfx_file_exists(key):
    path = assets.sfx_path(key)
    assert path is not None and path.exists(), f"missing sfx: {key}"
    assert path.stat().st_size > 500


def test_unknown_asset_lookups_return_none():
    assert assets.music_path("no_such_mood") is None
    assert assets.sfx_path("no_such_sfx") is None


# --------------------------------------------------------------------------- #
# schemas
# --------------------------------------------------------------------------- #
def test_script_line_rejects_unknown_type():
    with pytest.raises(Exception):
        schemas.ScriptLine(type="song", speaker="Maya", text="hi")


def test_script_line_defaults_are_sparse():
    ln = schemas.ScriptLine(type="dialogue", speaker="Maya", text="hi")
    assert ln.sfx == [] and ln.music is None, "sound must default to silence"


def test_sound_plan_defaults_to_empty():
    plan = schemas.SoundPlan()
    assert plan.music == [] and plan.sfx == []


def test_clarify_result_requires_exactly_four_questions():
    with pytest.raises(ValueError):
        schemas.ClarifyResult(questions=[])


# --------------------------------------------------------------------------- #
# prompts
# --------------------------------------------------------------------------- #
def test_feedback_is_injected_only_when_present():
    assert "REGENERATE" not in prompts.extract("an idea")
    assert "REGENERATE" in prompts.extract("an idea", "make it darker")
    assert "make it darker" in prompts.extract("an idea", "make it darker")


def test_script_prompt_lists_only_allowed_emotion_tags():
    p = prompts.script({"logline": "x"}, {"number": 1, "title": "t"})
    for tag in config.EMOTION_TAGS:
        assert f"[{tag}]" in p
    assert "[pause]" in p


def test_sound_design_prompt_constrains_to_real_assets():
    p = prompts.sound_design(
        [{"type": "narration", "speaker": "Narrator", "text": "It rained."}],
        assets.music_moods(), assets.sfx_keys(),
    )
    for mood in assets.music_moods():
        assert mood in p
    for key in assets.sfx_keys():
        assert key in p
    assert "0: (narration) Narrator: It rained." in p, "lines must be index-numbered"


def test_episode_plan_prompt_states_the_requested_count():
    p = prompts.episode_plan({"logline": "x"}, ep_count=7, ep_minutes=9)
    assert "exactly 7 episodes" in p
    assert "9" in p


def test_voice_cast_prompt_includes_full_catalogue():
    p = prompts.voice_cast([{"name": "Maya"}])
    for name in config.VOICE_NAMES:
        assert name in p


def test_blueprint_prompt_carries_continuation_arcs():
    p = prompts.blueprint("idea", {}, [], arcs=["Maya returns a decade later."])
    assert "CONTINUATION PLOTS" in p
    assert "Maya returns a decade later." in p
