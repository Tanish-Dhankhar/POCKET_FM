"""Artwork generation: the disabled-by-default guard, selection rule, and paths.

Nothing here touches the network. The most important test in this file is the
first one: with images disabled (the shipped default) no provider call is made
and no file is written.
"""
from __future__ import annotations

import base64
from types import SimpleNamespace

import pytest

from app import config, image_service, images, prompts, store


@pytest.fixture
def blueprint_series(tmp_output):
    """A series on disk with a blueprint and a mixed cast."""
    sid = "img-test"
    store.save_index(sid, title="Room 4B", genre="Supernatural Thriller")
    store.save_blueprint(
        sid,
        {
            "logline": "Three nights, one room, one impossible patient.",
            "story_world": "A decaying county hospital scheduled for demolition.",
            "main_storyline": "Maya uncovers what the hospital buried in 4B.",
            "tone": "tense, intimate",
            "theme": "grief and denial",
            "characters": [
                {"name": "Maya", "role": "protagonist", "description": "Night nurse.",
                 "personality": "stubborn, warm", "vocal_signature": "low",
                 "physical_persona": "Late twenties, tired eyes, dark braid, scrubs."},
                {"name": "Benji", "role": "skeptic", "description": "Security guard.",
                 "personality": "wry", "vocal_signature": "gravelly",
                 "physical_persona": "Fifties, heavyset, greying stubble, uniform."},
                {"name": "Narrator", "role": "narrator", "description": "The voice.",
                 "personality": "measured", "vocal_signature": "even",
                 "physical_persona": "A calm presence outside the story.",
                 "is_narrator": True},
            ],
        },
        meta={"genre": "Supernatural Thriller", "setting": "A county hospital at night"},
    )
    return sid


# --------------------------------------------------------------------------- #
# the disabled-by-default guarantee
# --------------------------------------------------------------------------- #
def test_images_are_disabled_by_default():
    assert config.IMAGE_ENABLED is False


def test_generate_image_is_a_noop_when_disabled(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "IMAGE_ENABLED", False)

    def explode():
        raise AssertionError("the provider must not be contacted when disabled")

    monkeypatch.setattr(images, "client", explode)

    path = tmp_path / "thumbnail.png"
    assert images.generate_image("any prompt", path) is None
    assert not path.exists()


def test_identical_image_prompt_uses_disk_cache(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "IMAGE_ENABLED", True)
    monkeypatch.setattr(config, "OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(config, "MODEL_CACHE_ENABLED", True)
    monkeypatch.setattr(config, "MODEL_CACHE_DIR", tmp_path / "model-cache")
    monkeypatch.setattr(config, "MODEL_CACHE_TTL_SEC", 3600)

    class ImageAPI:
        def __init__(self):
            self.calls = 0

        def generate(self, **kwargs):
            self.calls += 1
            payload = base64.b64encode(b"fake-png").decode("ascii")
            return SimpleNamespace(data=[SimpleNamespace(b64_json=payload)])

    api = ImageAPI()
    monkeypatch.setattr(images, "_client", SimpleNamespace(images=api))

    first = images.generate_image("same visual prompt", tmp_path / "one.png")
    second = images.generate_image("same visual prompt", tmp_path / "two.png")

    assert first.read_bytes() == second.read_bytes() == b"fake-png"
    assert api.calls == 1


def test_enabled_requires_both_the_flag_and_a_key(monkeypatch):
    monkeypatch.setattr(config, "IMAGE_ENABLED", True)
    monkeypatch.setattr(config, "OPENAI_API_KEY", "")
    assert images.enabled() is False

    monkeypatch.setattr(config, "OPENAI_API_KEY", "sk-test")
    assert images.enabled() is True

    monkeypatch.setattr(config, "IMAGE_ENABLED", False)
    assert images.enabled() is False


def test_service_skips_everything_when_disabled(monkeypatch, blueprint_series):
    monkeypatch.setattr(config, "IMAGE_ENABLED", False)
    result = image_service.ensure_series_images(blueprint_series)
    assert result["thumbnail"] is None
    assert result["characters"] == {}
    assert result["skipped"]
    assert image_service.start_images_job(blueprint_series) is None


# --------------------------------------------------------------------------- #
# character selection
# --------------------------------------------------------------------------- #
def test_selection_excludes_the_narrator(blueprint_series):
    chosen = image_service.select_characters(store.load_characters(blueprint_series))
    names = [c["name"] for c in chosen]
    assert "Narrator" not in names
    assert names == ["Benji", "Maya"]   # load order: narrator first, then alphabetical


def test_selection_excludes_characters_without_an_appearance():
    chosen = image_service.select_characters([
        {"name": "Maya", "physical_persona": "Dark braid, tired eyes."},
        {"name": "Ghost", "physical_persona": "", "description": ""},
    ])
    assert [c["name"] for c in chosen] == ["Maya"]


def test_selection_caps_at_the_configured_maximum(monkeypatch):
    monkeypatch.setattr(config, "MAX_CHARACTER_IMAGES", 3)
    cast = [{"name": f"C{i}", "physical_persona": "described"} for i in range(10)]
    assert len(image_service.select_characters(cast)) == 3


# --------------------------------------------------------------------------- #
# prompts
# --------------------------------------------------------------------------- #
def test_thumbnail_prompt_carries_the_story_and_setting():
    prompt = prompts.thumbnail_image(
        {"title": "Room 4B", "genre": "Supernatural Thriller"},
        {"setting": "A county hospital at night", "tone": "tense",
         "logline": "Three nights, one room.", "story_world": "A decaying hospital"},
    )
    assert "Room 4B" in prompt
    assert "Supernatural Thriller" in prompt
    assert "A county hospital at night" in prompt
    assert "Three nights, one room." in prompt
    assert "No text" in prompt or "no text" in prompt


def test_character_prompt_leads_with_physical_appearance():
    prompt = prompts.character_image(
        {"name": "Maya", "role": "protagonist", "gender": "Female",
         "personality": "stubborn, warm",
         "physical_persona": "Late twenties, tired eyes, dark braid."},
        {"genre": "Supernatural Thriller", "setting": "A county hospital at night"},
    )
    assert "Late twenties, tired eyes, dark braid." in prompt
    assert "stubborn, warm" in prompt
    assert "A county hospital at night" in prompt
    assert "no text" in prompt.lower()


def test_character_prompt_falls_back_to_description():
    prompt = prompts.character_image(
        {"name": "Benji", "description": "A weathered guard in a worn uniform."}, {})
    assert "A weathered guard in a worn uniform." in prompt


# --------------------------------------------------------------------------- #
# paths + computed flags
# --------------------------------------------------------------------------- #
def test_image_paths_live_under_the_series_folder(tmp_output):
    sid = "abc123"
    assert store.thumbnail_path(sid) == store.series_dir(sid) / "images" / "thumbnail.png"
    assert (store.character_image_path(sid, "maya")
            == store.series_dir(sid) / "images" / "characters" / "maya.png")


def test_character_key_matches_the_stored_file_stem():
    assert store.character_key({"name": "Dr. Ravi Menon"}) == "dr-ravi-menon"
    assert store.character_key({"name": "Maya", "is_narrator": True}) == "narrator"


def test_has_thumbnail_reflects_the_file_on_disk(blueprint_series):
    assert store.load_index(blueprint_series)["has_thumbnail"] is False

    path = store.thumbnail_path(blueprint_series)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"png")
    assert store.load_index(blueprint_series)["has_thumbnail"] is True


