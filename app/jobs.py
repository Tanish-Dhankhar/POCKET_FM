"""Bounded in-process job runner.

Jobs remain local to one API process until the product adopts durable queue
infrastructure. Within that boundary, this module provides admission control,
atomic de-duplication, cancellation, and a stable pollable job contract.
"""
from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
import logging
import threading
import traceback
import uuid
from datetime import datetime, timezone
from typing import Any, Callable

from . import config

_JOBS: dict[str, dict[str, Any]] = {}
_LOCK = threading.Lock()
_FUTURES: dict[str, Future[Any]] = {}
_ACTIVE_KEYS: dict[tuple[Any, ...], str] = {}
_EXECUTOR = ThreadPoolExecutor(
    max_workers=config.JOB_MAX_CONCURRENCY,
    thread_name_prefix="pocketfm-job",
)
_LOG = logging.getLogger(__name__)

# Keep finished jobs around so a slow poller can still read the result.
_MAX_JOBS = config.JOB_MAX_RETAINED


class QueueFullError(RuntimeError):
    """Raised when the local worker queue has reached its configured capacity."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _trim() -> None:
    """Drop the oldest finished jobs once the table grows too large."""
    if len(_JOBS) <= _MAX_JOBS:
        return
    finished = sorted(
        (j for j in _JOBS.values() if j["state"] in ("done", "error", "cancelled")),
        key=lambda j: j.get("finished_at") or "",
    )
    for job in finished[: len(_JOBS) - _MAX_JOBS]:
        _JOBS.pop(job["id"], None)
        _FUTURES.pop(job["id"], None)


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


def _active_count() -> int:
    return sum(j["state"] in ("queued", "running") for j in _JOBS.values())


def _active_story_count() -> int:
    """How many story-generation jobs are currently queued or running."""
    return sum(
        j["state"] in ("queued", "running") and j.get("kind") in config.STORY_JOB_KINDS
        for j in _JOBS.values()
    )


def _clear_active_key(job: dict[str, Any]) -> None:
    key = job.get("dedupe_key")
    if key and _ACTIVE_KEYS.get(key) == job["id"]:
        _ACTIVE_KEYS.pop(key, None)


def start_or_rejoin(kind: str, fn: Callable[[JobHandle], Any], *,
                    dedupe_key: tuple[Any, ...], **meta: Any) -> dict[str, Any]:
    """Atomically return an active matching job or enqueue one bounded job."""
    with _LOCK:
        existing_id = _ACTIVE_KEYS.get(dedupe_key)
        if existing_id:
            existing = _JOBS.get(existing_id)
            if existing and existing["state"] in ("queued", "running"):
                return _public_job(existing)
            _ACTIVE_KEYS.pop(dedupe_key, None)

        if _active_count() >= config.JOB_MAX_QUEUE:
            raise QueueFullError("generation queue is full; please retry shortly")

        # At most STORY_MAX_CONCURRENCY story jobs may run at once. Rejoins
        # above already returned, so this only blocks genuinely new work.
        if kind in config.STORY_JOB_KINDS and _active_story_count() >= config.STORY_MAX_CONCURRENCY:
            raise QueueFullError(
                f"at most {config.STORY_MAX_CONCURRENCY} stories can be generated at once; "
                "please retry shortly"
            )

        job_id = uuid.uuid4().hex[:12]
        _JOBS[job_id] = {
            "id": job_id, "kind": kind, "state": "queued",
            "step": "", "message": "", "done": 0, "total": 0,
            "result": None, "error": None, "cancel": False,
            "started_at": _now(), "finished_at": None,
            "dedupe_key": dedupe_key, **meta,
        }
        _ACTIVE_KEYS[dedupe_key] = job_id
        _trim()

    handle = JobHandle(job_id)

    def run() -> None:
        with _LOCK:
            job = _JOBS.get(job_id)
            if not job or job["state"] == "cancelled":
                return
            if job["cancel"]:
                job.update(state="cancelled", finished_at=_now(), message="Cancelled")
                _clear_active_key(job)
                return
            job["state"] = "running"
        _LOG.info("job_started id=%s kind=%s", job_id, kind)
        try:
            result = fn(handle)
            cancelled = bool(result and result.get("cancelled"))
            state = "cancelled" if cancelled else "done"
            message = "Cancelled" if cancelled else "Complete"
            with _LOCK:
                job = _JOBS.get(job_id)
                if job:
                    job.update(state=state, result=result, finished_at=_now(),
                               message=message)
                    _clear_active_key(job)
            _LOG.info("job_finished id=%s state=%s", job_id, state)
        except Exception as exc:  # surfaced to the client, not swallowed
            traceback.print_exc()
            with _LOCK:
                job = _JOBS.get(job_id)
                if job:
                    job.update(state="error", error=f"{type(exc).__name__}: {exc}",
                               finished_at=_now(), message=str(exc))
                    _clear_active_key(job)
            _LOG.exception("job_failed id=%s", job_id)

    future = _EXECUTOR.submit(run)
    with _LOCK:
        _FUTURES[job_id] = future
        return _public_job(_JOBS[job_id])


def get(job_id: str) -> dict[str, Any] | None:
    with _LOCK:
        job = _JOBS.get(job_id)
        return _public_job(job) if job else None


def cancel(job_id: str) -> bool:
    """Cancel queued work immediately or request cooperative running cancellation."""
    with _LOCK:
        job = _JOBS.get(job_id)
        if not job or job["state"] in ("done", "error", "cancelled"):
            return False
        job["cancel"] = True
        if job["state"] == "queued":
            future = _FUTURES.get(job_id)
            if future and future.cancel():
                job.update(state="cancelled", finished_at=_now(), message="Cancelled")
                _clear_active_key(job)
        return True


def _public_job(job: dict[str, Any]) -> dict[str, Any]:
    """Keep scheduler internals out of the public polling response."""
    return {key: value for key, value in job.items() if key != "dedupe_key"}


def summary() -> dict[str, int]:
    """Small health-safe snapshot; no job details or creator data are exposed."""
    with _LOCK:
        return {
            "queued": sum(j["state"] == "queued" for j in _JOBS.values()),
            "running": sum(j["state"] == "running" for j in _JOBS.values()),
            "story_active": _active_story_count(),
            "retained": len(_JOBS),
            "max_concurrency": config.JOB_MAX_CONCURRENCY,
            "max_story_concurrency": config.STORY_MAX_CONCURRENCY,
            "max_queue": config.JOB_MAX_QUEUE,
        }
