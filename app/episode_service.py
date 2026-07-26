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
STEPS = ["script", "evaluate", "voices", "cinematic"]


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

    # --- 2. editorial evaluation ------------------------------------------
    handle.step("evaluate", "Evaluating the episode script")
    story_service.evaluate_episode(series_id, number)

    if handle.cancelled():
        return {"cancelled": True, "step": "evaluate"}

    # --- 3. voices (the slow part: one TTS call per line) ------------------
    handle.step("voices", "Voicing the lines")

    def on_line(done: int, total: int) -> None:
        if handle.cancelled():
            raise InterruptedError("episode generation cancelled")
        handle.progress(done, total, f"Voicing line {done} of {total}")

    try:
        manifest = audio_nodes.render_episode_audio(
            state, number, progress=on_line,
        )
    except InterruptedError:
        return {"cancelled": True, "step": "voices"}
    state.setdefault("audio_manifest", {})[str(number)] = manifest

    if handle.cancelled():
        return {"cancelled": True, "step": "voices"}

    # --- 4. cinematic direction + final mix -------------------------------
    handle.step("cinematic", "Directing and mixing the cinematic episode")
    plan = audio_nodes.design_episode_sound(state, number)
    state.setdefault("sound_plans", {})[str(number)] = plan
    handle.progress(1, 2, "Rendering and mastering the cinematic mix")

    if handle.cancelled():
        return {"cancelled": True, "step": "cinematic"}

    final = audio_nodes.mix_episode(state, number)
    handle.progress(2, 2, "Cinematic episode ready")

    if handle.cancelled():
        return {"cancelled": True, "step": "cinematic"}

    store.save_index(series_id, stage="episode_ready")
    return {
        "number": number,
        "lines": len(lines),
        "music_cues": len(plan.get("music", [])),
        "sfx_cues": len(plan.get("sfx", [])),
        "duration_ms": final.get("total_ms"),
        "final": final.get("final"),
        "status": store.episode_status(series_id, number),
    }


def start_episode_job(series_id: str, number: int, *, force_script: bool = False) -> dict:
    """Start (or rejoin) a generation job for this episode."""
    return jobs.start_or_rejoin(
        "episode",
        lambda h: generate_episode(series_id, number, h, force_script=force_script),
        dedupe_key=("episode", series_id, number),
        series_id=series_id, number=number, steps=STEPS,
    )


def remix_episode(series_id: str, number: int, instruction: str,
                  handle: jobs.JobHandle) -> dict[str, Any]:
    """Redesign and mix against existing immutable speech takes; never call TTS."""
    state = _state_for(series_id)
    if number not in store.episode_numbers(series_id):
        raise ValueError(f"episode {number} is not in the plan")
    info = state.get("audio_manifest", {}).get(str(number), {})
    if not info.get("voices") or not info.get("line_files"):
        raise ValueError("render episode voices before requesting a remix")

    direction = instruction.strip()
    if not direction:
        raise ValueError("audio direction cannot be empty")
    state["feedback"] = direction

    handle.step("sound", "Applying the new audio direction")
    plan = audio_nodes.design_episode_sound(state, number)
    state.setdefault("sound_plans", {})[str(number)] = plan
    if handle.cancelled():
        return {"cancelled": True, "step": "sound"}

    handle.step("mix", "Remixing existing dialogue, music, and effects")
    final = audio_nodes.mix_episode(state, number)
    final = {**info, **final, "remix_revision": store._now()}
    store.save_episode_audio(series_id, number, final)
    if handle.cancelled():
        return {"cancelled": True, "step": "mix"}

    store.save_index(series_id, stage="episode_ready")
    return {
        "number": number, "status": store.episode_status(series_id, number),
        "final": final.get("final"), "remix_revision": final["remix_revision"],
    }


def start_episode_remix_job(series_id: str, number: int,
                            instruction: str) -> dict[str, Any]:
    return jobs.start_or_rejoin(
        "episode_remix",
        lambda h: remix_episode(series_id, number, instruction, h),
        dedupe_key=("episode_remix", series_id, number),
        series_id=series_id, number=number, steps=["sound", "mix"],
    )
