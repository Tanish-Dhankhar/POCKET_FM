"""Focused regression tests for the bounded in-process job scheduler."""
from __future__ import annotations

import threading
import time

import pytest

from app import config, jobs


def _wait_for(job_id: str, state: str, timeout: float = 2.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = jobs.get(job_id)
        if job and job["state"] == state:
            return job
        time.sleep(0.01)
    raise AssertionError(f"job {job_id} did not reach {state}")


def test_start_or_rejoin_is_atomic_for_the_same_key():
    release = threading.Event()

    def work(handle):
        release.wait(1)
        return {"ok": True}

    first = jobs.start_or_rejoin("test", work, dedupe_key=("test", "same"))
    second = jobs.start_or_rejoin("test", work, dedupe_key=("test", "same"))

    assert first["id"] == second["id"]
    assert "dedupe_key" not in first
    release.set()
    assert _wait_for(first["id"], "done")["result"] == {"ok": True}


def test_worker_result_can_mark_a_job_cancelled():
    job = jobs.start_or_rejoin(
        "test", lambda handle: {"cancelled": True, "step": "voices"},
        dedupe_key=("test", "cancelled-result"),
    )

    finished = _wait_for(job["id"], "cancelled")
    assert finished["message"] == "Cancelled"


def test_at_most_five_story_jobs_can_run_at_once(monkeypatch):
    """A 6th distinct story generation is rejected while five are active."""
    monkeypatch.setattr(config, "STORY_MAX_CONCURRENCY", 5)
    release = threading.Event()

    def work(handle):
        release.wait(2)
        return {"ok": True}

    started = [
        jobs.start_or_rejoin(
            "episode", work, dedupe_key=("episode", f"series-{i}", i),
            series_id=f"series-{i}", number=i,
        )
        for i in range(5)
    ]
    assert len({job["id"] for job in started}) == 5

    with pytest.raises(jobs.QueueFullError, match="at most 5 stories"):
        jobs.start_or_rejoin(
            "episode", work, dedupe_key=("episode", "series-overflow", 1),
            series_id="series-overflow", number=1,
        )

    # Rejoining an in-flight story still works under the cap.
    rejoined = jobs.start_or_rejoin(
        "episode", work, dedupe_key=("episode", "series-0", 0),
        series_id="series-0", number=0,
    )
    assert rejoined["id"] == started[0]["id"]

    # Non-story work (e.g. images) is not counted against the story cap.
    images = jobs.start_or_rejoin(
        "images", work, dedupe_key=("images", "series-art"),
        series_id="series-art",
    )
    assert images["state"] in ("queued", "running")

    release.set()
    for job in started:
        _wait_for(job["id"], "done")
    _wait_for(images["id"], "done")


def test_synchronous_pipeline_requests_share_the_story_budget(monkeypatch):
    """Wizard traffic counts too: 5 concurrent creators fill the studio."""
    monkeypatch.setattr(config, "STORY_MAX_CONCURRENCY", 2)

    with jobs.story_slot():
        with jobs.story_slot():
            assert jobs.summary()["story_active"] == 2
            with pytest.raises(jobs.QueueFullError, match="at most 2 stories"):
                with jobs.story_slot():
                    pass
        # Leaving a slot frees capacity for the next creator immediately.
        assert jobs.summary()["story_active"] == 1
        with jobs.story_slot():
            pass

    assert jobs.summary()["story_active"] == 0


def test_a_held_slot_blocks_a_background_story_job(monkeypatch):
    """A synchronous creator and a background job cannot both exceed the cap."""
    monkeypatch.setattr(config, "STORY_MAX_CONCURRENCY", 1)

    with jobs.story_slot():
        with pytest.raises(jobs.QueueFullError):
            jobs.start_or_rejoin(
                "episode", lambda handle: {"ok": True},
                dedupe_key=("episode", "blocked-series", 1),
                series_id="blocked-series", number=1,
            )

    job = jobs.start_or_rejoin(
        "episode", lambda handle: {"ok": True},
        dedupe_key=("episode", "blocked-series", 1),
        series_id="blocked-series", number=1,
    )
    assert _wait_for(job["id"], "done")["result"] == {"ok": True}


def test_every_ai_job_kind_counts_against_the_story_budget(monkeypatch):
    """Remixes and the rest of the AI-backed kinds share the same cap."""
    monkeypatch.setattr(config, "STORY_MAX_CONCURRENCY", 1)

    for kind in sorted(config.STORY_JOB_KINDS):
        with jobs.story_slot():
            with pytest.raises(jobs.QueueFullError):
                jobs.start_or_rejoin(
                    kind, lambda handle: {"ok": True},
                    dedupe_key=(kind, f"budget-{kind}"),
                    series_id=f"budget-{kind}",
                )


def test_capacity_detail_carries_the_code_the_ui_matches_on():
    detail = jobs.capacity_detail(jobs.QueueFullError("full"))
    assert detail["code"] == jobs.CAPACITY_CODE
    assert detail["limit"] == config.STORY_MAX_CONCURRENCY
