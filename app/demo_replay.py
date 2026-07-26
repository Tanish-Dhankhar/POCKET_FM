"""Deterministic, model-free replay of the presentation series.

The replay deliberately mirrors the normal wizard's review stages while cloning
already-generated artifacts from ``the-thursday-lie-demo``. It is keyed to a
narrow demo prompt so ordinary creator ideas continue through LangGraph/LLMs.
"""
from __future__ import annotations

import re
import shutil
import time
from pathlib import Path
from typing import Any

from . import config, store


TEMPLATE_SERIES_ID = "the-thursday-lie-demo"
CANONICAL_IDEA = (
    "A wife discovers her husband's affair during their anniversary dinner "
    "and follows the evidence into a larger financial betrayal."
)

QUESTIONS = {
    "questions": [
        {
            "question": "How should Maya discover Daniel's affair during the anniversary dinner?",
            "options": [
                {"label": "Hotel key and voice note", "detail": "Physical evidence and Celeste's voice make denial impossible.", "recommended": True},
                {"label": "A message on his phone", "detail": "A quieter, familiar digital discovery.", "recommended": False},
                {"label": "Celeste arrives", "detail": "A more public and explosive confrontation.", "recommended": False},
            ],
            "allow_free_text": True,
        },
        {
            "question": "What dramatic tone should define the fight?",
            "options": [
                {"label": "Grounded and intimate", "detail": "Natural dialogue, restrained music, and painful specificity.", "recommended": True},
                {"label": "Explosive melodrama", "detail": "Bigger accusations and heightened reversals.", "recommended": False},
                {"label": "Cold psychological duel", "detail": "Controlled voices and almost no visible emotion.", "recommended": False},
            ],
            "allow_free_text": True,
        },
        {
            "question": "How should Daniel be treated after the affair is exposed?",
            "options": [
                {"label": "Accountable, not redeemed", "detail": "He can explain himself without escaping consequences.", "recommended": True},
                {"label": "Immediate reconciliation", "detail": "The marriage begins healing in Episode 1.", "recommended": False},
                {"label": "Irredeemable villain", "detail": "Remove ambiguity and make revenge the engine.", "recommended": False},
            ],
            "allow_free_text": True,
        },
        {
            "question": "Where should Maya's season arc ultimately lead?",
            "options": [
                {"label": "Self-trust and separation", "detail": "She chooses restitution and a future of her own.", "recommended": True},
                {"label": "Winning Daniel back", "detail": "Romantic reunion becomes the final goal.", "recommended": False},
                {"label": "Destroying both lovers", "detail": "The season becomes a revenge thriller.", "recommended": False},
            ],
            "allow_free_text": True,
        },
    ]
}

CONFIRM_CARD = {
    "title": "The Thursday Lie",
    "genre": "Intimate Relationship Mystery",
    "setting": "A rain-soaked city apartment and the evidence trail beyond it",
    "narrator_suggested": False,
    "recommended_ep_count": 8,
    "recommended_ep_minutes": 5,
    "genre_tags": ["Relationship Drama", "Domestic Mystery", "Romance", "Psychological"],
    "theme_tags": ["Betrayal and Truth", "Self-Trust", "Accountability", "Letting Go"],
}

_STAGES = ("extract", "clarify", "blueprint", "ep_config", "episode_plan")


