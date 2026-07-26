"""FastAPI route tests — driven through the real HTTP layer with TestClient."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import config
from app.main import app


@pytest.fixture
def client(offline, monkeypatch):
    """A client whose graph is fresh per test, with LLM/TTS stubbed."""
    from app.graph import build_graph
    fresh = build_graph()
    monkeypatch.setattr("app.main.GRAPH", fresh)
    return TestClient(app)


def _create(client, idea="A nurse, a ghost, three nights.") -> dict:
    r = client.post("/series", json={"idea": idea})
    assert r.status_code == 200, r.text
    return r.json()


# --------------------------------------------------------------------------- #
# health
# --------------------------------------------------------------------------- #
def test_health_reports_configured_models(client):
    body = client.get("/health").json()
    assert body["ok"] is True
    assert body["text_models"] == {
        "hard": config.TEXT_MODEL_HARD,
        "easy": config.TEXT_MODEL_EASY,
    }
    assert body["transcription_model"] == config.TRANSCRIPTION_MODEL
    assert body["tts_model"] == config.TTS_MODEL


# --------------------------------------------------------------------------- #
# create + review loop
# --------------------------------------------------------------------------- #
def test_create_series_returns_first_review(client):
    body = _create(client)
    assert body["status"] == "awaiting_review"
    assert body["stage"] == "extract"
    assert body["series_id"]
    assert body["payload"]["logline"]


def test_series_ids_are_unique(client):
    assert _create(client)["series_id"] != _create(client)["series_id"]


def test_state_endpoint_reflects_pending_review(client):
    sid = _create(client)["series_id"]
    body = client.get(f"/series/{sid}/state").json()
    assert body["awaiting_review"] is True
    assert body["stage"] == "extract"
    assert body["state"]["idea"]


def test_state_endpoint_404s_for_unknown_series(client):
    assert client.get("/series/does-not-exist/state").status_code == 404


def test_approve_advances_to_the_next_stage(client):
    sid = _create(client)["series_id"]
    body = client.post(f"/series/{sid}/approve", json={"action": "approve"}).json()
    assert body["stage"] == "clarify"


def test_approve_works_with_an_empty_body(client):
    """The frontend's simplest possible call: approve with no JSON at all."""
    sid = _create(client)["series_id"]
    r = client.post(f"/series/{sid}/approve")
    assert r.status_code == 200, r.text
    assert r.json()["stage"] == "clarify"


def test_edit_endpoint_persists_creator_changes(client):
    sid = _create(client)["series_id"]
    client.post(f"/series/{sid}/edit",
                json={"action": "edit", "data": {"genre": "cosmic horror"}})
    state = client.get(f"/series/{sid}/state").json()["state"]
    assert state["genre"] == "cosmic horror"


def test_regenerate_endpoint_returns_the_same_stage_again(client):
    sid = _create(client)["series_id"]
    body = client.post(f"/series/{sid}/regenerate",
                       json={"action": "regenerate", "note": "darker"}).json()
    assert body["stage"] == "extract", "regenerate must re-present the same stage"


def test_unknown_series_404s_on_every_resume_route(client):
    for route in ("approve", "edit", "submit", "regenerate"):
        r = client.post(f"/series/nope/{route}", json={"action": "approve"})
        assert r.status_code == 404, f"{route} did not 404"


# --------------------------------------------------------------------------- #
# full run through HTTP
# --------------------------------------------------------------------------- #
def _run_to_done(client, ep_count=1) -> dict:
    body = _create(client)
    sid = body["series_id"]
    guard = 0
    while body.get("status") == "awaiting_review":
        guard += 1
        assert guard < 30, "pipeline did not terminate"
        stage = body["stage"]
        if stage == "clarify":
            body = client.post(f"/series/{sid}/submit",
                               json={"action": "submit",
                                     "data": {"clarification_answers": []}}).json()
        elif stage == "ep_config":
            body = client.post(f"/series/{sid}/submit",
                               json={"action": "submit",
                                     "data": {"ep_count": ep_count, "ep_minutes": 5}}).json()
        else:
            body = client.post(f"/series/{sid}/approve").json()
    return sid, body


def test_full_run_through_http_completes(client):
    sid, body = _run_to_done(client)
    assert body["status"] == "done"
    assert body["stage"] == "deliver"
    assert "1" in body["audio_manifest"]


def test_audio_download_returns_a_wav(client):
    sid, _ = _run_to_done(client)
    r = client.get(f"/series/{sid}/episodes/1/audio")
    assert r.status_code == 200
    assert r.headers["content-type"] == "audio/wav"
    assert r.content[:4] == b"RIFF", "response is not a real WAV"
    assert len(r.content) > 10_000


def test_audio_download_404s_before_generation(client):
    sid = _create(client)["series_id"]
    assert client.get(f"/series/{sid}/episodes/1/audio").status_code == 404


def test_audio_download_404s_for_unknown_episode(client):
    sid, _ = _run_to_done(client)
    assert client.get(f"/series/{sid}/episodes/99/audio").status_code == 404


def test_state_shows_not_awaiting_review_when_done(client):
    sid, _ = _run_to_done(client)
    body = client.get(f"/series/{sid}/state").json()
    assert body["awaiting_review"] is False
    assert body["stage"] == "deliver"


# --------------------------------------------------------------------------- #
# continuation
# --------------------------------------------------------------------------- #
def test_continue_appends_the_arc_and_reopens_review(client):
    sid, _ = _run_to_done(client)
    body = client.post(f"/series/{sid}/continue",
                       json={"plot": "A decade later, Maya is the patient."}).json()

    assert body["status"] == "awaiting_review"
    assert body["stage"] == "blueprint", "continuation must re-enter at blueprint"
    state = client.get(f"/series/{sid}/state").json()["state"]
    assert state["arcs"] == ["A decade later, Maya is the patient."]


def test_continue_feeds_prior_arcs_into_the_prompt(client, offline):
    sid, _ = _run_to_done(client)
    client.post(f"/series/{sid}/continue", json={"plot": "Maya becomes the patient."})
    blueprint_prompts = [p for name, p in offline["llm"].calls if name == "Blueprint"]
    assert "Maya becomes the patient." in blueprint_prompts[-1]
    assert "CONTINUATION PLOTS" in blueprint_prompts[-1]


def test_continue_404s_for_unknown_series(client):
    assert client.post("/series/nope/continue", json={"plot": "x"}).status_code == 404


def test_continue_resets_approvals_for_the_new_pass(client):
    sid, _ = _run_to_done(client)
    client.post(f"/series/{sid}/continue", json={"plot": "New arc."})
    approvals = client.get(f"/series/{sid}/state").json()["approvals"]
    assert not approvals.get("blueprint"), "stale approval carried into the new pass"


# --------------------------------------------------------------------------- #
# validation
# --------------------------------------------------------------------------- #
def test_create_series_requires_an_idea(client):
    assert client.post("/series", json={}).status_code == 422


def test_continue_requires_a_plot(client):
    sid, _ = _run_to_done(client)
    assert client.post(f"/series/{sid}/continue", json={}).status_code == 422


def test_cors_allows_a_browser_frontend(client):
    """The React frontend runs on a different origin and must be able to call this."""
    r = client.options("/series", headers={
        "Origin": "http://localhost:5173",
        "Access-Control-Request-Method": "POST",
    })
    assert r.status_code < 400, "CORS preflight rejected — browser frontend cannot call the API"
    assert "access-control-allow-origin" in {k.lower() for k in r.headers}
