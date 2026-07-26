"""Long-running story analysis, refinement, and episode evaluation jobs."""
from __future__ import annotations

import hashlib
import json
from typing import Any

from . import config, jobs, prompts, schemas, store
from .llm import generate_structured


def _analysis_input(series_id: str) -> tuple[dict[str, Any], list[str], list[str]]:
    bp = store.load_blueprint(series_id)
    inp = store.load_input(series_id)
    confirmed = inp.get("confirmations", {})
    blueprint = {
        "logline": bp.get("logline", ""),
        "story_world": bp.get("story_world", ""),
        "main_storyline": bp.get("main_storyline", ""),
        "story_beats": bp.get("story_beats", []),
        "theme": bp.get("theme", ""),
        "tone": bp.get("tone", ""),
        "genre": bp.get("genre", ""),
        "setting": bp.get("setting", ""),
        "characters": bp.get("characters", []),
    }
    genre_tags = list(confirmed.get("genre_tags") or bp.get("genre_data", {}).get("tags") or [])[:4]
    theme_raw = confirmed.get("theme_tags") or bp.get("theme_data", {}).get("tags") or []
    theme_tags = [row.get("label", "") if isinstance(row, dict) else str(row) for row in theme_raw][:4]
    return blueprint, genre_tags, theme_tags


def generate_analysis(series_id: str, instruction: str = "") -> dict[str, Any]:
    blueprint, genre_tags, theme_tags = _analysis_input(series_id)
    result = generate_structured(
        prompts.story_analysis(blueprint, genre_tags, theme_tags, instruction),
        schemas.StoryAnalysis,
        thinking=config.THINK_HIGH,
        system=prompts.SYSTEM,
    )
    return store.save_story_analysis(series_id, result.model_dump())


def start_analysis_job(series_id: str, instruction: str = "") -> dict[str, Any]:
    existing = jobs.find_active("analysis", series_id=series_id)
    if existing:
        return existing

    def worker(handle: jobs.JobHandle) -> dict[str, Any]:
        handle.step("analysis", "Analysing story, genres, and themes")
        result = generate_analysis(series_id, instruction)
        handle.progress(1, 1, "Analysis ready")
        return {"series_id": series_id, "analysis": result}

    job_id = jobs.start("analysis", worker, series_id=series_id, steps=["analysis"])
    return jobs.get(job_id) or {"id": job_id}


