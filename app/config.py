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

_gemini_keys_raw = (
    os.environ.get("GEMINI_API_KEYS", "")
    or os.environ.get("GEMINI_API_KEY", "")
)
GEMINI_API_KEYS = [
    key.strip() for key in _gemini_keys_raw.split(",") if key.strip()
]
GEMINI_API_KEY = GEMINI_API_KEYS[0] if GEMINI_API_KEYS else ""
# Prefer the standard SDK variable. The fallback keeps existing local .env files
# that used the old hyphenated spelling working during the migration.
OPENAI_API_KEY = (
    os.environ.get("OPENAI_API_KEY", "")
    or os.environ.get("OPEN-AI-API-KEY", "")
).strip()

# Origins allowed to call the API from a browser. Comma-separated override via
# CORS_ORIGINS; "*" allows any origin (fine for local dev / a hackathon demo).
CORS_ORIGINS = [
    o.strip() for o in os.environ.get("CORS_ORIGINS", "*").split(",") if o.strip()
]

# Narrow, exact-input replay used for the hackathon presentation. Normal ideas
# never enter this path and continue to use the live graph/model pipeline.
DEMO_REPLAY_ENABLED = os.environ.get("DEMO_REPLAY_ENABLED", "true").strip().lower() in (
    "1", "true", "yes",
)
DEMO_REPLAY_STEP_DELAY_SEC = max(
    0.0, float(os.environ.get("DEMO_REPLAY_STEP_DELAY_SEC", "1.20"))
)

# ---------------------------------------------------------------------------
# Databricks (optional dual-write mirror — see app/databricks_store.py)
# ---------------------------------------------------------------------------
# Off by default. Local disk (app/store.py) is always the source of truth;
# turning this on only adds a best-effort mirrored copy in Delta + a Unity
# Catalog Volume. Leaving it off (or misconfigured) is 100% safe — nothing
# here is imported or contacted unless every required var is also set.
DATABRICKS_ENABLED = os.environ.get("DATABRICKS_ENABLED", "false").strip().lower() in (
    "1", "true", "yes",
)
DATABRICKS_HOST = os.environ.get("DATABRICKS_HOST", "")
DATABRICKS_CLIENT_ID = os.environ.get("DATABRICKS_CLIENT_ID", "")
DATABRICKS_CLIENT_SECRET = os.environ.get("DATABRICKS_CLIENT_SECRET", "")
DATABRICKS_SERVER_HOSTNAME = os.environ.get("DATABRICKS_SERVER_HOSTNAME", "")
DATABRICKS_HTTP_PATH = os.environ.get("DATABRICKS_HTTP_PATH", "")
DATABRICKS_CATALOG = os.environ.get("DATABRICKS_CATALOG", "pocketfm_dev")
DATABRICKS_SCHEMA = os.environ.get("DATABRICKS_SCHEMA", "studio")
DATABRICKS_VOLUME = os.environ.get("DATABRICKS_VOLUME", "audio")

# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
TEXT_MODEL_HARD = os.environ.get("OPENAI_HARD_MODEL", "gpt-5.6-sol")
TEXT_MODEL_EASY = os.environ.get("OPENAI_EASY_MODEL", "gpt-5.6-luna")
# Gemini model used by app.llm (text generation, structured output, and
# transcription). Restored after the OpenAI-routing config migration removed it
# while app/llm.py still references it.
TEXT_MODEL = os.environ.get("GEMINI_TEXT_MODEL", "gemini-3.1-flash-lite")
TRANSCRIPTION_MODEL = "gemini-3.1-flash-lite"
TTS_MODEL = "gemini-3.1-flash-tts-preview"
TTS_OPENAI_FALLBACK_ENABLED = os.environ.get(
    "TTS_OPENAI_FALLBACK_ENABLED", "false"
).strip().lower() in ("1", "true", "yes")
TTS_OPENAI_FALLBACK_MODEL = os.environ.get(
    "TTS_OPENAI_FALLBACK_MODEL", "gpt-4o-mini-tts"
)

