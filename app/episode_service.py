"""Per-episode generation service: script -> audio -> sound design -> mix.

The wizard stops the LangGraph at `episode_plan`. Everything after that runs here,
one episode at a time, on demand — which is what the ideaboard's per-episode
Generate button needs, and what keeps the free-tier TTS quota survivable.

Each step persists its own artifact via app/store.py, so a crash mid-run leaves a
partially-built episode that the UI can still read (and a re-run resumes cheaply,
because TTS clips are content-hash cached).
"""
from __future__ import annotations

from typing import Any

from . import jobs, store, story_service
from .nodes import audio as audio_nodes
from .nodes import text as text_nodes

# Weight of each step, used only to render a coherent overall progress bar.
STEPS = ["script", "voices", "sound", "mix", "evaluate"]


def _state_for(series_id: str) -> dict[str, Any]:
    """Pipeline-shaped state rebuilt from the folder on disk."""
    state = store.hydrate(series_id)
    if not state.get("blueprint", {}).get("main_storyline"):
        raise ValueError("this series has no blueprint yet")
    if not state.get("episodes"):
        raise ValueError("this series has no episode plan yet")
    return state


def generate_episode(series_id: str, number: int, handle: jobs.JobHandle,
                     *, force_script: bool = False) -> dict[str, Any]:
    """Run the full production chain for ONE episode. Returns a summary dict."""
    state = _state_for(series_id)
    if number not in store.episode_numbers(series_id):
        raise ValueError(f"episode {number} is not in the plan")

    # --- 1. script ---------------------------------------------------------
    existing = state.get("scripts", {}).get(str(number))
    if existing and not force_script:
        handle.step("script", "Using the existing script")
        lines = existing
    else:
        handle.step("script", "Writing the script")
        lines = text_nodes.gen_script_for_episode(state, number)
    state.setdefault("scripts", {})[str(number)] = lines

    if handle.cancelled():
        return {"cancelled": True, "step": "script"}

    # --- 2. voices (the slow part: one TTS call per line) ------------------
    handle.step("voices", "Voicing the lines")

    def on_line(done: int, total: int) -> None:
        handle.progress(done, total, f"Voicing line {done} of {total}")

    manifest = audio_nodes.render_episode_audio(state, number, progress=on_line)
    state.setdefault("audio_manifest", {})[str(number)] = manifest

    if handle.cancelled():
        return {"cancelled": True, "step": "voices"}

    # --- 3. sound design ---------------------------------------------------
    handle.step("sound", "Choosing music and effects")
    plan = audio_nodes.design_episode_sound(state, number)
    state.setdefault("sound_plans", {})[str(number)] = plan

    # --- 4. mix ------------------------------------------------------------
    handle.step("mix", "Mixing the episode")
    final = audio_nodes.mix_episode(state, number)

    # --- 5. evaluator ------------------------------------------------------
    handle.step("evaluate", "Evaluating hook, pacing, and cliffhanger")
    evaluation = story_service.evaluate_episode(series_id, number)

    store.save_index(series_id, stage="episode_ready")
    return {
        "number": number,
        "lines": len(lines),
        "music_cues": len(plan.get("music", [])),
        "sfx_cues": len(plan.get("sfx", [])),
        "duration_ms": final.get("total_ms"),
        "final": final.get("final"),
        "evaluation_points": len(evaluation.get("points", [])),
        "status": store.episode_status(series_id, number),
    }


def start_episode_job(series_id: str, number: int, *, force_script: bool = False) -> dict:
    """Start (or rejoin) a generation job for this episode."""
    existing = jobs.find_active("episode", series_id=series_id, number=number)
    if existing:
        return existing  # a second click rejoins rather than duplicating the work

    job_id = jobs.start(
        "episode",
        lambda h: generate_episode(series_id, number, h, force_script=force_script),
        series_id=series_id, number=number, steps=STEPS,
    )
    return jobs.get(job_id)