def _emotional_curve_input(series_id: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    bp = store.load_blueprint(series_id)
    blueprint = {
        "genre": bp.get("genre", ""),
        "theme": bp.get("theme", ""),
        "main_storyline": bp.get("main_storyline", ""),
    }
    episodes = [
        {
            "number": outline.get("number"),
            "title": outline.get("title", ""),
            "summary": outline.get("summary", ""),
            "emotional_focus": outline.get("emotional_focus", ""),
            "cliffhanger": outline.get("cliffhanger", ""),
        }
        for outline in store.load_outlines(series_id)
    ]
    return blueprint, episodes


def generate_emotional_curve(series_id: str, instruction: str = "") -> dict[str, Any]:
    blueprint, episodes = _emotional_curve_input(series_id)
    if not episodes:
        raise ValueError("generate the episode plan before building an emotional curve")
    result = generate_structured(
        prompts.emotional_curve(blueprint, episodes, instruction),
        schemas.EmotionCurve,
        thinking=config.THINK_HIGH,
        system=prompts.SYSTEM,
    )
    return store.save_emotional_curve(series_id, result.model_dump(), episodes)


def start_emotional_curve_job(series_id: str, instruction: str = "") -> dict[str, Any]:
    existing = jobs.find_active("emotional_curve", series_id=series_id)
    if existing:
        return existing

    def worker(handle: jobs.JobHandle) -> dict[str, Any]:
        handle.step("emotional_curve", "Charting the emotional arc across episodes")
        result = generate_emotional_curve(series_id, instruction)
        handle.progress(1, 1, "Emotional curve ready")
        return {"series_id": series_id, "emotional_curve": result}

    job_id = jobs.start("emotional_curve", worker, series_id=series_id,
                        steps=["emotional_curve"])
    return jobs.get(job_id) or {"id": job_id}


def _script_hash(lines: list[dict[str, Any]]) -> str:
    payload = json.dumps(lines, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def evaluate_episode(series_id: str, number: int) -> dict[str, Any]:
    state = store.hydrate(series_id)
    episode = store.load_episode(series_id, number)
    lines = episode.get("script", [])
    if not lines:
        raise ValueError("generate or write the episode script before evaluating it")
    result = generate_structured(
        prompts.episode_evaluation(state.get("blueprint", {}), episode.get("outline", {}), lines),
        schemas.EpisodeEvaluation,
        thinking=config.THINK_LOW,
        system=prompts.SYSTEM,
    ).model_dump()
    result.update({
        "script_hash": _script_hash(lines),
        "generated_at": store._now(),
        "stale": False,
    })
    store.save_episode_evaluation(series_id, number, result)
    return result


def refine_series(series_id: str, instruction: str, handle: jobs.JobHandle) -> dict[str, Any]:
    state = store.hydrate(series_id)
    card = store.load_index(series_id)
    old_characters = {store.slug(ch.get("name", "")): ch for ch in state.get("characters", [])}
    revision = int(card.get("revision", 1) or 1) + 1
    store.append_refinement(series_id, instruction, status="running", revision=revision)

    handle.step("blueprint", "Applying your refinement to the story")
    extracted = {
        "genre": state.get("genre", ""), "theme": state.get("theme", ""),
        "tone": state.get("tone", ""), "language": state.get("language", ""),
        "setting": state.get("setting", ""), "logline": state.get("logline", ""),
        "characters": state.get("characters", []),
    }
    arcs = list(state.get("arcs", [])) + [instruction]
    bp = generate_structured(
        prompts.blueprint(state.get("idea", ""), extracted,
                          state.get("clarification_answers", []), arcs, instruction),
        schemas.Blueprint,
        thinking=config.THINK_HIGH,
        system=prompts.SYSTEM,
    ).model_dump()
    for character in bp.get("characters", []):
        previous = old_characters.get(store.slug(character.get("name", "")), {})
        if previous:
            character["id"] = previous.get("id", character.get("id", ""))
            if previous.get("voice_id"):
                character["voice_id"] = previous["voice_id"]
            if previous.get("portrait_generated_at"):
                # Keep the cached image servable, but the persona may have
                # shifted — flag it so the Ideaboard offers a re-render.
                character["portrait_generated_at"] = previous["portrait_generated_at"]
                character["portrait_stale"] = True
    store.save_blueprint(series_id, bp, meta=extracted)
    store.save_index(series_id, stage="refining", revision=revision, arcs=arcs)

    handle.step("analysis", "Rebalancing story analysis")
    generate_analysis(series_id, instruction)

    handle.step("episodes", "Replanning affected episodes")
    count = int(card.get("ep_count") or len(state.get("episodes", [])) or 6)
    minutes = int(card.get("ep_minutes") or 10)
    plan = generate_structured(
        prompts.episode_plan(bp, count, minutes, "", instruction),
        schemas.EpisodePlan,
        thinking=config.THINK_HIGH,
        system=prompts.SYSTEM,
    )
    episodes = [item.model_dump() for item in plan.episodes]
    for outline in episodes:
        outline["source_revision"] = revision
        store.save_episode_outline(series_id, outline)
        existing = store.load_episode(series_id, int(outline["number"]))
        audio = existing.get("audio", {})
        if audio:
            audio["stale"] = True
            audio["stale_reason"] = "Story refined"
            store.save_episode_audio(series_id, int(outline["number"]), audio)
        evaluation = existing.get("evaluation", {})
        if evaluation:
            evaluation["stale"] = True
            store.save_episode_evaluation(series_id, int(outline["number"]), evaluation)
    store.save_index(series_id, stage="episode_plan", revision=revision, arcs=arcs)

    handle.step("emotional_curve", "Recharting the emotional arc")
    generate_emotional_curve(series_id, instruction)

    store.append_refinement(series_id, instruction, status="complete", revision=revision)
    return {"series_id": series_id, "revision": revision, "episodes": len(episodes)}


def start_refinement_job(series_id: str, instruction: str) -> dict[str, Any]:
    existing = jobs.find_active("refinement", series_id=series_id)
    if existing:
        return existing
    job_id = jobs.start(
        "refinement",
        lambda handle: refine_series(series_id, instruction, handle),
        series_id=series_id,
        steps=["blueprint", "analysis", "episodes", "emotional_curve"],
    )
    return jobs.get(job_id) or {"id": job_id}