# Reasoning and model selection are deliberately separate.  Every production
# text call names one route below, making its Luna/Sol assignment auditable.
THINK_HIGH = "high"
THINK_MEDIUM = "medium"
THINK_LOW = "low"

# Keep latency-sensitive, bounded structured work on Luna.  Sol is reserved for
# the three places where long-range creative consistency materially matters.
# max_output_tokens is a guardrail against runaway generations, not a target.
TEXT_TASKS: dict[str, dict[str, str | int]] = {
    "wizard_bootstrap": {"model": TEXT_MODEL_EASY, "tier": "luna", "effort": THINK_LOW, "max_output_tokens": 3000},
    "clarify_regeneration": {"model": TEXT_MODEL_EASY, "tier": "luna", "effort": THINK_LOW, "max_output_tokens": 2400},
    "confirm_card": {"model": TEXT_MODEL_EASY, "tier": "luna", "effort": THINK_LOW, "max_output_tokens": 1200},
    "blueprint": {"model": TEXT_MODEL_HARD, "tier": "sol", "effort": THINK_MEDIUM, "max_output_tokens": 8000},
    "episode_config": {"model": TEXT_MODEL_EASY, "tier": "luna", "effort": THINK_LOW, "max_output_tokens": 700},
    "episode_plan": {"model": TEXT_MODEL_HARD, "tier": "sol", "effort": THINK_MEDIUM, "max_output_tokens": 7000},
    "emotional_curve": {"model": TEXT_MODEL_EASY, "tier": "luna", "effort": THINK_LOW, "max_output_tokens": 3200},
    "episode_script": {"model": TEXT_MODEL_HARD, "tier": "sol", "effort": THINK_MEDIUM, "max_output_tokens": 16000},
    "voice_cast": {"model": TEXT_MODEL_EASY, "tier": "luna", "effort": THINK_LOW, "max_output_tokens": 2400},
    "sound_design": {"model": TEXT_MODEL_EASY, "tier": "luna", "effort": THINK_LOW, "max_output_tokens": 8000},
    "story_analysis": {"model": TEXT_MODEL_EASY, "tier": "luna", "effort": THINK_LOW, "max_output_tokens": 3200},
    "episode_evaluation": {"model": TEXT_MODEL_EASY, "tier": "luna", "effort": THINK_LOW, "max_output_tokens": 2600},
}

# ---------------------------------------------------------------------------
# Images (OpenAI) — series thumbnail + character portraits
# ---------------------------------------------------------------------------
# Off by default. Artwork is decoration: with this false, app/images.py never
# contacts a provider and every generator returns None, so the story pipeline is
# completely unaffected. Flip IMAGE_ENABLED=true in .env to turn it on.
IMAGE_ENABLED = os.environ.get("IMAGE_ENABLED", "false").strip().lower() in (
    "1", "true", "yes",
)
IMAGE_MODEL = os.environ.get("OPENAI_IMAGE_MODEL", "gpt-image-2")
# Portrait key art. Cropped by the landscape dashboard card, but reusable if a
# portrait cover view is added later.
IMAGE_SIZE = os.environ.get("IMAGE_SIZE", "1024x1536")
IMAGE_QUALITY = os.environ.get("IMAGE_QUALITY", "medium")   # low | medium | high

# At most this many character portraits per series, narrator excluded.
MAX_CHARACTER_IMAGES = max(1, int(os.environ.get("MAX_CHARACTER_IMAGES", "3")))

IMAGE_TIMEOUT_MS = max(1_000, int(os.environ.get("IMAGE_TIMEOUT_MS", "180000")))
IMAGE_MAX_RETRIES = max(1, int(os.environ.get("IMAGE_MAX_RETRIES", "3")))
IMAGE_MAX_CONCURRENCY = max(1, int(os.environ.get("IMAGE_MAX_CONCURRENCY", "2")))

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ASSETS_DIR = PROJECT_ROOT / "assets"
MUSIC_DIR = ASSETS_DIR / "music"
SFX_DIR = ASSETS_DIR / "sfx"
SOUND_MANIFEST = ASSETS_DIR / "sound_manifest.json"
OUTPUT_DIR = PROJECT_ROOT / "output"

