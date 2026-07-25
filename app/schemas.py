"""Pydantic schemas for every node's structured LLM output.

These are the *contracts* between the LLM and the pipeline. Each node asks the
model to fill exactly one of these, and the result is validated before it ever
touches the graph state.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

from .config import CLARIFY_QUESTION_COUNT


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
# Stage 2 — Clarification (ALWAYS exactly 4 questions, each with options)
# ---------------------------------------------------------------------------
class ClarifyOption(BaseModel):
    label: str = Field(description="the choice itself, a short concrete phrase")
    detail: str = Field(description="one line on what picking this would mean for the story")
    recommended: bool = Field(
        default=False,
        description="exactly ONE option per question must be true — the strongest choice",
    )


class ClarifyQuestion(BaseModel):
    question: str = Field(
        description="specific to THIS story — name its characters, setting, premise"
    )
    options: list[ClarifyOption] = Field(
        min_length=2, max_length=4,
        description="3-4 meaningfully different creative directions",
    )
    allow_free_text: bool = True


class ClarifyResult(BaseModel):
    questions: list[ClarifyQuestion] = Field(
        min_length=CLARIFY_QUESTION_COUNT, max_length=CLARIFY_QUESTION_COUNT,
        description=f"exactly {CLARIFY_QUESTION_COUNT} questions",
    )


# ---------------------------------------------------------------------------
# Confirm card — one cheap call so the wizard can show a title + recommended
# episode count BEFORE the blueprint exists (ep_config only runs after it).
# ---------------------------------------------------------------------------
class ConfirmCard(BaseModel):
    title: str = Field(description="a short, evocative series title — 2-5 words, no quotes")
    genre: str
    setting: str = Field(description="time period + place, in a few words")
    narrator_suggested: bool = Field(
        description="true if this story genuinely benefits from a narrator voice"
    )
    recommended_ep_count: int = Field(
        ge=1, le=30, description="focused first season, typically 6-12"
    )
    recommended_ep_minutes: int = Field(
        ge=5, le=15, description="average episode length in minutes"
    )
    genre_tags: list[str] = Field(min_length=4, max_length=4)
    theme_tags: list[str] = Field(min_length=4, max_length=4)


# ---------------------------------------------------------------------------
# Stage 3 — Series Blueprint
# ---------------------------------------------------------------------------
class CharacterProfile(BaseModel):
    id: str = ""
    name: str
    role: str
    gender: str = Field(default="Unspecified", description="gender identity or presentation")
    description: str
    personality: str = Field(description="core traits driving their behaviour")
    details: str = ""
    physical_persona: str = ""
    backstory: str = ""
    relationships: list[str] = Field(
        default_factory=list, description="ties to other characters, as short phrases"
    )
    vocal_signature: str = Field(
        description="how they sound: pace, pitch, verbal tics — guides casting & emotion"
    )
    vocal_direction: str = ""
    is_narrator: bool = False


class Blueprint(BaseModel):
    logline: str
    story_world: str = Field(description="the setting/world and its rules")
    main_storyline: str = Field(description="overall plot arc of the series")
    story_beats: list[str] = Field(default_factory=list, description="3-6 major series beats")
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
    id: str = ""
    type: Literal["narration", "dialogue"]
    speaker: str = Field(description="character name, or 'Narrator' for narration")
    text: str = Field(
        description="the spoken line; may contain an inline [Emotion] tag ONLY where "
                    "the emotion genuinely peaks/shifts — most lines carry no tag"
    )
    emotion: Optional[str] = None
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


class GenreDistribution(BaseModel):
    action: int = Field(ge=0, le=100)
    drama: int = Field(ge=0, le=100)
    comedy: int = Field(ge=0, le=100)
    sci_fi: int = Field(ge=0, le=100)
    horror: int = Field(ge=0, le=100)
    thriller: int = Field(ge=0, le=100)
    romance: int = Field(ge=0, le=100)


class WeightedTheme(BaseModel):
    label: str
    percentage: int = Field(ge=0, le=100)


class StoryAnalysis(BaseModel):
    strengths: list[str] = Field(min_length=2, max_length=4)
    weaknesses: list[str] = Field(min_length=2, max_length=4)
    opportunities: list[str] = Field(min_length=2, max_length=4)
    threats: list[str] = Field(min_length=2, max_length=4)
    genre_description: str
    genre_tags: list[str] = Field(min_length=4, max_length=4)
    genre_distribution: GenreDistribution
    theme_description: str
    themes: list[WeightedTheme] = Field(min_length=4, max_length=4)


class EvaluationPoint(BaseModel):
    category: str
    assessment: str
    suggestion: str


class EpisodeEvaluation(BaseModel):
    points: list[EvaluationPoint] = Field(min_length=3, max_length=6)
