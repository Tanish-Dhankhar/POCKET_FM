"""End-to-end contract for the model-free presentation replay."""
from __future__ import annotations

import shutil
import time

import pytest
from fastapi.testclient import TestClient

from app import config, demo_replay, store
from app.main import app


@pytest.fixture
def client(offline, monkeypatch):
    from app.graph import build_graph

    monkeypatch.setattr("app.main.GRAPH", build_graph())
    return TestClient(app)


def test_canonical_idea_replays_every_wizard_stage_without_model_calls(
    client, offline, monkeypatch,
):
    source = config.PROJECT_ROOT / "output" / demo_replay.TEMPLATE_SERIES_ID
    target = config.OUTPUT_DIR / demo_replay.TEMPLATE_SERIES_ID
    assert source.is_dir(), "the committed demo cache is missing"
    shutil.copytree(source, target)

    monkeypatch.setattr(config, "DEMO_REPLAY_ENABLED", True)
    monkeypatch.setattr(config, "DEMO_REPLAY_STEP_DELAY_SEC", 0.0)
    calls_before = len(offline["llm"].calls)

    created = client.post("/series", json={"idea": demo_replay.CANONICAL_IDEA})
    assert created.status_code == 200, created.text
    body = created.json()
    series_id = body["series_id"]
    assert series_id != demo_replay.TEMPLATE_SERIES_ID
    assert body["stage"] == "extract"
    assert body["demo_replay"] is True
    assert body["model_calls"] == 0

    body = client.post(f"/series/{series_id}/approve").json()
    assert body["stage"] == "clarify"
    assert len(body["payload"]["questions"]) == 4
    assert all(len(question["options"]) == 3 for question in body["payload"]["questions"])

    card = client.post(f"/studio/series/{series_id}/confirm-card").json()
    assert card["title"] == "The Thursday Lie"

    answers = [
        {"question": question["question"], "answer": question["options"][0]["label"]}
        for question in body["payload"]["questions"]
    ]
    body = client.post(
        f"/series/{series_id}/submit",
        json={"data": {"clarification_answers": answers}},
    ).json()
    assert body["stage"] == "blueprint"
    assert body["payload"]["blueprint"]["theme_tags"] == card["theme_tags"]

    saved = client.post(
        f"/studio/series/{series_id}/confirmations",
        json={
            "title": card["title"],
            "genre": card["genre"],
            "setting": card["setting"],
            "include_narrator": card["narrator_suggested"],
            "ep_count": card["recommended_ep_count"],
            "ep_minutes": card["recommended_ep_minutes"],
            "genre_tags": card["genre_tags"],
            "theme_tags": card["theme_tags"],
        },
    )
    assert saved.status_code == 200, saved.text

    assert client.post(f"/series/{series_id}/approve").json()["stage"] == "ep_config"
    body = client.post(
        f"/series/{series_id}/submit",
        json={"data": {"ep_count": 8, "ep_minutes": 5, "include_narrator": False}},
    ).json()
    assert body["stage"] == "episode_plan"
    assert len(body["payload"]["episodes"]) == 8

    queued = client.post(f"/studio/series/{series_id}/analysis/regenerate")
    assert queued.status_code == 202, queued.text
    job_id = queued.json()["id"]
    for _ in range(100):
        job = client.get(f"/studio/jobs/{job_id}").json()
        if job["state"] in {"done", "error"}:
            break
        time.sleep(0.01)
    assert job["state"] == "done", job
    assert job["result"] == {"series_id": series_id, "cached": True, "model_calls": 0}

    state = client.get(f"/series/{series_id}/state").json()
    assert state["stage"] == "episode_ready"
    assert state["awaiting_review"] is False
    assert state["model_calls"] == 0
    assert len(offline["llm"].calls) == calls_before

    # The first loader finishes on the Idea Board. Although all media files are
    # already cloned, Episode 1 stays visually planned until the presenter
    # clicks Generate Episode and watches the second cached loading sequence.
    board = client.get(f"/studio/series/{series_id}").json()
    assert board["episodes"][0]["status"] == "planned"

    queued = client.post(f"/studio/series/{series_id}/episodes/1/generate")
    assert queued.status_code == 202, queued.text
    episode_job_id = queued.json()["id"]
    for _ in range(100):
        episode_job = client.get(f"/studio/jobs/{episode_job_id}").json()
        if episode_job["state"] in {"done", "error"}:
            break
        time.sleep(0.01)
    assert episode_job["state"] == "done", episode_job
    assert episode_job["result"]["cached"] is True
    assert episode_job["result"]["model_calls"] == 0
    board = client.get(f"/studio/series/{series_id}").json()
    assert board["episodes"][0]["status"] == "ready"
    assert len(offline["llm"].calls) == calls_before

    manifest = store.load_audio_manifest(series_id)["1"]
    assert series_id in manifest["final"]
    assert demo_replay.TEMPLATE_SERIES_ID not in manifest["final"]
    audio = client.get(f"/series/{series_id}/episodes/1/audio")
    assert audio.status_code == 200
    assert audio.content[:4] == b"RIFF"
    assert client.get(f"/studio/series/{series_id}/thumbnail").status_code == 200
    assert client.get(f"/studio/series/{series_id}/characters/maya/image").status_code == 200