# Shared content-addressed cache for text responses, transcription, and images.
# Exact requests return locally without contacting a provider. Bump VERSION to
# invalidate all entries after a semantic request-format change.
MODEL_CACHE_ENABLED = os.environ.get("MODEL_CACHE_ENABLED", "true").strip().lower() in (
    "1", "true", "yes",
)
MODEL_CACHE_DIR = Path(
    os.environ.get("MODEL_CACHE_DIR", str(OUTPUT_DIR / "_model_cache"))
)
MODEL_CACHE_TTL_SEC = max(
    0, int(os.environ.get("MODEL_CACHE_TTL_SEC", str(7 * 24 * 60 * 60)))
)
MODEL_CACHE_VERSION = os.environ.get("MODEL_CACHE_VERSION", "v1").strip() or "v1"

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
TTS_MAX_CONCURRENCY = max(1, int(os.environ.get("TTS_MAX_CONCURRENCY", "1")))
TTS_PARALLEL_WORKERS = max(
    1, int(os.environ.get("TTS_PARALLEL_WORKERS", str(TTS_MAX_CONCURRENCY)))
)
TTS_CACHE_DIR = Path(os.environ.get("TTS_CACHE_DIR", str(OUTPUT_DIR / "tts_cache")))

# Provider protection. The API routes remain synchronous, but these limits keep
# a burst of creator requests from exhausting every request thread or provider slot.
MODEL_TIMEOUT_MS = max(1_000, int(os.environ.get("MODEL_TIMEOUT_MS", "120000")))
# Reasoning models on a long prompt (the blueprint and per-episode scripts are
# the worst cases) routinely run past the generic 120s budget, so text
# generation gets its own, longer one.
TEXT_TIMEOUT_MS = max(1_000, int(os.environ.get("TEXT_TIMEOUT_MS", "600000")))
MODEL_MAX_RETRIES = max(1, int(os.environ.get("MODEL_MAX_RETRIES", "3")))
MODEL_MAX_CONCURRENCY = max(1, int(os.environ.get("MODEL_MAX_CONCURRENCY", "8")))

# In-process job controls. These deliberately do not imply multi-instance
# durability; PostgreSQL/queue-backed work remains a later migration.
JOB_MAX_CONCURRENCY = max(1, int(os.environ.get("JOB_MAX_CONCURRENCY", "5")))
JOB_MAX_QUEUE = max(1, int(os.environ.get("JOB_MAX_QUEUE", "100")))
JOB_MAX_RETAINED = max(1, int(os.environ.get("JOB_MAX_RETAINED", "200")))
# Cap how many story-generation jobs (episode / analysis / refinement /
# emotional curve) may be queued or running at once. A 6th request gets 429.
STORY_MAX_CONCURRENCY = max(1, int(os.environ.get("STORY_MAX_CONCURRENCY", "5")))
STORY_JOB_KINDS = frozenset({"episode", "analysis", "refinement", "emotional_curve"})

# Input guardrails cap memory and provider work without affecting normal ideas,
# recordings, or scripts.
MAX_IDEA_CHARS = max(1_000, int(os.environ.get("MAX_IDEA_CHARS", "50000")))
MAX_UPLOAD_BYTES = max(1_024 * 1_024, int(os.environ.get("MAX_UPLOAD_BYTES", str(50 * 1024 * 1024))))
UPLOAD_CHUNK_BYTES = 1024 * 1024
MAX_SCRIPT_LINES = max(1, int(os.environ.get("MAX_SCRIPT_LINES", "1000")))
MAX_SCRIPT_LINE_CHARS = max(100, int(os.environ.get("MAX_SCRIPT_LINE_CHARS", "4000")))

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
