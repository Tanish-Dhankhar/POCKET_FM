"""LangGraph state — the single object that flows through the whole pipeline.

Nodes return partial dicts that LangGraph merges into this state; the
checkpointer persists it per thread (series_id), which is also our continuity /
"remember everything" store.
"""
from __future__ import annotations

from typing import Any, TypedDict


class SeriesState(TypedDict, total=False):
    series_id: str

    # Stage 0 — the only required input
    idea: str
    include_narrator: bool

    # Stage 1 — extracted then confirmed
    genre: str
    theme: str
    tone: str
    language: str
    setting: str
    logline: str
    characters: list[dict[str, Any]]        # CharacterProfile-shaped dicts

    # Stage 2
    clarification: dict[str, Any]           # {questions: [...]} as generated
    clarification_answers: list[dict]       # creator's answers

    # Stage 3
    blueprint: dict[str, Any]

    # Stage 4
    recommended_ep_count: int
    ep_count: int
    ep_minutes: int

    # Stage 5
    episodes: list[dict[str, Any]]          # EpisodePlanItem-shaped dicts

    # Stage 6 — scripts keyed by episode number (as str for JSON safety)
    scripts: dict[str, list[dict[str, Any]]]

    # Stage 7
    voice_cast: dict[str, str]              # character name -> voice id

    # Stage 9
    sound_plans: dict[str, dict[str, Any]]  # ep number -> SoundPlan dict

    # Continuation
    arcs: list[str]                         # each appended plain-text plot

    # Bookkeeping / human-in-the-loop control
    stage: str                              # current pipeline stage
    approvals: dict[str, bool]              # stage -> approved?
    feedback: str                           # latest regenerate/edit note
    command: dict[str, Any]                 # last human command payload
    ui: dict[str, Any]                      # transient display extras for review
    audio_manifest: dict[str, Any]          # ep number -> rendered file paths


# Ordered pipeline stages (used for routing + progress display).
STAGES = [
    "extract",
    "clarify",
    "blueprint",
    "ep_config",
    "episode_plan",
    "script",
    "voice_cast",
    "audio",
    "sound_design",
    "mix",
    "deliver",
]


def new_state(series_id: str, idea: str) -> SeriesState:
    """Fresh state for a brand-new series."""
    return SeriesState(
        series_id=series_id,
        idea=idea,
        language="",
        characters=[],
        clarification={},
        clarification_answers=[],
        episodes=[],
        scripts={},
        voice_cast={},
        sound_plans={},
        arcs=[],
        stage="extract",
        approvals={},
        feedback="",
        command={},
        ui={},
        audio_manifest={},
    )
