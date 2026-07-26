"""Pydantic schemas for every node's structured LLM output.

These are the *contracts* between the LLM and the pipeline. Each node asks the
model to fill exactly one of these, and the result is validated before it ever
touches the graph state.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import AliasChoices, BaseModel, Field

from .config import CLARIFY_QUESTION_COUNT, PAUSE_BETWEEN_LINES_MS


# ---------------------------------------------------------------------------
# Stage 1 — Extract & Confirm
# ---------------------------------------------------------------------------
class DetectedCharacter(BaseModel):
    name: str
    role: str = Field(description="e.g. protagonist, antagonist, mentor, love interest")
    description: str = Field(description="one or two sentences on who they are")


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
        min_length=3, max_length=3,
        description="exactly 3 meaningfully different creative directions",
    )
    allow_free_text: bool = True


class ExtractResult(BaseModel):
    """One initial call returns provisional metadata and all wizard questions."""

    genre: str
    theme: str
    tone: str
    language: str
    setting: str = Field(description="time period + place the story lives in")
    logline: str = Field(description="one-sentence summary of the whole series")
    characters: list[DetectedCharacter] = Field(
        description="every character explicitly implied by the initial idea"
    )
    questions: list[ClarifyQuestion] = Field(
        default_factory=list,
        min_length=CLARIFY_QUESTION_COUNT,
        max_length=CLARIFY_QUESTION_COUNT,
        description=(
            f"exactly {CLARIFY_QUESTION_COUNT} questions, each with exactly 3 options"
        ),
    )


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
    details: str = Field(description="goals, fears, contradictions, and story function")
    physical_persona: str = Field(description="concise appearance and physical presence")
    backstory: str = Field(description="formative history relevant to the plot")
    relationships: list[str] = Field(
        default_factory=list, description="ties to other characters, as short phrases"
    )
    vocal_signature: str = Field(
        description="how they sound: pace, pitch, verbal tics — guides casting & emotion"
    )
    vocal_direction: str = Field(description="performance direction for emotional range")
    is_narrator: bool = False


class Blueprint(BaseModel):
    logline: str
    story_world: str = Field(description="the setting/world and its rules")
    main_storyline: str = Field(
        min_length=1800,
        description=(
            "detailed causal whole-series plot with setup, escalation, reversals, "
            "character consequences, climax, and resolution direction"
        )
    )
    story_beats: list[str] = Field(
        min_length=6, max_length=10,
        description="6-10 ordered major series beats",
    )
    genre: str
    genre_tags: list[str] = Field(min_length=4, max_length=4)
    tone: str
    theme: str
    theme_tags: list[str] = Field(min_length=4, max_length=4)
    setting: str = Field(description="time period and primary place")
    language: str
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


class EmotionCurvePoint(BaseModel):
    episode: int
    emotion_1: int = Field(default=0, ge=0, le=100)
    emotion_2: int = Field(default=0, ge=0, le=100)
    emotion_3: int = Field(default=0, ge=0, le=100)


class EmotionCurve(BaseModel):
    emotion_1_label: str
    emotion_2_label: str
    emotion_3_label: str
    dominant_emotion: str
    summary: str
    points: list[EmotionCurvePoint]


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
    gain_db: Optional[float] = Field(
        default=None,
        description="authored bed gain in dB; null keeps the configured legacy level",
    )
    fade_in_ms: Optional[int] = Field(
        default=None, description="optional bounded fade-in duration"
    )
    fade_out_ms: Optional[int] = Field(
        default=None, description="optional bounded fade-out duration"
    )
    duck_under_dialogue: bool = Field(
        default=True,
        description="whether dialogue should lower this bed while speech is active",
    )
    duck_db: float = Field(
        default=-10.0,
        description="additional gain reduction in dB while dialogue is active",
    )
    duck_attack_ms: int = Field(default=80, description="music-duck attack time")
    duck_hold_ms: int = Field(
        default=180, description="hold across short gaps to prevent pumping"
    )
    duck_release_ms: int = Field(default=420, description="music-duck recovery time")


class SfxCue(BaseModel):
    line: int = Field(description="0-based index of the line the effect lands on")
    name: str = Field(description="must be an allowed sfx key from the manifest")
    offset_ms: int = Field(
        default=0,
        description="bounded offset from line start; a negative value pre-rolls the event",
    )
    gain_db: Optional[float] = Field(
        default=None,
        description="effect gain in dB; null keeps the configured legacy level",
    )
    pan: float = Field(default=0.0, description="stereo position from -1 (left) to +1 (right)")


class DialogueEdit(BaseModel):
    """Non-destructive editorial choices for one rendered speech line."""

    line: int = Field(description="0-based script-line index")
    pause_before_ms: int = Field(
        default=0, description="silence or room-tone beat immediately before this line"
    )
    pause_after_ms: int = Field(
        default=PAUSE_BETWEEN_LINES_MS,
        description="turn-taking beat immediately after this line",
    )
    rate: float = Field(
        default=1.0,
        description="playback tempo multiplier; 1.0 preserves the generated take",
    )
    gain_db: float = Field(default=0.0, description="non-destructive clip gain in dB")
    trim_tail_ms: int = Field(
        default=0,
        description=(
            "destructively unheard tail of the immutable take; use only to make an "
            "explicit interruption cut a sentence off"
        ),
    )
    fade_in_ms: int = Field(
        default=0, description="short anti-click fade at the edited clip entrance"
    )
    fade_out_ms: int = Field(
        default=0, description="short anti-click fade at a deliberately cut clip ending"
    )
    overlap_previous_ms: int = Field(
        default=0,
        validation_alias=AliasChoices("overlap_previous_ms", "overlap_ms"),
        description="how far this line begins before the preceding speech line ends",
    )
    interrupt: bool = Field(
        default=False,
        description="intentional interruption rather than incidental crosstalk",
    )


class AmbienceCue(BaseModel):
    start_line: int = Field(description="0-based line where the ambience begins")
    end_line: int = Field(description="0-based line where the ambience ends")
    name: str = Field(description="allowed ambience/SFX asset key from the manifest")
    gain_db: float = Field(default=-24.0, description="quiet authored ambience-bed gain")
    fade_in_ms: int = Field(default=800, description="bounded fade-in duration")
    fade_out_ms: int = Field(default=800, description="bounded fade-out duration")


class SoundPlan(BaseModel):
    dialogue: list[DialogueEdit] = Field(
        default_factory=list,
        description="post-TTS timing, pace, level and overlap choices",
    )
    music: list[MusicCue] = Field(
        default_factory=list, description="sparse; silence is fine — omit when unneeded"
    )
    sfx: list[SfxCue] = Field(
        default_factory=list, description="only for concrete, script-mentioned events"
    )
    ambience: list[AmbienceCue] = Field(
        default_factory=list,
        description="optional quiet environmental beds; sparse and scene-length only",
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


# ---------------------------------------------------------------------------
# Emotional curve — top-3 tracked emotions, scored per episode
# ---------------------------------------------------------------------------
class EmotionCurvePoint(BaseModel):
    episode: int = Field(description="episode number, matching the plan")
    emotion_1: int = Field(ge=0, le=100, description="intensity of emotion_1_label in this episode")
    emotion_2: int = Field(ge=0, le=100, description="intensity of emotion_2_label in this episode")
    emotion_3: int = Field(ge=0, le=100, description="intensity of emotion_3_label in this episode")


class EmotionCurve(BaseModel):
    emotion_1_label: str = Field(description="short, story-specific emotion name, e.g. 'Tension'")
    emotion_2_label: str = Field(description="short, story-specific emotion name")
    emotion_3_label: str = Field(description="short, story-specific emotion name")
    dominant_emotion: str = Field(description="must exactly match one of the three labels above")
    summary: str = Field(description="2-3 sentences on how the emotional arc rises and falls")
    points: list[EmotionCurvePoint] = Field(
        description="one entry per episode in the plan, in episode order"
    )
