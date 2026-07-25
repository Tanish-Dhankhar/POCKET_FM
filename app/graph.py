"""LangGraph wiring: generate → review (interrupt) → route, per stage.

Each stage is a (gen_X, review_X) pair. Generation lives in nodes/*; the review
node only calls interrupt() and then routes with a Command, so resuming after an
interrupt never re-runs an LLM call. A checkpointer persists state per series_id.
"""
from __future__ import annotations

from typing import Any

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import interrupt, Command

from . import config
from .nodes import text
from .nodes import audio as audio_nodes
from .state import SeriesState

# The linear chain of reviewable stages, in order.
CHAIN = [
    "extract", "clarify", "blueprint", "ep_config",
    "episode_plan", "script", "voice_cast", "audio", "sound_design", "mix",
]

# Which state keys a creator EDIT/SUBMIT payload is allowed to overwrite.
ALLOWED_EDIT_KEYS = {
    "genre", "theme", "tone", "language", "setting", "logline", "characters",
    "clarification", "clarification_answers", "blueprint",
    "recommended_ep_count", "ep_count", "ep_minutes", "episodes",
    "scripts", "voice_cast", "sound_plans",
}

# Stages that are automatic (no human gate) — audio/mix just produce artifacts.
AUTO_STAGES = {"audio", "mix"}

# Generation function for each stage.
GEN = {
    "extract": text.gen_extract,
    "clarify": text.gen_clarify,
    "blueprint": text.gen_blueprint,
    "ep_config": text.gen_ep_config,
    "episode_plan": text.gen_episode_plan,
    "script": text.gen_script,
    "voice_cast": text.gen_voice_cast,
    "audio": audio_nodes.gen_audio,
    "sound_design": audio_nodes.gen_sound_design,
    "mix": audio_nodes.gen_mix,
}


def _payload(stage: str, state: SeriesState) -> dict[str, Any]:
    """The slice of state a frontend needs to render this stage's review."""
    ui = state.get("ui", {})
    if stage == "extract":
        return {k: state.get(k) for k in
                ("genre", "theme", "tone", "language", "setting", "logline", "characters")}
    if stage == "clarify":
        return state.get("clarification", {})
    if stage == "blueprint":
        return {"blueprint": state.get("blueprint"), "characters": state.get("characters")}
    if stage == "ep_config":
        return {
            "recommended_ep_count": state.get("recommended_ep_count"),
            "rationale": ui.get("ep_config_rationale"),
            "minutes_bounds": [config.EP_MINUTES_MIN, config.EP_MINUTES_MAX],
        }
    if stage == "episode_plan":
        return {"episodes": state.get("episodes"),
                "ep_count": state.get("ep_count"), "ep_minutes": state.get("ep_minutes")}
    if stage == "script":
        return {"scripts": state.get("scripts")}
    if stage == "voice_cast":
        return {"voice_cast": state.get("voice_cast"),
                "reasons": ui.get("voice_reasons"), "voices": config.VOICES}
    if stage == "sound_design":
        return {"sound_plans": state.get("sound_plans")}
    return {}


def _make_review(stage: str, next_node: str):
    gen_node = f"gen_{stage}"

    def review(state: SeriesState) -> Command:
        # Clarify auto-skips when the model asked nothing.
        if stage == "clarify" and not state.get("clarification", {}).get("questions"):
            return Command(goto=next_node, update={"feedback": ""})

        cmd = interrupt({"stage": stage, "payload": _payload(stage, state)}) or {}
        action = cmd.get("action", "approve")

        if action == "regenerate":
            return Command(goto=gen_node,
                          update={"feedback": cmd.get("note", ""), "command": cmd})

        update: dict[str, Any] = {
            "feedback": "", "command": cmd,
            "approvals": {**state.get("approvals", {}), stage: True},
        }
        data = cmd.get("data") or {}
        update.update({k: v for k, v in data.items() if k in ALLOWED_EDIT_KEYS})
        return Command(goto=next_node, update=update)

    return review


def build_graph():
    g = StateGraph(SeriesState)

    for i, stage in enumerate(CHAIN):
        next_stage = CHAIN[i + 1] if i + 1 < len(CHAIN) else None
        next_node = f"gen_{next_stage}" if next_stage else "deliver"

        g.add_node(f"gen_{stage}", GEN[stage])
        if stage in AUTO_STAGES:
            # No human gate: generation flows straight to the next stage.
            g.add_edge(f"gen_{stage}", next_node)
        else:
            g.add_node(f"review_{stage}", _make_review(stage, next_node))
            g.add_edge(f"gen_{stage}", f"review_{stage}")

    g.add_node("deliver", audio_nodes.gen_deliver)
    g.add_edge(START, "gen_extract")
    g.add_edge("deliver", END)

    return g.compile(checkpointer=MemorySaver())


# Module-level singleton compiled graph.
GRAPH = build_graph()
