"""In-process background job runner.

Episode generation takes minutes (an LLM script pass plus one TTS call per line,
rate-limited to ~3/min on the free tier), so it cannot run inside a request. Jobs
run on a daemon thread and report progress into a dict the client polls.

Deliberately simple: single process, in memory, no persistence. The *artifacts*
are durable (every step writes to the series folder), so a lost job only means a
lost progress bar — re-running picks up cached TTS clips and is cheap.
"""
from __future__ import annotations

import threading
import traceback
import uuid
from datetime import datetime, timezone
from typing import Any, Callable

_JOBS: dict[str, dict[str, Any]] = {}
_LOCK = threading.Lock()

# Keep finished jobs around so a slow poller can still read the result.
_MAX_JOBS = 200


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _trim() -> None:
    """Drop the oldest finished jobs once the table grows too large."""
    if len(_JOBS) <= _MAX_JOBS:
        return
    finished = sorted(
        (j for j in _JOBS.values() if j["state"] in ("done", "error")),
        key=lambda j: j.get("finished_at") or "",
    )
    for job in finished[: len(_JOBS) - _MAX_JOBS]:
        _JOBS.pop(job["id"], None)


class JobHandle:
    """Passed to the worker so it can report progress."""

    def __init__(self, job_id: str) -> None:
        self.id = job_id

    def _patch(self, **fields: Any) -> None:
        with _LOCK:
            job = _JOBS.get(self.id)
            if job:
                job.update(fields)

    def step(self, name: str, message: str = "") -> None:
        """Move to a named step and reset the counter."""
        self._patch(step=name, message=message, done=0, total=0)

    def progress(self, done: int, total: int, message: str = "") -> None:
        fields: dict[str, Any] = {"done": done, "total": total}
        if message:
            fields["message"] = message
        self._patch(**fields)

    def cancelled(self) -> bool:
        with _LOCK:
            return bool(_JOBS.get(self.id, {}).get("cancel"))


def start(kind: str, fn: Callable[[JobHandle], Any], **meta: Any) -> str:
    """Run `fn(handle)` on a background thread; return the job id immediately."""
    job_id = uuid.uuid4().hex[:12]
    with _LOCK:
        _JOBS[job_id] = {
            "id": job_id, "kind": kind, "state": "queued",
            "step": "", "message": "", "done": 0, "total": 0,
            "result": None, "error": None, "cancel": False,
            "started_at": _now(), "finished_at": None, **meta,
        }
        _trim()

    handle = JobHandle(job_id)

    def run() -> None:
        handle._patch(state="running")
        try:
            result = fn(handle)
            handle._patch(state="done", result=result, finished_at=_now(),
                          message="Complete")
        except Exception as exc:  # surfaced to the client, not swallowed
            traceback.print_exc()
            handle._patch(state="error", error=f"{type(exc).__name__}: {exc}",
                          finished_at=_now(), message=str(exc))

    threading.Thread(target=run, name=f"job-{kind}-{job_id}", daemon=True).start()
    return job_id


def get(job_id: str) -> dict[str, Any] | None:
    with _LOCK:
        job = _JOBS.get(job_id)
        return dict(job) if job else None


def cancel(job_id: str) -> bool:
    """Cooperative cancel — the worker must check `handle.cancelled()`."""
    with _LOCK:
        job = _JOBS.get(job_id)
        if not job or job["state"] in ("done", "error"):
            return False
        job["cancel"] = True
        return True


def find_active(kind: str, **match: Any) -> dict[str, Any] | None:
    """Existing queued/running job matching these fields, if any.

    Used to make 'generate episode' idempotent: a second click returns the job
    already in flight instead of starting a duplicate TTS run.
    """
    with _LOCK:
        for job in _JOBS.values():
            if job["kind"] != kind or job["state"] not in ("queued", "running"):
                continue
            if all(job.get(k) == v for k, v in match.items()):
                return dict(job)
    return None
