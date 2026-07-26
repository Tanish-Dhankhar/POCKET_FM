"""Text-pipeline generation nodes.

Each function is a pure generator: it reads the state, calls the LLM, and returns
a partial state update. Human-in-the-loop review/routing is handled separately in
graph.py so that resuming after an interrupt never re-runs generation.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Any

from .. import config, image_service, prompts, schemas, store
from ..llm import generate_structured
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

    # Both calls depend only on the initial idea, so run them concurrently.  The
    # first call returns all four questions in the same structured response as
    # the provisional extraction; the second preloads the later confirm card.
    with ThreadPoolExecutor(max_workers=2, thread_name_prefix="wizard-llm") as pool:
        bootstrap_future = pool.submit(
            generate_structured,
            prompts.extract(state["idea"], state.get("feedback", "")),
            schemas.ExtractResult,
            task="wizard_bootstrap",
            system=prompts.SYSTEM,
        )
        confirm_future = pool.submit(
            generate_structured,
            prompts.confirm_card(state["idea"], state.get("feedback", "")),
            schemas.ConfirmCard,
            task="confirm_card",
            system=prompts.SYSTEM,
        )
        res = bootstrap_future.result()
        card = confirm_future.result().model_dump()

    clarification = _normalise_clarify({"questions": [q.model_dump() for q in res.questions]})
    store.save_clarification(sid, clarification)
    store.save_confirmation_draft(sid, card)
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
    return {**out, "clarification": clarification, "confirmation_draft": card}


# --------------------------------------------------------------------------- #
# Stage 2 — Clarify
# --------------------------------------------------------------------------- #
def _normalise_clarify(clarification: dict[str, Any]) -> dict[str, Any]:
    """Guarantee the UI's invariants regardless of what the model returned.

    The schema already pins the count, but a guard here means a misbehaving model
    can never break the wizard's fixed N-step flow:
      - exactly CLARIFY_QUESTION_COUNT questions (trim, or pad with a generic one)
      - every question has exactly three options and allows free text
      - exactly one option per question is `recommended`
    """
    n = config.CLARIFY_QUESTION_COUNT
    questions = list(clarification.get("questions") or [])[:n]

    while len(questions) < n:
        questions.append({
            "question": "Anything else we should know before writing this series?",
            "options": [
                {"label": "Keep it as described", "detail": "Stay close to the idea.",
                 "recommended": True},
                {"label": "Surprise me", "detail": "Take a bolder creative swing.",
                 "recommended": False},
                {"label": "Raise the stakes", "detail": "Make the consequences sharper.",
                 "recommended": False},
            ],
            "allow_free_text": True,
        })

    for q in questions:
        q["allow_free_text"] = True
        options = list(q.get("options") or [])[:3]
        defaults = [
                {"label": "Keep it as described", "detail": "Stay close to the idea.",
                 "recommended": True},
                {"label": "Surprise me", "detail": "Take a bolder creative swing.",
                 "recommended": False},
                {"label": "Raise the stakes", "detail": "Make the consequences sharper.",
                 "recommended": False},
        ]
        while len(options) < 3:
            options.append(defaults[len(options)])
        # exactly one recommended: keep the first flagged, else default to the first
        flagged = [i for i, o in enumerate(options) if o.get("recommended")]
        winner = flagged[0] if flagged else 0
        for i, o in enumerate(options):
            o["recommended"] = (i == winner)
        q["options"] = options

    return {"questions": questions}


def gen_clarify(state: SeriesState) -> dict[str, Any]:
    # Normal wizard progression reuses the questions generated in gen_extract;
    # only an explicit regenerate action spends another model call.
    if state.get("clarification") and not state.get("feedback", "").strip():
        return {"clarification": state["clarification"], "stage": "clarify"}
    res = generate_structured(
        prompts.clarify(state["idea"], _extracted(state), state.get("feedback", "")),
        schemas.ClarifyResult, task="clarify_regeneration", system=prompts.SYSTEM,
    )
    clarification = _normalise_clarify(res.model_dump())
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
        schemas.Blueprint, task="blueprint", system=prompts.SYSTEM,
    )
    sid = state["series_id"]
    characters = [c.model_dump() for c in bp.characters]
    # Answers may have arrived with the approve command — persist them too.
    store.save_clarification_answers(sid, state.get("clarification_answers", []))
    blueprint = bp.model_dump()
    authoritative_meta = {
        "genre": bp.genre, "genre_tags": bp.genre_tags,
        "theme": bp.theme, "theme_tags": bp.theme_tags,
        "tone": bp.tone, "language": bp.language,
        "setting": bp.setting, "logline": bp.logline,
    }
    store.save_blueprint(sid, blueprint, meta=authoritative_meta)
    draft = store.load_confirmation_draft(sid)
    if draft:
        draft.update({
            "genre": bp.genre, "setting": bp.setting,
            "genre_tags": bp.genre_tags, "theme_tags": bp.theme_tags,
        })
        store.save_confirmation_draft(sid, draft)
    store.save_index(sid, stage="blueprint", arcs=state.get("arcs", []))
    # plot.json and the character files (with their physical descriptions) now
    # exist, which is everything the artwork needs. Runs in the background — the
    # graph never waits on it, and it no-ops when images are disabled.
    image_service.start_images_job(sid)
    return {

        "blueprint": blueprint,
        # blueprint is now the authoritative character source
        "characters": characters,
        **authoritative_meta,
        "stage": "blueprint",
    }


# --------------------------------------------------------------------------- #
# Stage 4 — Episode config recommendation
# --------------------------------------------------------------------------- #
def gen_ep_config(state: SeriesState) -> dict[str, Any]:
    if state.get("ep_count"):
        return {
            "recommended_ep_count": int(state["ep_count"]),
            "ui": {"ep_config_rationale": "Creator already confirmed the season length."},
            "stage": "ep_config",
        }
    sug = generate_structured(
        prompts.ep_config(state["blueprint"], state.get("feedback", "")),
        schemas.EpisodeConfigSuggestion, task="episode_config", system=prompts.SYSTEM,
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
        schemas.EpisodePlan, task="episode_plan", system=prompts.SYSTEM,
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
                          state.get("feedback", ""),
                          state.get("include_narrator"), state.get("ep_minutes")),
            schemas.EpisodeScript, task="episode_script", system=prompts.SYSTEM,
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
                      state.get("feedback", ""),
                      state.get("include_narrator"), state.get("ep_minutes")),
        schemas.EpisodeScript, task="episode_script", system=prompts.SYSTEM,
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
        schemas.VoiceCastSuggestion, task="voice_cast", system=prompts.SYSTEM,
    )
    cast = {a.character: a.voice_id for a in sug.assignments}
    reasons = {a.character: a.reason for a in sug.assignments}
    # Voice choice is stored on each character file so per-character edits persist.
    store.save_voice_cast(state["series_id"], cast)
    store.save_index(state["series_id"], stage="voice_cast")
    return {"voice_cast": cast, "ui": {"voice_reasons": reasons}, "stage": "voice_cast"}