def test_has_image_reflects_the_file_on_disk(blueprint_series):
    by_name = {c["name"]: c for c in store.load_characters(blueprint_series)}
    assert by_name["Maya"]["has_image"] is False

    path = store.character_image_path(blueprint_series, "maya")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"png")

    by_name = {c["name"]: c for c in store.load_characters(blueprint_series)}
    assert by_name["Maya"]["has_image"] is True
    assert by_name["Benji"]["has_image"] is False


def test_computed_flags_are_never_written_to_disk(blueprint_series):
    """A load -> save round trip must not bake `has_image` into the JSON."""
    path = store.character_image_path(blueprint_series, "maya")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"png")

    maya = next(c for c in store.load_characters(blueprint_series) if c["name"] == "Maya")
    assert maya["has_image"] is True
    store.save_character(blueprint_series, maya)

    raw = store.read_json(store.characters_dir(blueprint_series) / "maya.json")
    assert "has_image" not in raw


# --------------------------------------------------------------------------- #
# generate-once
# --------------------------------------------------------------------------- #
def test_existing_artwork_is_never_regenerated(monkeypatch, blueprint_series):
    """Refining rewrites the blueprint; art the creator has seen must survive."""
    monkeypatch.setattr(config, "IMAGE_ENABLED", True)
    monkeypatch.setattr(config, "OPENAI_API_KEY", "sk-test")

    def explode(*args, **kwargs):
        raise AssertionError("an existing image must not be regenerated")

    monkeypatch.setattr(images, "generate_image", explode)

    thumb = store.thumbnail_path(blueprint_series)
    thumb.parent.mkdir(parents=True, exist_ok=True)
    thumb.write_bytes(b"png")
    portrait = store.character_image_path(blueprint_series, "maya")
    portrait.parent.mkdir(parents=True, exist_ok=True)
    portrait.write_bytes(b"png")

    assert image_service.generate_thumbnail(blueprint_series) == "images/thumbnail.png"
    maya = next(c for c in store.load_characters(blueprint_series) if c["name"] == "Maya")
    assert (image_service.generate_character_image(blueprint_series, maya)
            == "images/characters/maya.png")


def test_generation_writes_the_expected_files(monkeypatch, blueprint_series):
    monkeypatch.setattr(config, "IMAGE_ENABLED", True)
    monkeypatch.setattr(config, "OPENAI_API_KEY", "sk-test")

    seen: list[str] = []

    def fake_generate(prompt, path, *, size=None):
        seen.append(prompt)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"png")
        return path

    monkeypatch.setattr(images, "generate_image", fake_generate)

    result = image_service.ensure_series_images(blueprint_series)
    assert result["thumbnail"] == "images/thumbnail.png"
    assert set(result["characters"]) == {"maya", "benji"}
    assert store.thumbnail_path(blueprint_series).exists()
    assert store.character_image_path(blueprint_series, "maya").exists()
    assert not store.character_image_path(blueprint_series, "narrator").exists()
    assert len(seen) == 3   # one thumbnail + two portraits


def test_a_failed_portrait_does_not_lose_the_others(monkeypatch, blueprint_series):
    monkeypatch.setattr(config, "IMAGE_ENABLED", True)
    monkeypatch.setattr(config, "OPENAI_API_KEY", "sk-test")

    def flaky(prompt, path, *, size=None):
        if "Benji" in prompt:
            raise RuntimeError("provider blew up")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"png")
        return path

    monkeypatch.setattr(images, "generate_image", flaky)

    result = image_service.ensure_series_images(blueprint_series)
    assert result["thumbnail"] == "images/thumbnail.png"
    assert result["characters"]["maya"] == "images/characters/maya.png"
    assert "benji" not in result["characters"]
