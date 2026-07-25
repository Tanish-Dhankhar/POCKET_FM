"""Text-pipeline generation nodes.

Each function is a pure generator: it reads the state, calls the LLM, and returns
a partial state update. Human-in-the-loop review/routing is handled separately in
graph.py so that resuming after an interrupt never re-runs generation.
"""
from __future__ import annotations

from typing import Any

from .. import prompts, schemas, store
from ..llm import generate_structured
from ..config import THINK_HIGH, THINK_LOW
from ..state import SeriesState


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _extracted(state: SeriesState) -> dict[str, Any]:
    """The confirmed Stage-1 metadata bundle, fed into later prompts."""
    return {
        "genre": state.get("genre", ""),
        "theme": state.get("theme", ""),
        "tone": state.get("tone", ""),
        "language": state.get("language", ""),
        "setting": state.get("setting", ""),
        "logline": state.get("logline", ""),
        "characters": state.get("characters", []),
    }


def _recap_before(state: SeriesState, number: int) -> str:
    """Continuity recap: summaries of every planned episode before `number`."""
    lines = []
    for ep in state.get("episodes", []):
        if ep.get("number", 0) < number:
            lines.append(f"Ep {ep['number']} — {ep.get('title','')}: {ep.get('summary','')}")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Stage 1 — Extract
# --------------------------------------------------------------------------- #
def gen_extract(state: SeriesState) -> dict[str, Any]:
    sid = state["series_id"]
    store.save_idea(sid, state["idea"])
    res = generate_structured(
        prompts.extract(state["idea"], state.get("feedback", "")),
        schemas.ExtractResult, thinking=THINK_HIGH, system=prompts.SYSTEM,
    )
    out = {
        "genre": res.genre, "theme": res.theme, "tone": res.tone,
        "language": res.language, "setting": res.setting, "logline": res.logline,
        "characters": [c.model_dump() for c in res.characters],
        "stage": "extract",
    }
    # Persist the extracted metadata immediately so the folder is authoritative.
    store.save_blueprint(sid, {"logline": res.logline, "theme": res.theme,
                               "tone": res.tone, "characters": out["characters"]},
                         meta=out)
    store.save_index(sid, title=state.get("title") or res.logline[:60],
                     genre=res.genre, stage="extract")
    return out


# --------------------------------------------------------------------------- #
# Stage 2 — Clarify
# --------------------------------------------------------------------------- #
def gen_clarify(state: SeriesState) -> dict[str, Any]:
    res = generate_structured(
        prompts.clarify(state["idea"], _extracted(state), state.get("feedback", "")),
        schemas.ClarifyResult, thinking=THINK_HIGH, system=prompts.SYSTEM,
    )
    clarification = res.model_dump()
    store.save_clarification(state["series_id"], clarification)
    return {"clarification": clarification, "stage": "clarify"}


# --------------------------------------------------------------------------- #
# Stage 3 — Blueprint
# --------------------------------------------------------------------------- #
def gen_blueprint(state: SeriesState) -> dict[str, Any]:
    bp = generate_structured(
        prompts.blueprint(
            state["idea"], _extracted(state),
            state.get("clarification_answers", []),
            state.get("arcs", []), state.get("feedback", ""),
        ),
        schemas.Blueprint, thinking=THINK_HIGH, system=prompts.SYSTEM,
    )
    sid = state["series_id"]
    characters = [c.model_dump() for c in bp.characters]
    # Answers may have arrived with the approve command — persist them too.
    store.save_clarification_answers(sid, state.get("clarification_answers", []))
    store.save_blueprint(sid, bp.model_dump(), meta=_extracted(state))
    store.save_index(sid, stage="blueprint", arcs=state.get("arcs", []))
    return {
        "blueprint": bp.model_dump(),
        # blueprint is now the authoritative character source
        "characters": characters,
        "stage": "blueprint",
    }


