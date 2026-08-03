<div align="center">

# Pocket FM AI Story Studio

**Turn any story idea into a fully produced audio drama — script, voices, music, and all.**

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![React](https://img.shields.io/badge/React-18+-61DAFB?style=for-the-badge&logo=react&logoColor=black)](https://react.dev)
[![OpenAI](https://img.shields.io/badge/OpenAI-Powered-412991?style=for-the-badge&logo=openai&logoColor=white)](https://openai.com)
[![Gemini](https://img.shields.io/badge/Gemini-TTS%20%26%20STT-4285F4?style=for-the-badge&logo=google&logoColor=white)](https://ai.google.dev)
[![LangGraph](https://img.shields.io/badge/LangGraph-Workflow-FF6B35?style=for-the-badge)](https://langchain-ai.github.io/langgraph/)

[![Trophy](https://img.shields.io/badge/Zero%20to%20One%20Hackathon-1st%20Runner--Up-gold?style=for-the-badge&logo=trophy&logoColor=white)](#)

</div>

---

## Teaser



https://github.com/user-attachments/assets/5425ea71-cd73-4594-88bb-44a5d4065a7f



---

## Team

![Pocket FM AI Story Studio team at the Zero to One hackathon](assets/readme/team-photo.jpg)

*Pocket FM AI Story Studio — Zero to One Hackathon, 1st Runner-Up*

---

## What is Pocket FM AI Story Studio?

Pocket FM AI Story Studio is a **human-guided AI production tool** that takes a raw story idea — typed or spoken — and transforms it into a complete, ready-to-listen audio drama episode.

The creator stays in **full control** at every key decision point. The AI automates the repetitive heavy lifting: writing, voicing, sound planning, and audio mixing. This is **not** a "press one button and hope" system — every important stage can be reviewed, edited, or regenerated before the next step begins.

---

## Features

| Feature | Description |
|---|---|
| **Voice Input** | Speak your idea directly — Gemini transcribes it automatically |
| **AI Story Planner** | Extracts genre, tone, setting, characters, and builds a full story blueprint |
| **Creator Q&A Flow** | 4 tailored clarification questions before any heavy generation begins |
| **Episode Script Generator** | Structured dialogue and narration with per-line emotional cues |
| **Automatic Voice Casting** | Assigns distinct Gemini TTS voices to every character |
| **AI Sound Design** | Plans music beds, ambient layers, and SFX timed to script lines |
| **Full Audio Mix** | Exports a polished `.wav` episode with ducking, panning, and transitions |
| **Approve / Edit / Regenerate** | Creator has full control at every planning stage |
| **Story Analytics** | Genre mix charts, emotional curves, and episode plot arcs |
| **Optional Cover Art** | AI-generated series thumbnail and character portraits |
| **Persistent Storage** | Everything saved to disk — resume work after a server restart |
| **Optional Databricks Mirror** | Replicate series data and audio to Delta tables and Unity Catalog |

---

## Architecture Overview

```
React Web App  (Vite + Tailwind + Zustand + Framer Motion)
      │  HTTP + JSON / file upload
      ▼
FastAPI Backend  (app/main.py)
      │
      ├──► LangGraph Planning Workflow  (app/graph.py)
      │         │
      │         ├──► OpenAI Responses API  →  structured story objects
      │         └──► Local JSON series folder  (output/<series-id>/)
      │
      ├──► Episode Production Jobs  (app/episode_service.py)
      │         │
      │         ├──► OpenAI  →  scripts + evaluations + sound plan
      │         ├──► Gemini TTS  →  one WAV clip per spoken line
      │         └──► pydub audio engine  →  final mixed .wav episode
      │
      ├──► Gemini STT  →  transcribe microphone idea input
      ├──► OpenAI Images  →  optional cover art & character portraits
      └──► Databricks Client  →  optional Delta table mirror
```

For the full pipeline, data-flow diagrams, and AI design decisions, see **[ARCHITECTURE.md](ARCHITECTURE.md)**.

---

## Technology Stack

### Frontend

| Tech | Role |
|---|---|
| React 18 + Vite | SPA framework and dev server |
| Tailwind CSS | Utility-first styling |
| Zustand | Lightweight wizard state management |
| React Query | API data-fetching and caching |
| Recharts | Genre, emotional curve, and story-plot charts |
| Framer Motion | Page and panel transitions |
| React Router | Multi-page creator journey routing |

### Backend

| Tech | Role |
|---|---|
| Python 3.11+ | Application language |
| FastAPI + Pydantic | HTTP API, schema validation, serialization |
| LangGraph | Reviewable multi-stage planning state machine |
| pydub + FFmpeg | Audio assembly and mixing |

### AI & Services

| Provider | Usage |
|---|---|
| OpenAI Responses API | Story extraction, blueprint, scripts, sound plan, evaluation (structured output) |
| Google Gemini | Speech-to-text (idea transcription) + Text-to-speech (character voices) |
| OpenAI Images | Optional series cover art and character portraits |

---

## How the Pipeline Works

### Stage 1 — Series Planning (LangGraph Workflow)

The AI plans the series in **reviewable stages**. The creator approves, edits, or regenerates at each step before the pipeline advances:

| Stage | What the AI does | Creator action |
|---|---|---|
| **Extract** | Detects genre, tone, setting, logline, and characters | Review / edit metadata |
| **Clarify** | Presents 4 story-specific multiple-choice questions | Submit answers or regenerate |
| **Blueprint** | Builds the story world, characters, and causal storyline | Approve / edit / regenerate |
| **Episode Config** | Recommends episode count and duration | Choose count and duration |
| **Episode Plan** | Titles, summaries, events, and cliffhangers per episode | Approve / edit / regenerate |
| **Voice Cast** | Assigns a Gemini voice to every character | Change voice assignments |
| **Sound Design** | Plans music, ambience, SFX, and timing | Approve / edit / regenerate |

### Stage 2 — Episode Production (Background Job)

Once planning is approved, each episode is produced in a background job with no additional creator input required:

```
Approved outline
  → Script (OpenAI)           —  typed lines with speaker names and emotion cues
  → Evaluation (OpenAI)       —  story-plot beats + editorial feedback
  → TTS per line (Gemini)     —  one .wav clip per spoken line
  → Voice track assembly      —  concatenated clips with natural pauses
  → Sound plan (OpenAI)       —  music / SFX / ambience cues with timings
  → Validation + clamping     —  rejects invalid or overcrowded AI suggestions
  → pydub mix                 —  ducking, panning, looping, fade transitions
  → Final episode .wav        —  ready to listen
```

---

## Quick Start

### Prerequisites

| Requirement | Version | Notes |
|---|---|---|
| Python | 3.11+ | Required for the backend |
| Node.js | 20+ | Required for the frontend |
| FFmpeg | Any recent | Must be on your system `PATH` — used by pydub for audio processing |

---

### Step 1 — Clone the repository

```powershell
git clone <your-repo-url>
cd POCKET_FM
```

---

### Step 2 — Create the Python virtual environment

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt -r requirements-dev.txt
```

---

### Step 3 — Configure environment variables

Copy the example file and open it to fill in your keys:

```powershell
Copy-Item .env.example .env
```

#### Required keys

| Variable | Description |
|---|---|
| `OPENAI_API_KEY` | OpenAI key for story generation (also used for optional images and TTS fallback) |
| `GEMINI_API_KEY` | Primary Gemini key for speech-to-text and text-to-speech |
| `GEMINI_API_KEYS` | Comma-separated list of Gemini keys for TTS rotation and rate limit handling |

#### Optional settings

| Variable | Default | Description |
|---|---|---|
| `OPENAI_HARD_MODEL` | `gpt-5.6-sol` | Model for blueprint, episode plan, and scripts (long-range reasoning tasks) |
| `OPENAI_EASY_MODEL` | `gpt-5.6-luna` | Model for extraction, voice cast, sound plan, and other fast tasks |
| `IMAGE_ENABLED` | `false` | Set `true` to generate cover art and up to 3 character portraits |
| `DEMO_REPLAY_ENABLED` | `true` | Set `false` to disable exact-input demo replay mode |
| `TTS_PARALLEL_WORKERS` | `3` | Number of concurrent Gemini TTS workers |
| `TTS_MIN_INTERVAL_SEC` | `21` | Minimum gap between TTS requests — reduce only if your Gemini quota allows |
| `TTS_OPENAI_FALLBACK_ENABLED` | `false` | Fall back to OpenAI TTS after Gemini retries are exhausted |
| `MODEL_CACHE_ENABLED` | `true` | Cache AI responses to disk to avoid repeated provider calls |
| `MODEL_CACHE_TTL_SEC` | `604800` | Cache TTL in seconds (default: 7 days) |
| `DATABRICKS_ENABLED` | *(unset)* | Enable optional mirror to Databricks Delta tables and Unity Catalog Volume |

> **Note:** Keep `.env` private. It is already listed in `.gitignore`. Only `.env.example` (with placeholder values) is committed to the repository.

---

### Step 4 — Start the backend

With the virtual environment active, from the project root:

```powershell
python -m uvicorn app.main:app --reload --port 8000
```

Verify the server is running:

```
GET http://localhost:8000/health
```

---

### Step 5 — Start the frontend

Open a **second terminal**:

```powershell
cd frontend
npm install
npm run dev
```

Vite prints a local URL — usually `http://localhost:5173`. Open it in your browser.

#### Frontend environment (standalone development only)

Create `frontend/.env` so the frontend knows where the API is:

```env
VITE_API_BASE=http://localhost:8000
```

> Without this setting, the frontend expects a reverse proxy at `/api` (used in production deployments).

---

## Tests

Run the full backend test suite from the project root:

```powershell
pytest
```

Most tests use fakes and temporary folders — **no live API keys are required**. The GitHub Actions CI workflow runs this suite automatically on every push.

---

## Project Layout

```
POCKET_FM/
├── app/                      FastAPI application and all backend logic
│   ├── main.py               HTTP routes and API entry point
│   ├── graph.py              LangGraph planning state machine
│   ├── state.py              Shared workflow state definition
│   ├── config.py             Centralized config loaded from .env
│   ├── schemas.py            Pydantic contracts for every AI result
│   ├── prompts.py            Prompt templates for all AI tasks
│   ├── llm.py                OpenAI Responses API client (structured output, retry, cache)
│   ├── tts.py                Gemini TTS with rate limiting, retry, and clip cache
│   ├── audio_engine.py       pydub mixing, ducking, panning, and WAV export
│   ├── episode_service.py    Background episode production job runner
│   ├── story_service.py      Story analysis and emotional curve generation
│   ├── image_service.py      Optional cover art and character portrait generation
│   ├── store.py              Local JSON persistence — primary source of truth
│   ├── jobs.py               In-process background job registry
│   ├── api_store.py          API-layer state helpers
│   └── nodes/                LangGraph stage node implementations
│       ├── text.py           Planning nodes (extract, clarify, blueprint, etc.)
│       └── audio.py          Audio and sound-design nodes
│
├── frontend/                 React creator interface (Vite + Tailwind CSS)
├── assets/                   Bundled music, SFX, voice samples, and sound manifest
│   └── sound_manifest.json   Allowlist of music moods and SFX names for the AI planner
├── sql/                      Optional Databricks schema definitions
├── tests/                    Backend test suite
├── tools/                    Smoke tests and demo-replay helpers
├── output/                   Runtime series data — created locally, git-ignored
│
├── .env.example              Environment variable template with descriptions
├── requirements.txt          Production Python dependencies
├── requirements-dev.txt      Dev and test Python dependencies
├── pytest.ini                Pytest configuration
├── ARCHITECTURE.md           Full system design, data flow, and AI decision notes
└── README.md                 This file
```

---

## Security Notes

- All API keys are in `.env`, which is git-ignored. **Never commit secrets.**
- The browser has **no direct access** to any AI provider — all credentials are server-side only.
- `output/` contains generated scripts, audio, and images. Keep it private or move it to protected storage before any deployment.
- Sound assets in `assets/library/` carry their own source licenses. Review them before any commercial or public distribution.
- For production: add authentication middleware, tighten CORS origins, replace `MemorySaver` with a persistent LangGraph checkpointer, and add a durable task queue.

---

## Extension Points

| What to extend | Where to look |
|---|---|
| Add a durable queue for multi-user use | Replace `app/jobs.py` with Celery + Redis; swap `MemorySaver` in `app/graph.py` |
| Change or add AI providers | Edit `app/config.py` (model routes) and `app/llm.py` (client) only |
| Add new sound assets | Add entries to `assets/sound_manifest.json` — the AI planner learns them automatically |
| Add new audio export formats | Extend `app/audio_engine.py` with mastering steps or format conversion |
| Add authentication | Add OAuth/JWT middleware in `app/main.py` and tighten `CORS_ORIGINS` in `app/config.py` |
| Add Databricks persistence | Configure the `DATABRICKS_*` env vars; see `app/databricks_store.py` and `sql/` |

---

<div align="center">

Built for the **Zero to One Hackathon**

</div>

