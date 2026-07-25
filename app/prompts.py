"""Prompt builders for every text-generation node.

Each function returns the full user prompt string. Craft rules (Pocket-FM
serialized format, sparse emotion, restrained sound) live here so the pipeline
code stays about orchestration.
"""
from __future__ import annotations

import json
from typing import Any

from . import config

SYSTEM = (
    "You are an expert showrunner and audio-drama writer for a Pocket-FM-style "
    "serialized fiction platform. You write for the ear: natural spoken rhythm, "
    "distinct character voices, strong hooks, and emotionally-driven cliffhangers. "
    "You always respond with valid JSON matching the requested schema."
)


def _feedback_block(feedback: str) -> str:
    if not feedback.strip():
        return ""
    return (
        "\n\nThe creator asked you to REGENERATE with this guidance — honour it:\n"
        f"\"{feedback.strip()}\"\n"
    )


# ---------------------------------------------------------------------------
# Stage 1 — Extract
# ---------------------------------------------------------------------------
def extract(idea: str, feedback: str = "") -> str:
    return (
        "Read the creator's story idea and extract its metadata.\n\n"
        "Infer the FULL cast of characters the idea implies — do not force a fixed "
        "number; some ideas have two characters, some have ten. Give each a name "
        "(invent fitting ones if unnamed), a role, and a short description.\n\n"
        f"STORY IDEA:\n\"\"\"\n{idea.strip()}\n\"\"\""
        + _feedback_block(feedback)
    )


# ---------------------------------------------------------------------------
# Stage 2 — Clarify
# ---------------------------------------------------------------------------
def clarify(idea: str, extracted: dict[str, Any], feedback: str = "") -> str:
    return (
        "Based on the story idea and extracted metadata, decide what is genuinely "
        "unclear or missing before you could write a great series.\n\n"
        "Ask AT MOST 5 questions. Ask FEWER (even zero) if the idea is already clear. "
        "Each question should offer 2-4 concrete multiple-choice options (with a short "
        "explanation each) AND allow free text. Options should be meaningfully different "
        "creative directions, not trivia.\n\n"
        f"STORY IDEA:\n\"\"\"\n{idea.strip()}\n\"\"\"\n\n"
        f"EXTRACTED METADATA:\n{json.dumps(extracted, indent=2)}"
        + _feedback_block(feedback)
    )


# ---------------------------------------------------------------------------
# Stage 3 — Blueprint
# ---------------------------------------------------------------------------
def blueprint(idea: str, extracted: dict[str, Any], answers: list[dict],
              arcs: list[str] | None = None, feedback: str = "") -> str:
    arcs_block = ""
    if arcs:
        joined = "\n\n".join(f"- {a}" for a in arcs)
        arcs_block = (
            "\n\nCONTINUATION PLOTS the creator later added — UPDATE the storyline and "
            "ADD any new characters these introduce, while keeping the same theme and "
            "existing characters/relationships consistent:\n" + joined
        )
    return (
        "Write the complete SERIES BLUEPRINT — the foundation for the whole show.\n\n"
        "Include: a sharp logline, the story world and its rules, the overall main "
        "storyline (with the potential to run for many episodes), the tone and theme, "
        "and a full character roster. For every character give personality, "
        "relationships, and a distinct VOCAL SIGNATURE (pace, pitch, verbal tics) so "
        "voices are instantly distinguishable in audio. Mark exactly one character as "
        "the narrator ONLY if the story benefits from narration.\n\n"
        f"STORY IDEA:\n\"\"\"\n{idea.strip()}\n\"\"\"\n\n"
        f"EXTRACTED METADATA:\n{json.dumps(extracted, indent=2)}\n\n"
        f"CREATOR'S CLARIFICATION ANSWERS:\n{json.dumps(answers, indent=2)}"
        + arcs_block
        + _feedback_block(feedback)
    )


# ---------------------------------------------------------------------------
# Stage 4 — Episode config recommendation
# ---------------------------------------------------------------------------
def ep_config(blueprint: dict[str, Any], feedback: str = "") -> str:
    return (
        "Given this series blueprint, recommend how many episodes the FIRST season "
        "should have, based on the depth and scope of the story. Prefer a focused "
        "season (typically 6-12) that can each end on a strong cliffhanger. Explain "
        "your reasoning briefly.\n\n"
        f"BLUEPRINT:\n{json.dumps(blueprint, indent=2)}"
        + _feedback_block(feedback)
    )