# --------------------------------------------------------------------------- #
# Stage 4 — Episode config recommendation
# --------------------------------------------------------------------------- #
def gen_ep_config(state: SeriesState) -> dict[str, Any]:
    sug = generate_structured(
        prompts.ep_config(state["blueprint"], state.get("feedback", "")),
        schemas.EpisodeConfigSuggestion, thinking=THINK_HIGH, system=prompts.SYSTEM,
    )
    return {
        "recommended_ep_count": sug.recommended_ep_count,
        "ui": {"ep_config_rationale": sug.rationale},
        "stage": "ep_config",
    }


# --------------------------------------------------------------------------- #
# Stage 5 — Episode plan
# --------------------------------------------------------------------------- #
def gen_episode_plan(state: SeriesState) -> dict[str, Any]:
    ep_count = state.get("ep_count") or state.get("recommended_ep_count", 6)
    ep_minutes = state.get("ep_minutes", 10)
    prior = "\n".join(state.get("arcs", []))  # continuation context, if any
    plan = generate_structured(
        prompts.episode_plan(state["blueprint"], ep_count, ep_minutes, prior,
                             state.get("feedback", "")),
        schemas.EpisodePlan, thinking=THINK_HIGH, system=prompts.SYSTEM,
    )
    sid = state["series_id"]
    episodes = [e.model_dump() for e in plan.episodes]
    # One folder per episode, each with its own outline.json.
    for ep in episodes:
        store.save_episode_outline(sid, ep)
    store.save_index(sid, stage="episode_plan", ep_count=ep_count, ep_minutes=ep_minutes)
    return {
        "episodes": episodes,
        "ep_count": ep_count, "ep_minutes": ep_minutes,
        "stage": "episode_plan",
    }


# --------------------------------------------------------------------------- #
# Stage 6 — Scripts (all episodes)
# --------------------------------------------------------------------------- #
def gen_script(state: SeriesState) -> dict[str, Any]:
    sid = state["series_id"]
    scripts: dict[str, list[dict[str, Any]]] = dict(state.get("scripts", {}))
    for ep in state.get("episodes", []):
        num = ep["number"]
        sc = generate_structured(
            prompts.script(state["blueprint"], ep, _recap_before(state, num),
                          state.get("feedback", "")),
            schemas.EpisodeScript, thinking=THINK_HIGH, system=prompts.SYSTEM,
        )
        lines = [ln.model_dump() for ln in sc.lines]
        scripts[str(num)] = lines
        store.save_episode_script(sid, num, lines)
    store.save_index(sid, stage="script")
    return {"scripts": scripts, "stage": "script"}


# --------------------------------------------------------------------------- #
# Single-episode script (used by the per-episode generate endpoint)
# --------------------------------------------------------------------------- #
def gen_script_for_episode(state: SeriesState, number: int) -> list[dict[str, Any]]:
    """Generate + persist the script for ONE episode, and return its lines."""
    ep = next((e for e in state.get("episodes", []) if e.get("number") == number), None)
    if ep is None:
        raise ValueError(f"episode {number} is not in the plan")
    sc = generate_structured(
        prompts.script(state["blueprint"], ep, _recap_before(state, number),
                      state.get("feedback", "")),
        schemas.EpisodeScript, thinking=THINK_HIGH, system=prompts.SYSTEM,
    )
    lines = [ln.model_dump() for ln in sc.lines]
    store.save_episode_script(state["series_id"], number, lines)
    return lines


# --------------------------------------------------------------------------- #
# Stage 7 — Voice casting suggestion
# --------------------------------------------------------------------------- #
def gen_voice_cast(state: SeriesState) -> dict[str, Any]:
    sug = generate_structured(
        prompts.voice_cast(state.get("characters", []), state.get("feedback", "")),
        schemas.VoiceCastSuggestion, thinking=THINK_LOW, system=prompts.SYSTEM,
    )
    cast = {a.character: a.voice_id for a in sug.assignments}
    reasons = {a.character: a.reason for a in sug.assignments}
    # Voice choice is stored on each character file so per-character edits persist.
    store.save_voice_cast(state["series_id"], cast)
    store.save_index(state["series_id"], stage="voice_cast")
    return {"voice_cast": cast, "ui": {"voice_reasons": reasons}, "stage": "voice_cast"}
