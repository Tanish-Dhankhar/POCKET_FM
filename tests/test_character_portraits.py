"""Character portraits: lazy Gemini image generation, cached per character."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import character_art, store
from app.main import app


# --------------------------------------------------------------------------- #
# store helpers
# --------------------------------------------------------------------------- #
def test_mark_portrait_stale_is_a_noop_before_first_generation(tmp_output):
    sid = "series-1"
    store.save_character(sid, {"name": "Maya", "personality": "stubborn"})
    store.mark_character_portrait_stale(sid, "maya")  # must not raise
    assert store.load_character(sid, "maya").get("portrait_stale") is None


def test_mark_portrait_stale_flags_a_generated_portrait(tmp_output):
    sid = "series-2"
    store.save_character(sid, {
        "name": "Maya", "personality": "stubborn",
        "portrait_generated_at": "2024-01-01T00:00:00+00:00",
    })
    store.mark_character_portrait_stale(sid, "maya")
    assert store.load_character(sid, "maya")["portrait_stale"] is True


def test_mark_all_portraits_stale_only_touches_generated_ones(tmp_output):
    sid = "series-3"
    store.save_character(sid, {"name": "Maya", "portrait_generated_at": "t"})
    store.save_character(sid, {"name": "Benji"})  # never generated
    store.mark_all_character_portraits_stale(sid)
    assert store.load_character(sid, "maya")["portrait_stale"] is True
    assert store.load_character(sid, "benji").get("portrait_stale") is None


# --------------------------------------------------------------------------- #
# service layer
# --------------------------------------------------------------------------- #
def test_ensure_portrait_rejects_an_unknown_character(offline):
    with pytest.raises(ValueError):
        character_art.ensure_portrait("no-such-series", "maya")


def test_ensure_portrait_renders_once_and_caches(offline):
    sid = "series-4"
    store.save_character(sid, {"name": "Maya", "personality": "stubborn, warm",
                               "physical_persona": "Lean, watchful, tired eyes."})
    path = character_art.ensure_portrait(sid, "maya")
    assert path.exists()
    assert path.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    assert len(offline["images"].rendered) == 1

    # Second call is a cache hit — no second (billable) render.
    character_art.ensure_portrait(sid, "maya")
    assert len(offline["images"].rendered) == 1

    character = store.load_character(sid, "maya")
    assert character["portrait_stale"] is False
    assert character["portrait_generated_at"]


def test_ensure_portrait_force_always_rerenders(offline):
    sid = "series-5"
    store.save_character(sid, {"name": "Maya"})
    character_art.ensure_portrait(sid, "maya")
    character_art.ensure_portrait(sid, "maya", force=True)
    assert len(offline["images"].rendered) == 2


# --------------------------------------------------------------------------- #
# HTTP layer
# --------------------------------------------------------------------------- #
@pytest.fixture
def client(offline, monkeypatch):
    from app.graph import build_graph
    fresh = build_graph()
    monkeypatch.setattr("app.main.GRAPH", fresh)
    return TestClient(app)


def _build_to_blueprint(client) -> str:
    """Drive the wizard far enough that Maya, Benji, and a Narrator all exist."""
    body = client.post("/series", json={"idea": "A nurse, a ghost, three nights."}).json()
    sid = body["series_id"]
    body = client.post(f"/series/{sid}/approve").json()
    assert body["stage"] == "clarify"
    body = client.post(f"/series/{sid}/submit",
                       json={"action": "submit",
                             "data": {"clarification_answers": []}}).json()
    assert body["stage"] == "blueprint"
    return sid


def test_get_portrait_404s_for_unknown_series(client):
    assert client.get("/studio/series/nope/characters/maya/portrait").status_code == 404


def test_get_portrait_404s_for_unknown_character(client):
    sid = _build_to_blueprint(client)
    assert client.get(f"/studio/series/{sid}/characters/nope/portrait").status_code == 404


def test_get_portrait_renders_lazily_and_caches(client, offline):
    sid = _build_to_blueprint(client)
    r1 = client.get(f"/studio/series/{sid}/characters/maya/portrait")
    assert r1.status_code == 200
    assert r1.headers["content-type"] == "image/png"
    assert r1.content[:8] == b"\x89PNG\r\n\x1a\n"
    assert len(offline["images"].rendered) == 1

    r2 = client.get(f"/studio/series/{sid}/characters/maya/portrait")
    assert r2.status_code == 200
    assert len(offline["images"].rendered) == 1, "second load must be a cache hit"


def test_regenerate_forces_a_fresh_render(client, offline):
    sid = _build_to_blueprint(client)
    client.get(f"/studio/series/{sid}/characters/maya/portrait")
    r = client.post(f"/studio/series/{sid}/characters/maya/portrait/regenerate")
    assert r.status_code == 200
    assert r.json()["stale"] is False
    assert len(offline["images"].rendered) == 2


def test_editing_appearance_marks_the_portrait_stale_and_rerenders(client, offline):
    sid = _build_to_blueprint(client)
    client.get(f"/studio/series/{sid}/characters/maya/portrait")
    assert len(offline["images"].rendered) == 1

    client.patch(f"/studio/series/{sid}/characters/maya",
                json={"physical_persona": "Now with a long scar across one cheek."})
    character = client.get(f"/studio/series/{sid}/characters").json()["characters"]
    maya = next(c for c in character if c["name"] == "Maya")
    assert maya["portrait_stale"] is True

    client.get(f"/studio/series/{sid}/characters/maya/portrait")
    assert len(offline["images"].rendered) == 2, "appearance edit must trigger a re-render"


def test_editing_unrelated_fields_does_not_mark_the_portrait_stale(client, offline):
    sid = _build_to_blueprint(client)
    client.get(f"/studio/series/{sid}/characters/maya/portrait")
    assert len(offline["images"].rendered) == 1

    client.patch(f"/studio/series/{sid}/characters/maya",
                json={"relationships": ["knows Benji"]})
    character = client.get(f"/studio/series/{sid}/characters").json()["characters"]
    maya = next(c for c in character if c["name"] == "Maya")
    assert not maya.get("portrait_stale")

    client.get(f"/studio/series/{sid}/characters/maya/portrait")
    assert len(offline["images"].rendered) == 1, "unrelated edits must not trigger a re-render"


def test_patching_the_blueprint_marks_every_portrait_stale(client, offline):
    sid = _build_to_blueprint(client)
    client.get(f"/studio/series/{sid}/characters/maya/portrait")
    client.get(f"/studio/series/{sid}/characters/benji/portrait")
    assert len(offline["images"].rendered) == 2

    client.patch(f"/studio/series/{sid}/blueprint", json={"genre": {"genre": "cosmic horror"}})

    characters = client.get(f"/studio/series/{sid}/characters").json()["characters"]
    assert all(c["portrait_stale"] for c in characters if c.get("portrait_generated_at"))

    client.get(f"/studio/series/{sid}/characters/maya/portrait")
    client.get(f"/studio/series/{sid}/characters/benji/portrait")
    assert len(offline["images"].rendered) == 4, "both cached portraits must re-render"


def test_renaming_a_character_drops_its_old_portrait(client, offline):
    sid = _build_to_blueprint(client)
    client.get(f"/studio/series/{sid}/characters/maya/portrait")

    r = client.patch(f"/studio/series/{sid}/characters/maya", json={"name": "Maya Reyes"})
    assert r.status_code == 200

    assert client.get(f"/studio/series/{sid}/characters/maya/portrait").status_code == 404
    r2 = client.get(f"/studio/series/{sid}/characters/maya-reyes/portrait")
    assert r2.status_code == 200
    assert len(offline["images"].rendered) == 2
