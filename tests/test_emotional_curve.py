"""Emotional curve: top-3 tracked emotions charted across the episode plan."""
from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from app import schemas, store, story_service
from app.main import app


def _await_job(client, job_id: str, timeout: float = 5.0) -> dict:
    """Poll a background job until it leaves queued/running (jobs run on a thread)."""
    deadline = time.monotonic() + timeout
    job = client.get(f"/studio/jobs/{job_id}").json()
    while job["state"] in ("queued", "running") and time.monotonic() < deadline:
        time.sleep(0.05)
        job = client.get(f"/studio/jobs/{job_id}").json()
    return job


# --------------------------------------------------------------------------- #
# store persistence
# --------------------------------------------------------------------------- #
def test_save_emotional_curve_builds_chart_ready_points(tmp_output):
    sid = "series-1"
    outlines = [{"number": 1, "title": "Night One"}, {"number": 2, "title": "Night Two"}]
    for outline in outlines:
        store.save_episode_outline(sid, outline)

    analysis = schemas.EmotionCurve(
        emotion_1_label="Cold Betrayal", emotion_2_label="Hope", emotion_3_label="Hope",
        dominant_emotion="Cold Betrayal", summary="Rises then breaks.",
        points=[
            schemas.EmotionCurvePoint(episode=2, emotion_1=80, emotion_2=20, emotion_3=10),
            schemas.EmotionCurvePoint(episode=1, emotion_1=30, emotion_2=40, emotion_3=15),
        ],
    ).model_dump()

    saved = store.save_emotional_curve(sid, analysis, outlines)

    # Labels are slugified into stable, unique chart keys (duplicate "Hope" disambiguated).
    keys = [e["key"] for e in saved["emotions"]]
    assert keys == ["cold_betrayal", "hope", "hope_2"]
    assert [e["label"] for e in saved["emotions"]] == ["Cold Betrayal", "Hope", "Hope"]

    # Points are sorted by episode and carry the outline title + a chart "beat" label.
    assert [p["episode"] for p in saved["points"]] == [1, 2]
    assert saved["points"][0]["beat"] == "E1"
    assert saved["points"][0]["title"] == "Night One"
    assert saved["points"][0]["cold_betrayal"] == 30
    assert saved["points"][1]["cold_betrayal"] == 80

    assert saved["dominant_emotion"] == "cold_betrayal"
    assert saved["stale"] is False
    assert store.load_emotional_curve(sid) == saved


def test_save_emotional_curve_clamps_out_of_range_and_missing_values(tmp_output):
    sid = "series-2"
    store.save_episode_outline(sid, {"number": 1, "title": "Ep 1"})
    analysis = {
        "emotion_1_label": "Fear", "emotion_2_label": "Joy", "emotion_3_label": "Awe",
        "dominant_emotion": "unknown emotion", "summary": "",
        "points": [{"episode": 1, "emotion_1": 500, "emotion_2": -20}],
    }
    saved = store.save_emotional_curve(sid, analysis)
    point = saved["points"][0]
    assert point["fear"] == 100        # clamped to the 0-100 ceiling
    assert point["joy"] == 0           # clamped to the 0-100 floor
    assert point["awe"] == 0           # missing field defaults to 0
    # An unrecognised dominant_emotion falls back to the first tracked emotion.
    assert saved["dominant_emotion"] == "fear"


def test_mark_emotional_curve_stale_is_a_noop_before_first_generation(tmp_output):
    sid = "series-3"
    store.mark_emotional_curve_stale(sid)  # must not raise
    assert store.load_emotional_curve(sid) == {}


def test_mark_emotional_curve_stale_flags_an_existing_curve(tmp_output):
    sid = "series-4"
    store.save_episode_outline(sid, {"number": 1, "title": "Ep 1"})
    store.save_emotional_curve(sid, {
        "emotion_1_label": "Fear", "emotion_2_label": "Joy", "emotion_3_label": "Awe",
        "dominant_emotion": "Fear", "summary": "x",
        "points": [{"episode": 1, "emotion_1": 10, "emotion_2": 10, "emotion_3": 10}],
    })
    store.mark_emotional_curve_stale(sid)
    assert store.load_emotional_curve(sid)["stale"] is True


