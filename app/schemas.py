"""Pydantic schemas for every node's structured LLM output.

These are the *contracts* between the LLM and the pipeline. Each node asks the
model to fill exactly one of these, and the result is validated before it ever
touches the graph state.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Stage 1 — Extract & Confirm
# ---------------------------------------------------------------------------
class DetectedCharacter(BaseModel):
    name: str
    role: str = Field(description="e.g. protagonist, antagonist, mentor, love interest")
    description: str = Field(description="one or two sentences on who they are")


class ExtractResult(BaseModel):
    genre: str
    theme: str
    tone: str
    language: str
    setting: str = Field(description="time period + place the story lives in")
    logline: str = Field(description="one-sentence summary of the whole series")
    characters: list[DetectedCharacter] = Field(
        description="every character the idea implies; count is inferred, not fixed"
    )


# ---------------------------------------------------------------------------
# Stage 2 — Clarification (max 5 questions)
# ---------------------------------------------------------------------------
class ClarifyOption(BaseModel):
    label: str = Field(description="short option label, e.g. 'A. Born Different'")
    detail: str = Field(description="1-2 sentence explanation of this option")


class ClarifyQuestion(BaseModel):
    question: str
    options: list[ClarifyOption] = Field(
        default_factory=list,
        description="multiple-choice options; may be empty for a pure free-text question",
    )
    allow_free_text: bool = True


class ClarifyResult(BaseModel):
    questions: list[ClarifyQuestion] = Field(
        description="0 to 5 questions; return an empty list if nothing is unclear"
    )


# ---------------------------------------------------------------------------
# Stage 3 — Series Blueprint
# ---------------------------------------------------------------------------
class CharacterProfile(BaseModel):
    name: str
    role: str
    description: str
    personality: str = Field(description="core traits driving their behaviour")
    relationships: list[str] = Field(
        default_factory=list, description="ties to other characters, as short phrases"
    )
    vocal_signature: str = Field(
        description="how they sound: pace, pitch, verbal tics — guides casting & emotion"
    )
    is_narrator: bool = False


class Blueprint(BaseModel):
    logline: str
    story_world: str = Field(description="the setting/world and its rules")
    main_storyline: str = Field(description="overall plot arc of the series")
    tone: str
    theme: str
    characters: list[CharacterProfile]


# ---------------------------------------------------------------------------
# Stage 4 — Episode Config recommendation
# ---------------------------------------------------------------------------
class EpisodeConfigSuggestion(BaseModel):
    recommended_ep_count: int = Field(description="based on the depth/scope of the story")
    rationale: str


# ---------------------------------------------------------------------------
# Stage 5 — Episode Plan
# ---------------------------------------------------------------------------
class EpisodePlanItem(BaseModel):
    number: int
    title: str
    summary: str
    main_events: list[str]
    emotional_focus: str = Field(description="the dominant feeling this episode drives")
    cliffhanger: str = Field(description="the hook that ends the episode")


class EpisodePlan(BaseModel):
    episodes: list[EpisodePlanItem]


# ---------------------------------------------------------------------------
# Stage 6 — Script (per episode)
# ---------------------------------------------------------------------------
class ScriptLine(BaseModel):
    type: Literal["narration", "dialogue"]
    speaker: str = Field(description="character name, or 'Narrator' for narration")
    text: str = Field(
        description="the spoken line; may contain an inline [Emotion] tag ONLY where "
                    "the emotion genuinely peaks/shifts — most lines carry no tag"
    )
    sfx: list[str] = Field(
        default_factory=list,
        description="optional SFX keyword hints for this line; usually empty",
    )
    music: Optional[str] = Field(
        default=None,
        description="optional mood keyword if a music bed should (re)start here; usually null",
    )


class EpisodeScript(BaseModel):
    lines: list[ScriptLine]


# ---------------------------------------------------------------------------
# Stage 7 — Voice casting suggestions
# ---------------------------------------------------------------------------
class VoiceAssignment(BaseModel):
    character: str
    voice_id: str = Field(description="must be one of the provided Gemini voice names")
    reason: str


class VoiceCastSuggestion(BaseModel):
    assignments: list[VoiceAssignment]


# ---------------------------------------------------------------------------
# Stage 9 — Sound design cues (refined against the real asset manifest)
# ---------------------------------------------------------------------------
class MusicCue(BaseModel):
    start_line: int = Field(description="0-based index of the line where this bed starts")
    end_line: int = Field(description="0-based index of the line where this bed ends")
    mood: str = Field(description="must be an allowed music mood key from the manifest")


class SfxCue(BaseModel):
    line: int = Field(description="0-based index of the line the effect lands on")
    name: str = Field(description="must be an allowed sfx key from the manifest")


class SoundPlan(BaseModel):
    music: list[MusicCue] = Field(
        default_factory=list, description="sparse; silence is fine — omit when unneeded"
    )
    sfx: list[SfxCue] = Field(
        default_factory=list, description="only for concrete, script-mentioned events"
    )
