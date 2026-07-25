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
    n = config.CLARIFY_QUESTION_COUNT
    return (
        f"Ask the creator EXACTLY {n} questions that will most improve the series.\n\n"
        "Rules:\n"
        f"- Exactly {n} questions. Not fewer, not more.\n"
        "- Each question must be SPECIFIC to this story — name its characters, setting, or "
        "premise. Never ask something already answered by the metadata below (don't ask "
        "'what genre?' — the genre is already known).\n"
        "- Ask about the things that genuinely change how the series is written: the "
        "protagonist's motivation, the nature of the central mystery/conflict, what the "
        "antagonist wants, the ending's direction, a key relationship, the level of "
        "supernatural vs grounded, the stakes.\n"
        "- Give each question 3-4 options that are meaningfully DIFFERENT creative "
        "directions (not shades of the same answer). Each option needs a short concrete "
        "`label` and a one-line `detail` describing what it would mean for the story.\n"
        "- Mark EXACTLY ONE option per question as recommended=true — the one that would "
        "make the strongest, most engaging series. All others must be recommended=false.\n"
        "- Set allow_free_text to true for every question.\n\n"
        f"STORY IDEA:\n\"\"\"\n{idea.strip()}\n\"\"\"\n\n"
        f"ALREADY KNOWN (do not ask about these):\n{json.dumps(extracted, indent=2)}"
        + _feedback_block(feedback)
    )


def confirm_card(idea: str, extracted: dict[str, Any], answers: list[dict]) -> str:
    """Cheap pre-blueprint summary for the wizard's confirm step."""
    return (
        "Summarise this story into the few decisions a creator confirms before we "
        "write the series.\n\n"
        "Give it a short evocative TITLE (2-5 words) that suits the genre — this is "
        "the name the series will be known by, so make it memorable, not descriptive. "
        "Say whether the story genuinely benefits from a NARRATOR voice (true only if "
        "it needs scene-setting or interior perspective that dialogue can't carry). "
        "Recommend a focused first-season episode count and an average episode length "
        "in minutes (5-15). Generate exactly four short GENRE TAGS and exactly four "
        "short THEME TAGS grounded in this specific story. Avoid generic filler.\n\n"
        f"STORY IDEA:\n\"\"\"\n{idea.strip()}\n\"\"\"\n\n"
        f"EXTRACTED METADATA:\n{json.dumps(extracted, indent=2)}\n\n"
        f"CREATOR'S ANSWERS:\n{json.dumps(answers, indent=2)}"
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
        "storyline, 3-6 major story beats (with the potential to run for many episodes), "
        "the tone and theme, "
        "and a full character roster. For every character give personality, useful "
        "details, physical persona, backstory, relationships, and a distinct VOCAL "
        "SIGNATURE and VOCAL DIRECTION (pace, pitch, verbal tics) so "
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
           prior_recap: str = "", feedback: str = "",
           include_narrator: bool | None = None) -> str:
    tag_list = ", ".join(f"[{t}]" for t in config.EMOTION_TAGS)
    recap = f"\n\nSTORY SO FAR (for continuity):\n{prior_recap}" if prior_recap else ""
    narrator_rule = (
        "NARRATOR: Do not write narration lines. The creator explicitly chose no "
        "narrator; carry scene-setting through natural dialogue and sparse sound hints.\n\n"
        if include_narrator is False else
        "NARRATOR: Use narration only when it materially improves clarity or pacing.\n\n"
    )
    return (
        "Write the full SCRIPT for this episode as an ordered list of lines.\n\n"
        "Each line is either 'narration' (speaker 'Narrator') or 'dialogue' (speaker = "
        "a character name). Write for the ear: natural, spoken, short beats, rising "
        "tension. Keep 2-4 speaking characters in any given scene. Open with a hook in "
        "the first moments and land the episode's cliffhanger at the end.\n\n"
        + narrator_rule +
        "EMOTION — use SPARINGLY. Store delivery direction in the separate `emotion` "
        "field and keep `text` free of inline emotion prefixes. Use emotion=null for "
        "natural delivery. Only set it when delivery differs materially from the "
        "speaker's established voice, and never repeat it mechanically on adjacent "
        f"lines. Allowed values only: {tag_list}. Use [pause] within text only for an "
        "intentional silence, never as a default emotion.\n\n"
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


def story_analysis(blueprint: dict[str, Any], genre_tags: list[str],
                   theme_tags: list[str], instruction: str = "") -> str:
    return (
        "Analyse this audio-series blueprint for its creator Ideaboard. Return a "
        "concise literary SWOT with 2-4 points in each quadrant. Strengths and "
        "weaknesses are qualities of the current story; opportunities are promising "
        "directions; threats are risks such as repetition, unclear rules, or weak "
        "audio-only comprehension.\n\n"
        "Classify the genre across exactly these seven categories: action, drama, "
        "comedy, sci_fi, horror, thriller, romance. Values should total roughly 100. "
        "Return exactly four genre tags and exactly four weighted theme tags; theme "
        "percentages should also total roughly 100. Preserve creator-confirmed tags "
        "when they fit the blueprint.\n\n"
        f"CONFIRMED GENRE TAGS: {json.dumps(genre_tags)}\n"
        f"CONFIRMED THEME TAGS: {json.dumps(theme_tags)}\n"
        f"BLUEPRINT:\n{json.dumps(blueprint, indent=2)}"
        + _feedback_block(instruction)
    )


def episode_evaluation(blueprint: dict[str, Any], outline: dict[str, Any],
                       script_lines: list[dict[str, Any]]) -> str:
    return (
        "Act as a concise audio-fiction script evaluator. Return 3-6 actionable points. "
        "Cover the opening hook, distinct character voices, pacing and repetition, "
        "emotional escalation, clarity without visuals, and cliffhanger strength where "
        "relevant. For every point provide a short category, an honest assessment, and "
        "one concrete suggestion. Do not praise generically or rewrite the script.\n\n"
        f"SERIES BLUEPRINT:\n{json.dumps(blueprint, indent=2)}\n\n"
        f"EPISODE OUTLINE:\n{json.dumps(outline, indent=2)}\n\n"
        f"SCRIPT:\n{json.dumps(script_lines, indent=2)}"
    )
