"""Focused regression tests for the bounded in-process job scheduler."""
from __future__ import annotations

import threading
import time

from app import jobs


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
