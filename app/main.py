"""FastAPI backend driving the LangGraph pipeline through its review interrupts.

Flow: POST /series submits the idea and runs to the first interrupt. The client
then repeatedly approves / edits / regenerates each stage until the pipeline
reaches `deliver`. Continuation adds a new plain-text plot and re-runs.
"""
from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from langgraph.types import Command
from pydantic import BaseModel

from . import config
from .graph import GRAPH
from .state import new_state

app = FastAPI(title="AI Creator Copilot", version="0.1.0")


# --------------------------------------------------------------------------- #
# request models
# --------------------------------------------------------------------------- #
class NewSeries(BaseModel):
    idea: str


class Command_(BaseModel):
    action: str = "approve"                 # approve | edit | submit | regenerate
    note: str = ""                          # guidance for regenerate
    data: dict[str, Any] | None = None      # edited fields / submitted answers


class ContinuePlot(BaseModel):
    plot: str


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
    snap = GRAPH.get_state(_cfg(series_id))
    if not snap.values:
        raise HTTPException(404, f"unknown series {series_id}")
    return snap.values


# --------------------------------------------------------------------------- #
# routes
# --------------------------------------------------------------------------- #
@app.post("/series")
def create_series(body: NewSeries) -> dict:
    series_id = uuid.uuid4().hex[:12]
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
    return {"ok": True, "text_model": config.TEXT_MODEL, "tts_model": config.TTS_MODEL}
