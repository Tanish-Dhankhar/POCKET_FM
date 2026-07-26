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
    assert body["text_call_routes"] == config.TEXT_TASKS
    assert body["model_cache"]["enabled"] == config.MODEL_CACHE_ENABLED
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


def test_confirm_card_is_preloaded_without_an_extra_llm_call(client, offline):
    sid = _create(client)["series_id"]
    calls_before = len(offline["llm"].calls)

    card = client.post(f"/studio/series/{sid}/confirm-card").json()

    assert card["title"]
    assert len(offline["llm"].calls) == calls_before


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


# --------------------------------------------------------------------------- #
# capacity
# --------------------------------------------------------------------------- #
def test_a_creator_over_the_limit_gets_a_429_the_ui_can_recognise(client, monkeypatch):
    """With every story slot held, a new creator is turned away, not queued."""
    from app import jobs

    monkeypatch.setattr(config, "STORY_MAX_CONCURRENCY", 1)
    with jobs.story_slot():
        r = client.post("/series", json={"idea": "A nurse, a ghost, three nights."})

    assert r.status_code == 429
    detail = r.json()["detail"]
    assert detail["code"] == jobs.CAPACITY_CODE
    assert detail["limit"] == 1
    assert "1 stories can be generated at once" in detail["message"]
    assert r.headers["Retry-After"] == "30"


def test_capacity_is_released_once_the_request_finishes(client, monkeypatch):
    """A rejected creator succeeds on retry — the slot is not leaked."""
    from app import jobs

    monkeypatch.setattr(config, "STORY_MAX_CONCURRENCY", 1)
    with jobs.story_slot():
        assert client.post("/series", json={"idea": "A nurse and a ghost."}).status_code == 429

    assert _create(client)["status"] == "awaiting_review"
    assert jobs.summary()["story_active"] == 0


def test_confirm_card_generation_is_capped_but_the_cached_draft_is_not(client, monkeypatch):
    """Only the branch that actually calls the model consumes a story slot."""
    from app import jobs, store

    sid = _create(client)["series_id"]
    (store.input_dir(sid) / "confirmation_draft.json").unlink(missing_ok=True)

    monkeypatch.setattr(config, "STORY_MAX_CONCURRENCY", 1)
    with jobs.story_slot():
        r = client.post(f"/studio/series/{sid}/confirm-card")
        assert r.status_code == 429
        assert r.json()["detail"]["code"] == jobs.CAPACITY_CODE

    assert client.post(f"/studio/series/{sid}/confirm-card").status_code == 200

    # The draft is now cached; serving it does no AI work, so no slot is needed.
    with jobs.story_slot():
        assert client.post(f"/studio/series/{sid}/confirm-card").status_code == 200


def test_transcription_is_turned_away_at_capacity(client, monkeypatch):
    from app import jobs

    monkeypatch.setattr(config, "STORY_MAX_CONCURRENCY", 1)
    with jobs.story_slot():
        r = client.post("/studio/transcribe",
                        files={"file": ("idea.webm", b"not-really-audio", "audio/webm")})

    assert r.status_code == 429
    assert r.json()["detail"]["code"] == jobs.CAPACITY_CODE


def test_voice_sample_rendering_is_turned_away_at_capacity(client, monkeypatch, tmp_path):
    """An uncached voice preview is a TTS call and respects the budget."""
    from app import jobs

    monkeypatch.setattr(config, "ASSETS_DIR", tmp_path)  # guarantee a cache miss
    monkeypatch.setattr(config, "STORY_MAX_CONCURRENCY", 1)
    voice = next(iter(config.VOICES))
    with jobs.story_slot():
        r = client.get(f"/studio/voices/{voice}/sample")

    assert r.status_code == 429
    assert r.json()["detail"]["code"] == jobs.CAPACITY_CODE


def test_cors_allows_a_browser_frontend(client):
    """The React frontend runs on a different origin and must be able to call this."""
    r = client.options("/series", headers={
        "Origin": "http://localhost:5173",
        "Access-Control-Request-Method": "POST",
    })
    assert r.status_code < 400, "CORS preflight rejected — browser frontend cannot call the API"
    assert "access-control-allow-origin" in {k.lower() for k in r.headers}