def _normalise(value: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", value.casefold()).split())


def matches(idea: str) -> bool:
    if not config.DEMO_REPLAY_ENABLED:
        return False
    normal = _normalise(idea)
    if normal == _normalise(CANONICAL_IDEA):
        return True
    # Also accept the verbose presentation brief used to create this asset,
    # without hijacking ordinary infidelity story ideas.
    return all(fragment in normal for fragment in (
        "husband", "cheat", "emotional fight", "20 dialogue", "enough",
    ))


def _state_path(series_id: str):
    return store.input_dir(series_id) / "demo_replay.json"


def is_replay(series_id: str) -> bool:
    return bool((store.read_json(_state_path(series_id), {}) or {}).get("enabled"))


def current_stage(series_id: str) -> str:
    state = store.read_json(_state_path(series_id), {}) or {}
    return str(state.get("stage") or "extract")


def _save_stage(series_id: str, stage: str) -> None:
    store.write_json(_state_path(series_id), {
        "enabled": True,
        "template_series_id": TEMPLATE_SERIES_ID,
        "stage": stage,
        "model_calls": 0,
        "revealed_episodes": [],
    })
    store.save_index(series_id, stage=stage, demo_replay=True,
                     demo_template=TEMPLATE_SERIES_ID)


def _rewrite(value: Any, old_root: str, new_root: str,
             old_id: str, new_id: str) -> Any:
    if isinstance(value, dict):
        return {key: _rewrite(item, old_root, new_root, old_id, new_id)
                for key, item in value.items()}
    if isinstance(value, list):
        return [_rewrite(item, old_root, new_root, old_id, new_id) for item in value]
    if isinstance(value, str):
        # Cache folders may be moved between machines or test output roots.
        # Re-anchor every absolute asset path at the newly cloned series folder
        # instead of merely swapping the series id inside a stale old root.
        candidate = Path(value)
        if candidate.is_absolute() and old_id in candidate.parts:
            position = candidate.parts.index(old_id)
            return str(Path(new_root, *candidate.parts[position + 1:]))
        return value.replace(old_root, new_root).replace(old_id, new_id)
    return value


def seed(series_id: str, idea: str, *, transcript: str | None = None) -> None:
    source = store.series_dir(TEMPLATE_SERIES_ID).resolve()
    target = store.series_dir(series_id).resolve()
    if not source.is_dir():
        raise RuntimeError(
            f"demo template '{TEMPLATE_SERIES_ID}' is missing; run its renderer first"
        )
    if target.exists():
        raise RuntimeError(f"refusing to overwrite existing series '{series_id}'")
    shutil.copytree(source, target)
    old_root, new_root = str(source), str(target)
    for path in target.rglob("*.json"):
        payload = store.read_json(path, None)
        if payload is not None:
            store.write_json(path, _rewrite(
                payload, old_root, new_root, TEMPLATE_SERIES_ID, series_id,
            ))
    store.save_idea(series_id, idea, transcript=transcript)
    store.save_clarification(series_id, QUESTIONS)
    store.save_confirmation_draft(series_id, CONFIRM_CARD)
    _save_stage(series_id, "extract")


def _extract_payload(series_id: str) -> dict[str, Any]:
    bp = store.load_blueprint(series_id)
    return {
        "genre": bp.get("genre", ""),
        "theme": bp.get("theme", ""),
        "tone": bp.get("tone", ""),
        "language": bp.get("language", "English"),
        "setting": bp.get("setting", ""),
        "logline": bp.get("logline", ""),
        "characters": bp.get("characters", []),
    }


def _payload(series_id: str, stage: str) -> dict[str, Any]:
    if stage == "extract":
        return _extract_payload(series_id)
    if stage == "clarify":
        return QUESTIONS
    if stage == "blueprint":
        bp = store.load_blueprint(series_id)
        # Story-analysis files store weighted theme objects for charts, while
        # the wizard's confirmation inputs require plain editable tag strings.
        bp["genre_tags"] = list(CONFIRM_CARD["genre_tags"])
        bp["theme_tags"] = list(CONFIRM_CARD["theme_tags"])
        return {"blueprint": bp, "characters": bp.get("characters", [])}
    if stage == "ep_config":
        return {
            "recommended_ep_count": 8,
            "rationale": "Eight focused episodes let each piece of evidence change the relationship.",
            "minutes_bounds": [5, 15],
        }
    return {
        "episodes": store.load_outlines(series_id),
        "ep_count": 8,
        "ep_minutes": 5,
    }


def response(series_id: str, stage: str | None = None) -> dict[str, Any]:
    selected = stage or current_stage(series_id)
    return {
        "series_id": series_id,
        "status": "awaiting_review",
        "stage": selected,
        "payload": _payload(series_id, selected),
        "demo_replay": True,
        "model_calls": 0,
    }


def resume(series_id: str, action: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
    stage = current_stage(series_id)
    if action == "regenerate":
        time.sleep(config.DEMO_REPLAY_STEP_DELAY_SEC)
        return response(series_id, stage)
    if stage == "clarify" and data and "clarification_answers" in data:
        store.save_clarification_answers(series_id, data["clarification_answers"])
    index = _STAGES.index(stage)
    next_stage = _STAGES[min(index + 1, len(_STAGES) - 1)]
    _save_stage(series_id, next_stage)
    time.sleep(config.DEMO_REPLAY_STEP_DELAY_SEC)
    return response(series_id, next_stage)


def complete(series_id: str) -> None:
    store.write_json(_state_path(series_id), {
        "enabled": True,
        "template_series_id": TEMPLATE_SERIES_ID,
        "stage": "episode_ready",
        "model_calls": 0,
        "revealed_episodes": [],
    })
    store.save_index(series_id, stage="episode_ready", demo_replay=True,
                     demo_template=TEMPLATE_SERIES_ID)


def episode_is_revealed(series_id: str, number: int) -> bool:
    state = store.read_json(_state_path(series_id), {}) or {}
    return int(number) in {int(item) for item in state.get("revealed_episodes", [])}


def reveal_episode(series_id: str, number: int) -> None:
    state = store.read_json(_state_path(series_id), {}) or {}
    revealed = {int(item) for item in state.get("revealed_episodes", [])}
    revealed.add(int(number))
    state.update({
        "enabled": True,
        "template_series_id": TEMPLATE_SERIES_ID,
        "stage": "episode_ready",
        "model_calls": 0,
        "revealed_episodes": sorted(revealed),
    })
    store.write_json(_state_path(series_id), state)
    store.save_index(series_id, stage="episode_ready", demo_replay=True,
                     demo_template=TEMPLATE_SERIES_ID)