# ---------------------------------------------------------------------------
# Stage 5 — Episode plan
# ---------------------------------------------------------------------------
def episode_plan(blueprint: dict[str, Any], ep_count: int, ep_minutes: int,
                 prior_recap: str = "", feedback: str = "") -> str:
    recap = (
        f"\n\nPRIOR EPISODES (for continuity — do not repeat them):\n{prior_recap}"
        if prior_recap else ""
    )
    return (
        f"Divide the story into exactly {ep_count} episodes of about {ep_minutes} "
        "minutes each. For every episode give: number, title, summary, the main events, "
        "the dominant emotional focus, and an ending cliffhanger.\n\n"
        "Rules: the first 3 episodes are critical — front-load the strongest, most "
        "engaging material. EVERY episode must end on an emotionally-driven cliffhanger "
        "calibrated to the protagonist's state (not a mechanical shock). Keep the plot "
        "progressing so it stays binge-able.\n\n"
        f"BLUEPRINT:\n{json.dumps(blueprint, indent=2)}"
        + recap
        + _feedback_block(feedback)
    )


# ---------------------------------------------------------------------------
# Stage 6 — Script
# ---------------------------------------------------------------------------
def script(blueprint: dict[str, Any], episode: dict[str, Any],
           prior_recap: str = "", feedback: str = "") -> str:
    tag_list = ", ".join(f"[{t}]" for t in config.EMOTION_TAGS)
    recap = f"\n\nSTORY SO FAR (for continuity):\n{prior_recap}" if prior_recap else ""
    return (
        "Write the full SCRIPT for this episode as an ordered list of lines.\n\n"
        "Each line is either 'narration' (speaker 'Narrator') or 'dialogue' (speaker = "
        "a character name). Write for the ear: natural, spoken, short beats, rising "
        "tension. Keep 2-4 speaking characters in any given scene. Open with a hook in "
        "the first moments and land the episode's cliffhanger at the end.\n\n"
        "EMOTION — use SPARINGLY. Put an inline emotion tag at the START of a line's "
        "text ONLY when the emotion genuinely peaks or changes (a reveal, threat, "
        "breakdown). Most lines should have NO tag and read in a natural voice. Aim for "
        "at most roughly one tagged line in every three or four. Allowed tags only: "
        f"{tag_list}. You may also use [pause].\n\n"
        "SOUND — keep it sparse. Leave 'sfx' as [] and 'music' as null for most lines. "
        "Only add an sfx hint for a concrete event the text mentions (thunder, door, "
        "footsteps). Only set 'music' (a mood word) on the FIRST line of a scene whose "
        "mood clearly calls for a bed. Silence is good.\n\n"
        f"BLUEPRINT:\n{json.dumps(blueprint, indent=2)}\n\n"
        f"THIS EPISODE:\n{json.dumps(episode, indent=2)}"
        + recap
        + _feedback_block(feedback)
    )


# ---------------------------------------------------------------------------
# Stage 7 — Voice casting suggestion
# ---------------------------------------------------------------------------
def voice_cast(characters: list[dict[str, Any]], feedback: str = "") -> str:
    catalogue = "\n".join(f"- {name}: {style}" for name, style in config.VOICES.items())
    return (
        "Assign each character (including the Narrator if present) a DISTINCT voice "
        "from the catalogue below, matching each character's vocal signature and "
        "personality. Never reuse a voice for two characters if avoidable. Return the "
        "chosen voice_id (exactly as listed) and a short reason per character.\n\n"
        f"VOICE CATALOGUE (name: style):\n{catalogue}\n\n"
        f"CHARACTERS:\n{json.dumps(characters, indent=2)}"
        + _feedback_block(feedback)
    )


# ---------------------------------------------------------------------------
# Stage 9 — Sound design
# ---------------------------------------------------------------------------
def sound_design(episode_lines: list[dict[str, Any]],
                 music_moods: list[str], sfx_keys: list[str],
                 feedback: str = "") -> str:
    numbered = "\n".join(
        f"{i}: ({ln.get('type')}) {ln.get('speaker')}: {ln.get('text')}"
        for i, ln in enumerate(episode_lines)
    )
    return (
        "Design SPARSE, tasteful sound for this episode. You choose optional music "
        "beds (each spanning a line range) and optional one-shot SFX (each on a single "
        "line).\n\n"
        "Hard rules:\n"
        "- Silence is the default. Many scenes need NO music. Do not blanket the "
        "episode.\n"
        "- Music only on a clear mood scene; keep beds few and let them span whole "
        "scenes, not single lines.\n"
        "- SFX only for concrete events the line text actually mentions.\n"
        "- Use ONLY these music moods: " + ", ".join(music_moods) + "\n"
        "- Use ONLY these sfx keys: " + ", ".join(sfx_keys) + "\n\n"
        f"EPISODE LINES (index: (type) speaker: text):\n{numbered}"
        + _feedback_block(feedback)
    )