def test_load_blueprint_bundles_the_emotional_curve(tmp_output):
    sid = "series-5"
    assert store.load_blueprint(sid)["emotional_curve"] == {}


# --------------------------------------------------------------------------- #
# service layer
# --------------------------------------------------------------------------- #
def test_generate_emotional_curve_requires_an_episode_plan(offline):
    with pytest.raises(ValueError):
        story_service.generate_emotional_curve("no-episodes-yet")


def test_generate_emotional_curve_uses_the_fake_llm(offline):
    sid = "series-6"
    store.save_blueprint(sid, {"logline": "x"}, meta={"genre": "horror", "theme": "grief"})
    store.save_episode_outline(sid, {
        "number": 1, "title": "Night One", "summary": "Maya starts the case.",
        "emotional_focus": "dread", "cliffhanger": "The door opens.",
    })
    result = story_service.generate_emotional_curve(sid)
    assert len(result["emotions"]) == 3
    assert len(result["points"]) == 1
    assert result["points"][0]["episode"] == 1


# --------------------------------------------------------------------------- #
# HTTP layer
# --------------------------------------------------------------------------- #
@pytest.fixture
def client(offline, monkeypatch):
    from app.graph import build_graph
    fresh = build_graph()
    monkeypatch.setattr("app.main.GRAPH", fresh)
    return TestClient(app)


def _build_to_episode_plan(client, ep_count=2) -> str:
    body = client.post("/series", json={"idea": "A nurse, a ghost, three nights."}).json()
    sid = body["series_id"]
    guard = 0
    while body.get("status") == "awaiting_review" and body.get("stage") != "episode_plan":
        guard += 1
        assert guard < 30, "pipeline did not reach episode_plan"
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
    assert body["stage"] == "episode_plan"
    return sid


def test_regenerate_404s_for_unknown_series(client):
    r = client.post("/studio/series/nope/emotional-curve/regenerate")
    assert r.status_code == 404


def test_regenerate_409s_before_the_episode_plan_exists(client):
    sid = client.post("/series", json={"idea": "x"}).json()["series_id"]
    r = client.post(f"/studio/series/{sid}/emotional-curve/regenerate")
    assert r.status_code == 409


def test_get_emotional_curve_is_empty_before_generation(client):
    sid = _build_to_episode_plan(client)
    assert client.get(f"/studio/series/{sid}/emotional-curve").json() == {}


def test_regenerate_then_poll_produces_one_point_per_episode(client):
    sid = _build_to_episode_plan(client, ep_count=3)
    job = client.post(f"/studio/series/{sid}/emotional-curve/regenerate")
    assert job.status_code == 202
    job_id = job.json()["id"]

    polled = _await_job(client, job_id)
    assert polled["state"] == "done", polled

    curve = client.get(f"/studio/series/{sid}/emotional-curve").json()
    assert len(curve["emotions"]) == 3
    assert len(curve["points"]) == 3
    assert {p["episode"] for p in curve["points"]} == {1, 2, 3}
    assert curve["dominant_emotion"] in {e["key"] for e in curve["emotions"]}

    # The series bundle used by the Ideaboard carries the same curve.
    bundled = client.get(f"/studio/series/{sid}").json()
    assert bundled["blueprint"]["emotional_curve"]["points"] == curve["points"]


def test_editing_an_outline_marks_the_curve_stale(client):
    sid = _build_to_episode_plan(client, ep_count=2)
    job_id = client.post(f"/studio/series/{sid}/emotional-curve/regenerate").json()["id"]
    _await_job(client, job_id)

    outline = client.get(f"/studio/series/{sid}/episodes/1").json()["outline"]
    outline["summary"] = "A completely different turn of events."
    client.put(f"/studio/series/{sid}/episodes/1/outline", json={"outline": outline})

    assert client.get(f"/studio/series/{sid}/emotional-curve").json()["stale"] is True


def test_patching_the_blueprint_marks_the_curve_stale(client):
    sid = _build_to_episode_plan(client, ep_count=2)
    job_id = client.post(f"/studio/series/{sid}/emotional-curve/regenerate").json()["id"]
    _await_job(client, job_id)

    client.patch(f"/studio/series/{sid}/blueprint", json={"plot": {"main_storyline": "New arc."}})

    assert client.get(f"/studio/series/{sid}/emotional-curve").json()["stale"] is True
