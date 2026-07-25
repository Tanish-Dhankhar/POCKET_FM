"""Central configuration: model ids, paths, and tunables.

Everything that a maintainer might want to tweak (models, audio levels, density
caps, voice catalogue) lives here so the rest of the code stays declarative.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------
# Load .env from the project root (one level above this file's package).
PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env", override=True)

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

# Origins allowed to call the API from a browser. Comma-separated override via
# CORS_ORIGINS; "*" allows any origin (fine for local dev / a hackathon demo).
CORS_ORIGINS = [
    o.strip() for o in os.environ.get("CORS_ORIGINS", "*").split(",") if o.strip()
]

# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
TEXT_MODEL = "gemini-3.1-flash-lite"
TTS_MODEL = "gemini-3.1-flash-tts-preview"

# Thinking levels per task type (Flash-Lite supports minimal/low/medium/high).
THINK_HIGH = "high"    # creative + consistency-heavy (blueprint, plan, script)
THINK_LOW = "low"      # mechanical (sound-cue tagging, extraction)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ASSETS_DIR = PROJECT_ROOT / "assets"
MUSIC_DIR = ASSETS_DIR / "music"
SFX_DIR = ASSETS_DIR / "sfx"
SOUND_MANIFEST = ASSETS_DIR / "sound_manifest.json"
OUTPUT_DIR = PROJECT_ROOT / "output"

# ---------------------------------------------------------------------------
# Audio
# ---------------------------------------------------------------------------
TTS_SAMPLE_RATE = 24_000       # Hz — Gemini TTS returns 24kHz 16-bit mono PCM
TTS_CHANNELS = 1
TTS_SAMPLE_WIDTH = 2           # bytes (16-bit)

# TTS rate limiting. Free tier allows only ~3 requests/min for the TTS model, so
# space calls out and retry on 429. Set TTS_MIN_INTERVAL_SEC=0 on a paid tier.
TTS_MIN_INTERVAL_SEC = float(os.environ.get("TTS_MIN_INTERVAL_SEC", "21"))
TTS_MAX_RETRIES = 6

PAUSE_BETWEEN_LINES_MS = 350   # natural gap when stitching dialogue lines
MUSIC_DUCK_DB = -16            # bed level under speech
SFX_GAIN_DB = -6               # one-shot SFX level relative to voice
MUSIC_FADE_MS = 1_200          # cross-fade when a music bed changes

# Restraint guardrails (enforced in sound_design / mix).
MIN_SECONDS_BETWEEN_SFX = 6.0          # ≤1 SFX per N seconds
MAX_MUSIC_COVERAGE = 0.55              # ≤55% of an episode may have a music bed
MIN_SECONDS_BETWEEN_MUSIC_CUES = 20.0  # avoid constant bed-swapping

# Episode length bounds (minutes).
EP_MINUTES_MIN = 5
EP_MINUTES_MAX = 15

# ---------------------------------------------------------------------------
# Voice catalogue (Gemini TTS prebuilt voices) with their style labels.
# Used by voice_cast to suggest a fit per character.
# ---------------------------------------------------------------------------
VOICES: dict[str, str] = {
    "Zephyr": "Bright",         "Puck": "Upbeat",
    "Charon": "Informative",    "Kore": "Firm",
    "Fenrir": "Excitable",      "Leda": "Youthful",
    "Orus": "Firm",             "Aoede": "Breezy",
    "Callirrhoe": "Easy-going", "Autonoe": "Bright",
    "Enceladus": "Breathy",     "Iapetus": "Clear",
    "Umbriel": "Easy-going",    "Algieba": "Smooth",
    "Despina": "Smooth",        "Erinome": "Clear",
    "Algenib": "Gravelly",      "Rasalgethi": "Informative",
    "Laomedeia": "Upbeat",      "Achernar": "Soft",
    "Alnilam": "Firm",          "Schedar": "Even",
    "Gacrux": "Mature",         "Pulcherrima": "Forward",
    "Achird": "Friendly",       "Zubenelgenubi": "Casual",
    "Vindemiatrix": "Gentle",   "Sadachbia": "Lively",
    "Sadaltager": "Knowledgeable", "Sulafat": "Warm",
}
VOICE_NAMES = list(VOICES.keys())

# Emotion bracket tags the TTS model performs (proven in tts.py). Kept as a
# closed set so the script generator uses a consistent vocabulary. Used sparingly.
EMOTION_TAGS = [
    "Calm", "Curious", "Whisper", "Fear", "Panic", "Anger", "Relief", "Joy",
    "Sad", "Excited", "Nervous", "Serious", "Sarcastic", "Tender", "Shouting",
    "Trembling", "Pleading", "Cold", "Amused", "Determined",
]

DEFAULT_LANGUAGE = "English"

# Clarification: always exactly this many questions, each with options and one
# option flagged `recommended`. Fixed (not "up to N") so the wizard can render a
# deterministic N-step flow.
CLARIFY_QUESTION_COUNT = 4
