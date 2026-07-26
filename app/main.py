"""FastAPI backend driving the LangGraph pipeline through its review interrupts.

Flow: POST /series submits the idea and runs to the first interrupt. The client
then repeatedly approves / edits / regenerates each stage until the pipeline
reaches `deliver`. Continuation adds a new plain-text plot and re-runs.
"""
from __future__ import annotations

import uuid
import logging
import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from langgraph.types import Command
from pydantic import BaseModel, Field

from . import config, jobs, store
from .api_store import router as store_router
from .graph import GRAPH
from .state import new_state

app = FastAPI(title="AI Creator Copilot", version="0.1.0")
_LOG = logging.getLogger(__name__)

# The React frontend runs on its own dev-server origin, so the browser sends a
# preflight before every POST. Without this the whole API is unreachable from it.
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Store-backed routes (/studio/*): the frontend reads and writes the series
# folder through these, independently of the pipeline's in-memory state.
app.include_router(store_router)


@app.middleware("http")
async def request_observability(request: Request, call_next):
    """Attach a correlation id and timing without logging creator content."""
    request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        _LOG.exception("request_failed id=%s method=%s path=%s", request_id,
                       request.method, request.url.path)
        raise
    response.headers["X-Request-ID"] = request_id
    _LOG.info("request_completed id=%s method=%s path=%s status=%s duration_ms=%.1f",
              request_id, request.method, request.url.path, response.status_code,
              (time.perf_counter() - started) * 1000)
    return response


# --------------------------------------------------------------------------- #
# request models
# --------------------------------------------------------------------------- #
class NewSeries(BaseModel):
    idea: str = Field(min_length=1, max_length=config.MAX_IDEA_CHARS)
    title: str | None = None
    transcript: str | None = None   # set when the idea came from a recording


class Command_(BaseModel):
    action: str = "approve"                 # approve | edit | submit | regenerate
    note: str = ""                          # guidance for regenerate
    data: dict[str, Any] | None = None      # edited fields / submitted answers


class ContinuePlot(BaseModel):
    plot: str = Field(min_length=1, max_length=config.MAX_IDEA_CHARS)


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _cfg(series_id: str) -> dict:
    return {"configurable": {"thread_id": series_id}}


def _pending(series_id: str, result: dict) -> dict:
    """Shape the response: either a review request or a completion."""
    interrupts = result.get("__interrupt__")
    if interrupts:
        payload = interrupts[0].value
        return {"series_id": series_id, "status": "awaiting_review", **payload}
    return {
        "series_id": series_id, "status": "done",
        "stage": result.get("stage"),
        "audio_manifest": result.get("audio_manifest", {}),
    }


def _run(series_id: str, inp: Any) -> dict:
    result = GRAPH.invoke(inp, _cfg(series_id))
    return _pending(series_id, result)


def _snapshot(series_id: str) -> dict:
    """In-memory graph state, falling back to the folder on disk.

    The checkpointer is in-process, so after a restart the graph knows nothing —
    but the series folder still does. Hydrating from disk keeps reads working.
    """
    snap = GRAPH.get_state(_cfg(series_id))
    if snap.values:
        return snap.values
    if store.series_dir(series_id).exists():
        return store.hydrate(series_id)
    raise HTTPException(404, f"unknown series {series_id}")


# --------------------------------------------------------------------------- #
# routes
# --------------------------------------------------------------------------- #
@app.post("/series")
def create_series(body: NewSeries) -> dict:
    series_id = uuid.uuid4().hex[:12]
    # Seed the folder before the first LLM call so the series exists on disk
    # even if generation fails partway.
    store.save_idea(series_id, body.idea, transcript=body.transcript)
    store.save_index(series_id, title=body.title or "", stage="extract",
                     source="audio" if body.transcript else "text")
    return _run(series_id, new_state(series_id, body.idea))


@app.get("/series/{series_id}/state")
def get_state(series_id: str) -> dict:
    values = _snapshot(series_id)
    snap = GRAPH.get_state(_cfg(series_id))
    pending = snap.tasks and any(t.interrupts for t in snap.tasks)
    return {
        "series_id": series_id,
        "stage": values.get("stage"),
        "approvals": values.get("approvals", {}),
        "awaiting_review": bool(pending),
        "state": values,
    }


def _resume(series_id: str, cmd: Command_) -> dict:
    _snapshot(series_id)  # 404 if unknown
    # Creator-supplied data arrives with the command rather than from a node, so
    # persist the pieces the folder owns before handing back to the graph.
    data = cmd.data or {}
    if "clarification_answers" in data:
        store.save_clarification_answers(series_id, data["clarification_answers"])
    if "voice_cast" in data:
        store.save_voice_cast(series_id, data["voice_cast"])
    for ep in data.get("episodes", []) or []:
        store.save_episode_outline(series_id, ep)
    for num, lines in (data.get("scripts") or {}).items():
        store.save_episode_script(series_id, int(num), lines)

    payload = {"action": cmd.action, "note": cmd.note, "data": cmd.data}
    return _run(series_id, Command(resume=payload))


@app.post("/series/{series_id}/approve")
def approve(series_id: str, cmd: Command_ | None = None) -> dict:
    return _resume(series_id, cmd or Command_(action="approve"))


@app.post("/series/{series_id}/edit")
def edit(series_id: str, cmd: Command_) -> dict:
    cmd.action = "edit"
    return _resume(series_id, cmd)


@app.post("/series/{series_id}/submit")
def submit(series_id: str, cmd: Command_) -> dict:
    cmd.action = "submit"
    return _resume(series_id, cmd)


@app.post("/series/{series_id}/regenerate")
def regenerate(series_id: str, cmd: Command_) -> dict:
    cmd.action = "regenerate"
    return _resume(series_id, cmd)


@app.post("/series/{series_id}/continue")
def continue_story(series_id: str, body: ContinuePlot) -> dict:
    """Append a new plot and re-run planning → production with full prior context."""
    values = _snapshot(series_id)
    arcs = list(values.get("arcs", [])) + [body.plot]
    # Re-enter at the blueprint node so the story + characters update for the new
    # plot, then flow through planning → production again with full prior context.
    update = {"arcs": arcs, "feedback": "", "approvals": {}}
    return _run(series_id, Command(goto="gen_blueprint", update=update))


@app.get("/series/{series_id}/episodes/{number}/audio")
def get_episode_audio(series_id: str, number: int) -> FileResponse:
    values = _snapshot(series_id)
    info = values.get("audio_manifest", {}).get(str(number), {})
    path = info.get("final") or info.get("voices")
    if not path or not Path(path).exists():
        raise HTTPException(404, "audio not generated yet")
    return FileResponse(path, media_type="audio/wav",
                        filename=f"{series_id}_ep{number:02d}.wav")


@app.get("/health")
def health() -> dict:
    return {
        "ok": True,
        "text_models": {
            "hard": config.TEXT_MODEL_HARD,
            "easy": config.TEXT_MODEL_EASY,
        },
        "text_call_routes": config.TEXT_TASKS,
        "model_cache": {
            "enabled": config.MODEL_CACHE_ENABLED,
            "ttl_seconds": config.MODEL_CACHE_TTL_SEC,
            "version": config.MODEL_CACHE_VERSION,
        },
        "transcription_model": config.TRANSCRIPTION_MODEL,
        "tts_model": config.TTS_MODEL,
        "jobs": jobs.summary(),
    }
