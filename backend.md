# AI Creator Copilot — Backend Documentation

> **Stack:** Python 3.13 · LangGraph · FastAPI · OpenAI GPT-5.6 (text) · Gemini Flash TTS (audio) · pydub
> **Purpose:** Turn a single plain-text story idea into a complete, multi-voice, publish-ready audio series through a human-in-the-loop pipeline.

---

## Smoke Test Results

The full text pipeline was verified locally on 2026-07-24:

```
[REVIEW] stage=extract        payload_keys=['genre', 'theme', 'tone', 'language', 'setting', 'logline', 'characters']
[REVIEW] stage=clarify        payload_keys=['questions']
[REVIEW] stage=blueprint      payload_keys=['blueprint', 'characters']
[REVIEW] stage=ep_config      payload_keys=['recommended_ep_count', 'rationale', 'minutes_bounds']
[REVIEW] stage=episode_plan   payload_keys=['episodes', 'ep_count', 'ep_minutes']
[REVIEW] stage=script         payload_keys=['scripts']
[REVIEW] stage=voice_cast     payload_keys=['voice_cast', 'reasons', 'voices']
== stopping at voice_cast (not approving) ==
```

All 7 text stages completed. Each stage correctly paused for review, exposing the right payload keys. Pipeline halted cleanly at `voice_cast` as configured.

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Project Structure](#2-project-structure)
3. [Pipeline Stages](#3-pipeline-stages)
4. [LangGraph Orchestration](#4-langgraph-orchestration)
5. [State Schema](#5-state-schema)
6. [FastAPI Routes](#6-fastapi-routes)
7. [LLM Layer](#7-llm-layer)
8. [Schemas and Structured Output](#8-schemas-and-structured-output)
9. [Prompt Templates](#9-prompt-templates)
10. [TTS and Audio Engine](#10-tts-and-audio-engine)
11. [Sound Assets and Manifest](#11-sound-assets-and-manifest)
12. [Configuration Reference](#12-configuration-reference)
13. [Running and Testing](#13-running-and-testing)
14. [Human-in-the-Loop Contract](#14-human-in-the-loop-contract)
15. [Continuation and Memory](#15-continuation-and-memory)
16. [Caching and Rate Limiting](#16-caching-and-rate-limiting)
17. [Key Design Decisions](#17-key-design-decisions)

---

## 1. Architecture Overview

```
+--------------------------------------------------------------+
|              FastAPI backend  (JSON, headless)                |
|   POST /series  GET /state  /approve  /edit  /regenerate     |
|            (any frontend drives the approve/edit loop)        |
+------------------------+-------------------------------------+
                         |  human-in-the-loop interrupts
+------------------------v-------------------------------------+
|                   LangGraph Orchestrator                      |
|   StateGraph + MemorySaver checkpointer (per series_id)       |
|                                                               |
|  extract -> clarify -> blueprint -> ep_config ->              |
|     -> episode_plan -> script -> voice_cast -> audio ->       |
|       -> sound_design -> mix -> deliver                       |
+------------------------+-------------------------------------+
           +-------------+--------------+
           v             v              v
   +--------------+ +---------+ +------------------+
   | Gemini Flash | | Gemini  | | Audio Engine      |
   | Lite (text)  | | Flash   | | pydub: concat,    |
   | structured   | | TTS     | | duck, loop, SFX,  |
   | JSON output  | |         | | export            |
   +--------------+ +---------+ +------------------+
                                       ^
                                +------+------+
                                | CC0 asset   |
                                | library     |
                                +-------------+
```

**Why LangGraph?**
The pipeline is a stateful graph with approval gates. LangGraph gives us:
1. **Explicit nodes per stage** - pure generator functions that read state and return partial updates.
2. **interrupt() for human-in-the-loop** - the graph pauses at every review node and exposes the payload over FastAPI. Resuming never re-runs the LLM call; only the review routing executes again.
3. **MemorySaver checkpointer** - persists the full SeriesState per thread_id (= series_id), which doubles as the "AI remembers everything" continuity store for series extension.

---

## 2. Project Structure

```
POCKET_FM/
+-- .env                       # GEMINI_API_KEY
+-- requirements.txt           # Python dependencies
+-- tts.py                     # root-level TTS reference/scratch
+-- test.py                    # quick Gemini connectivity test
+-- plan.md                    # detailed implementation plan
+-- backend.md                 # this file
+-- app/
|   +-- __init__.py
|   +-- main.py                # FastAPI app + all routes
|   +-- config.py              # models, paths, audio tunables, voice catalogue
|   +-- llm.py                 # Routed OpenAI text client + structured output
|   +-- tts.py                 # Gemini TTS client: render_line() + caching
|   +-- state.py               # SeriesState TypedDict + new_state() factory
|   +-- graph.py               # StateGraph wiring + GRAPH singleton
|   +-- schemas.py             # Pydantic models for every node LLM output
|   +-- prompts.py             # prompt builders for every text-generation node
|   +-- audio_engine.py        # pydub helpers: concat, music, SFX, export
|   +-- assets.py              # sound manifest reader + path lookups
|   +-- nodes/
|       +-- __init__.py
|       +-- text.py            # Stages 1-7: extract, clarify, blueprint, ...
|       +-- audio.py           # Stages 8-9 + deliver: TTS, sound design, mix
+-- tools/
|   +-- __init__.py
|   +-- smoke.py               # local drive-through test (no HTTP)
|   +-- build_assets.py        # verifies/restores the licensed manifest pack
+-- assets/
|   +-- library/v2/music/      # licensed mood beds
|   +-- library/v2/sfx/        # licensed one-shots and ambience
|   +-- sound_manifest.json    # mood/key -> file + metadata
+-- output/
    +-- <series_id>/
        +-- series.json        # full state snapshot
        +-- ep01/
            +-- lines/         # 0001_Narrator.wav, 0002_Maya.wav, ...
            +-- ep01_voices.wav
            +-- ep01_final.wav
```

---

## 3. Pipeline Stages

The pipeline runs as an ordered chain of (gen_X, review_X) node pairs. Auto stages skip the review interrupt.

| # | Stage | Nodes | Auto? | What it does |
|---|-------|-------|-------|-------------|
| 1 | extract | gen_extract -> review_extract | No | Reads the idea and extracts: genre, theme, tone, language, setting, logline, and the inferred character list. |
| 2 | clarify | gen_clarify -> review_clarify | No | Generates 0-5 MCQ clarification questions. Auto-skips if nothing is unclear. |
| 3 | blueprint | gen_blueprint -> review_blueprint | No | Writes full series blueprint: logline, story world, main storyline, tone/theme, character roster with vocal signatures. |
| 4 | ep_config | gen_ep_config -> review_ep_config | No | Recommends episode count. Creator sets final ep_count and ep_minutes (5-15). |
| 5 | episode_plan | gen_episode_plan -> review_episode_plan | No | Plans every episode: title, summary, main events, emotional focus, cliffhanger. |
| 6 | script | gen_script -> review_script | No | Writes full dialogue + narration for every episode with sparse inline emotion tags. |
| 7 | voice_cast | gen_voice_cast -> review_voice_cast | No | Assigns a distinct Gemini voice to each character, guided by vocal signature. |
| 8 | audio | gen_audio | YES | TTS renders every script line; stitches per-line WAVs into epNN_voices.wav. |
| 9a | sound_design | gen_sound_design -> review_sound_design | No | LLM picks sparse music/SFX cues; density guardrails enforced in Python. |
| 9b | mix | gen_mix | YES | Overlays music beds (ducked) and SFX one-shots -> epNN_final.wav. |
| - | deliver | gen_deliver | YES | Snapshots full state to output/<series_id>/series.json. |

---

## 4. LangGraph Orchestration

**File:** `app/graph.py`

### Node Pattern

```
gen_X  ->  (if not AUTO)  review_X  ->  gen_next
```

`gen_X` functions are pure: they read state, call LLM/TTS, return a partial dict. They never touch interrupt().

`review_X` functions are generated by `_make_review(stage, next_node)`. They:
1. Call `interrupt(payload)` - the graph pauses and FastAPI returns the payload.
2. On resume, receive a cmd dict: `{action, note, data}`.
3. Route:
   - REGENERATE -> back to gen_X with feedback set.
   - APPROVE or EDIT -> merge any edits from cmd.data, advance to the next node.

### Graph Wiring

```python
CHAIN = [
    "extract", "clarify", "blueprint", "ep_config",
    "episode_plan", "script", "voice_cast",
    "audio", "sound_design", "mix",
]
AUTO_STAGES = {"audio", "mix"}
```

For each stage:
- Always adds `gen_{stage}` node.
- If not auto: adds `review_{stage}` node and `gen_{stage} -> review_{stage}` edge.
- If auto: edge goes directly `gen_{stage} -> gen_{next}`.

`graph.py` exposes a module-level singleton compiled graph:
```python
GRAPH = build_graph()   # compiled StateGraph with MemorySaver
```

### Allowed Edit Keys

Only keys in ALLOWED_EDIT_KEYS are merged from a client EDIT payload:
```python
ALLOWED_EDIT_KEYS = {
    "genre", "theme", "tone", "language", "setting", "logline", "characters",
    "clarification", "clarification_answers", "blueprint",
    "recommended_ep_count", "ep_count", "ep_minutes", "episodes",
    "scripts", "voice_cast", "sound_plans",
}
```

---

## 5. State Schema

**File:** `app/state.py`

```python
class SeriesState(TypedDict, total=False):
    series_id: str

    # Stage 0 - only required input
    idea: str

    # Stage 1 - extracted then confirmed by creator
    genre: str
    theme: str
    tone: str
    language: str
    setting: str
    logline: str
    characters: list[dict]          # CharacterProfile-shaped dicts

    # Stage 2
    clarification: dict             # {questions: [...]}
    clarification_answers: list[dict]

    # Stage 3
    blueprint: dict                 # plot, world, storyline, tone, theme, characters

    # Stage 4
    recommended_ep_count: int
    ep_count: int
    ep_minutes: int                 # 5-15

    # Stage 5
    episodes: list[dict]            # EpisodePlanItem-shaped dicts

    # Stage 6 - keyed by str(episode_number)
    scripts: dict[str, list[dict]]

    # Stage 7
    voice_cast: dict[str, str]      # character name -> voice id

    # Stage 9
    sound_plans: dict[str, dict]    # ep number -> SoundPlan dict

    # Continuation
    arcs: list[str]                 # each appended continuation plot

    # Bookkeeping
    stage: str
    approvals: dict[str, bool]
    feedback: str
    command: dict
    ui: dict                        # transient display extras (rationale, reasons)
    audio_manifest: dict            # ep number -> {voices, offsets, total_ms, final}
```

`new_state(series_id, idea)` creates a fresh state with all lists/dicts pre-initialised so nodes never see None.

---

## 6. FastAPI Routes

**File:** `app/main.py`

Start the server:
```bash
uvicorn app.main:app --reload
```

### Endpoints

| Method | Path | Body | Description |
|--------|------|------|-------------|
| POST | /series | {"idea": "..."} | Create new series. Runs to first interrupt (Stage 1 review). Returns series_id + first review payload. |
| GET | /series/{id}/state | - | Current stage, approvals, pending status, full state. |
| POST | /series/{id}/approve | {} (optional) | Approve the current stage and advance. |
| POST | /series/{id}/edit | {"data": {...}} | Merge creator edits and advance. |
| POST | /series/{id}/submit | {"data": {...}} | Submit answers (used for clarify + ep_config stages). |
| POST | /series/{id}/regenerate | {"note": "..."} | Regenerate the current stage with a guidance note. |
| POST | /series/{id}/continue | {"plot": "..."} | Append a new continuation plot and re-run from blueprint. |
| GET | /series/{id}/episodes/{n}/audio | - | Download epNN_final.wav (or _voices.wav if mixing not done). |
| GET | /health | - | Returns configured hard/easy text models, transcription model, and TTS model. |

### Response Shapes

**While awaiting review:**
```json
{
  "series_id": "abc123",
  "status": "awaiting_review",
  "stage": "extract",
  "payload": {
    "genre": "Horror",
    "theme": "...",
    "characters": [...]
  }
}
```

**When pipeline completes:**
```json
{
  "series_id": "abc123",
  "status": "done",
  "stage": "deliver",
  "audio_manifest": {
    "1": {"voices": "output/abc123/ep01/ep01_voices.wav", "final": "..."}
  }
}
```

### Internal Helpers

- `_cfg(series_id)` - builds {"configurable": {"thread_id": series_id}} for the checkpointer.
- `_run(series_id, inp)` - invokes GRAPH and returns the pending/done response.
- `_snapshot(series_id)` - fetches current state; raises 404 if unknown.
- `_resume(series_id, cmd)` - resumes a paused graph with a Command(resume=payload).

---

## 7. LLM Layer

**File:** `app/llm.py`

The OpenAI client is lazily initialised from `OPENAI_API_KEY`. High-effort calls
route to Sol and low-effort calls route to Luna. Gemini remains responsible for
microphone transcription and TTS.

### generate_text(prompt, thinking, system)
Free-form text generation. Rarely used; nodes prefer structured output.

### generate_structured(prompt, schema, thinking, system) -> T
The primary function used by all text nodes.

```python
resp = openai_client().responses.parse(
    model=model_for_thinking(thinking),
    input=messages,
    reasoning={"effort": thinking},
    text_format=schema,
    store=False,
)
```

Every node gets a validated Pydantic instance through native structured output.

### Thinking Levels Per Stage

| Stage | Level | Reason |
|-------|-------|--------|
| extract, blueprint, episode_plan, script | high | Creative + consistency-heavy |
| clarify, ep_config, voice_cast | high | Story-sensitive decisions |
| sound_design | low | Mechanical keyword selection |

---

## 8. Schemas and Structured Output

**File:** `app/schemas.py`

One Pydantic schema per node output. These are the LLM-pipeline contracts.

| Schema | Stage | Key Fields |
|--------|-------|-----------|
| ExtractResult | 1 | genre, theme, tone, language, setting, logline, characters: list[DetectedCharacter] |
| ClarifyResult | 2 | questions: list[ClarifyQuestion] (0-5) |
| Blueprint | 3 | logline, story_world, main_storyline, tone, theme, characters: list[CharacterProfile] |
| EpisodeConfigSuggestion | 4 | recommended_ep_count, rationale |
| EpisodePlan | 5 | episodes: list[EpisodePlanItem] |
| EpisodeScript | 6 | lines: list[ScriptLine] |
| VoiceCastSuggestion | 7 | assignments: list[VoiceAssignment] |
| SoundPlan | 9 | music: list[MusicCue], sfx: list[SfxCue] |

### Key Schema Details

**CharacterProfile** (from Blueprint):
```
name, role, description, personality,
relationships: list[str],
vocal_signature: str,   # pace/pitch/tics - guides voice casting + emotion
is_narrator: bool
```

**ScriptLine**:
```
type: "narration" | "dialogue"
speaker: str              # character name or "Narrator"
text: str                 # may contain inline [Emotion] tag at start
sfx: list[str]            # SFX keyword hints - usually empty []
music: str | None         # mood keyword to start a bed - usually null
```

---

## 9. Prompt Templates

**File:** `app/prompts.py`

Each function returns the full user prompt string. Craft rules live in prompts; pipeline code stays about orchestration.

### System Prompt (SYSTEM)

> "You are an expert showrunner and audio-drama writer for a Pocket-FM-style serialized fiction platform. You write for the ear: natural spoken rhythm, distinct character voices, strong hooks, and emotionally-driven cliffhangers. You always respond with valid JSON matching the requested schema."

### Prompt Builders

| Function | Key Inputs | Key Instructions |
|----------|-----------|-----------------|
| extract | idea text | Infer full cast, don't fix character count |
| clarify | idea + metadata | 0-5 MCQ questions with 2-4 options each; fewer if idea is already clear |
| blueprint | all above + continuation arcs | Full series foundation; vocal signatures for every character |
| ep_config | blueprint | Recommend focused season (6-12 eps); explain reasoning |
| episode_plan | blueprint + ep_count + ep_minutes + prior recap | Front-load first 3 eps; every ep ends on cliffhanger |
| script | episode outline + char profiles + prior recap | Write for the ear; emotion tags sparse (1 in 3-4 lines); sound sparse |
| voice_cast | char list + voice catalogue | Match vocal signatures; never reuse a voice |
| sound_design | episode script + allowed keys | Silence is default; music on mood shifts; SFX only for concrete events |

**Feedback block:** If a feedback string is set (from REGENERATE), it's appended to every prompt:
"The creator asked you to REGENERATE with this guidance - honour it: '...'"

---

## 10. TTS and Audio Engine

### TTS (app/tts.py)

Single-speaker, per-line rendering via generate_content with response_modalities=["AUDIO"]:

```python
def render_line(text, voice_id, out_path, *, cache_dir=None) -> Path:
    resp = client().models.generate_content(
        model=TTS_MODEL,            # "gemini-3.1-flash-tts-preview"
        contents=text,              # may contain [Emotion] bracket tags
        config=types.GenerateContentConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name=voice_id
                    )
                )
            ),
        ),
    )
    pcm = resp.candidates[0].content.parts[0].inline_data.data
    _write_wav(out_path, pcm)   # 1ch, 24kHz, 16-bit PCM
```

**Content-hash caching:** Each call is keyed by SHA256(TTS_MODEL|voice_id|text)[:16]. If the same (model, voice, text) was rendered before, the cached WAV is copied without an API call.

**Why per-line single-speaker?** Gemini multi-speaker TTS is limited to 2 speakers per call. Per-line rendering gives unlimited distinct voices, clean per-line SFX insertion, short stable clips, and cheap single-line regeneration.

**Output format:** 1-channel, 24kHz, 16-bit PCM WAV (matching TTS output exactly, no resampling needed).

### Audio Engine (app/audio_engine.py)

pydub-based helpers:

| Function | Description |
|----------|-------------|
| load(path) | Load any audio file via pydub |
| concat_lines(paths, pause_ms) | Concatenate WAVs with 350ms pause between lines; returns (track, offsets_ms) |
| place_music(base, bed_path, start_ms, end_ms) | Loop + duck music bed under voice (MUSIC_DUCK_DB = -16 dB); fade in/out |
| place_sfx(base, sfx_path, at_ms) | Overlay one-shot SFX at timeline offset (SFX_GAIN_DB = -6 dB) |
| export(seg, out_path) | Export AudioSegment to WAV |

**Music ducking:** The bed is attenuated by duck_db (dB), then overlaid using pydub's .overlay(). The voice track plays on top unchanged.

### Audio Node Flow (app/nodes/audio.py)

```
gen_audio:
  for each episode:
    for each script line:
      render_line(text, voice, lines/NNNN_Speaker.wav, cache_dir)
    concat_lines -> ep01_voices.wav
    manifest[ep] = {voices, offsets, total_ms, line_files}

gen_sound_design:
  for each episode:
    generate_structured(SoundPlan)
    _enforce(plan, offsets, total_ms)  -> density guardrails
    sound_plans[ep] = {music: [...], sfx: [...]}

gen_mix:
  for each episode:
    load ep_voices.wav
    place_music for each music cue
    place_sfx for each SFX cue
    export -> ep01_final.wav
    manifest[ep]["final"] = path

gen_deliver:
  write output/<series_id>/series.json
```

**Voice fallback:** If a character is not in voice_cast, it gets a deterministic fallback:
`VOICE_NAMES[abs(hash(speaker)) % len(VOICE_NAMES)]`

---

## 11. Sound Assets and Manifest

**File:** `app/assets.py` + `assets/sound_manifest.json`

The manifest is the closed vocabulary the LLM must choose from in sound_design. The LLM cannot invent file names.

### Manifest Structure

```json
{
  "music": {
    "romantic": {"file": "library/v2/music/romantic_mixkit_659.mp3", "loopable": true, "keywords": ["love","tender"], "license": "Mixkit Stock Music Free License"},
    "horror":   {"file": "library/v2/music/horror_mixkit_671.mp3",   "loopable": true, "keywords": ["scary","dread"], "license": "Mixkit Stock Music Free License"}
  },
  "sfx": {
    "thunder": {"file": "library/v2/sfx/thunder_mixkit_1297.wav", "keywords": ["lightning","storm"], "license": "Mixkit Sound Effects Free License"},
    "rain":    {"file": "library/v2/sfx/rain_mixkit_2393.wav",    "keywords": ["rainfall","drizzle"], "license": "Mixkit Sound Effects Free License"}
  }
}
```

### Music Moods (8 beds)
romantic, emotional, hopeful, tense, horror, mystery, action, ambient

### SFX Keys (12 one-shots)
thunder, rain, wind, footsteps, door_creak, birds, heartbeat, clock_tick, sword_clash, glass_break, crowd, phone_ring

### Synchronising Licensed Assets

The manifest records each source and direct download URL. The sync command keeps
existing files by default and downloads only missing licensed assets.

```bash
python -m tools.build_assets
# Verifies 8 music beds + 15 SFX; restores missing files
```

### Sound Design Density Guardrails (_enforce in audio.py)

After the LLM picks cues, these Python rules are applied:

| Rule | Setting |
|------|---------|
| 1 SFX per N seconds max | MIN_SECONDS_BETWEEN_SFX = 6.0 |
| 55% of episode max may have music | MAX_MUSIC_COVERAGE = 0.55 |
| Music cues spaced 20s+ apart | MIN_SECONDS_BETWEEN_MUSIC_CUES = 20.0 |
| SFX keys must exist in manifest | validated, invalid keys dropped |
| Music moods must exist in manifest | validated, invalid moods dropped |

---

## 12. Configuration Reference

**File:** `app/config.py`

| Setting | Value | Description |
|---------|-------|-------------|
| TEXT_MODEL_HARD | gpt-5.6-sol | Difficult creative and consistency-heavy work |
| TEXT_MODEL_EASY | gpt-5.6-luna | Smaller, mechanical, or latency-sensitive work |
| TRANSCRIPTION_MODEL | gemini-3.1-flash-lite | Microphone transcription |
| TTS_MODEL | gemini-3.1-flash-tts-preview | Gemini TTS model |
| THINK_HIGH | "high" | Thinking level for creative nodes |
| THINK_LOW | "low" | Thinking level for mechanical nodes |
| TTS_SAMPLE_RATE | 24000 Hz | TTS output sample rate |
| TTS_CHANNELS | 1 | Mono audio |
| TTS_SAMPLE_WIDTH | 2 bytes | 16-bit PCM |
| TTS_MIN_INTERVAL_SEC | 21.0 | Rate-limit spacing for free-tier TTS (~3 req/min) |
| TTS_MAX_RETRIES | 6 | Retries on 429 responses |
| PAUSE_BETWEEN_LINES_MS | 350 | Silence gap between dialogue lines |
| MUSIC_DUCK_DB | -16 | Music bed attenuation under voice |
| SFX_GAIN_DB | -6 | SFX level relative to voice |
| MUSIC_FADE_MS | 1200 | Cross-fade when music bed changes |
| EP_MINUTES_MIN | 5 | Minimum episode length |
| EP_MINUTES_MAX | 15 | Maximum episode length |

### Voice Catalogue (30 voices)

```
Zephyr: Bright       Puck: Upbeat          Charon: Informative
Kore: Firm           Fenrir: Excitable     Leda: Youthful
Orus: Firm           Aoede: Breezy         Callirrhoe: Easy-going
Autonoe: Bright      Enceladus: Breathy    Iapetus: Clear
Umbriel: Easy-going  Algieba: Smooth       Despina: Smooth
Erinome: Clear       Algenib: Gravelly     Rasalgethi: Informative
Laomedeia: Upbeat    Achernar: Soft        Alnilam: Firm
Schedar: Even        Gacrux: Mature        Pulcherrima: Forward
Achird: Friendly     Zubenelgenubi: Casual Vindemiatrix: Gentle
Sadachbia: Lively    Sadaltager: Knowledgeable  Sulafat: Warm
```

### Emotion Tags (used sparingly in scripts)

```
Calm  Curious  Whisper  Fear  Panic  Anger  Relief  Joy
Sad  Excited  Nervous  Serious  Sarcastic  Tender  Shouting
Trembling  Pleading  Cold  Amused  Determined  [pause]
```

---

## 13. Running and Testing

### Prerequisites

```bash
# 1. Set API key in .env
echo GEMINI_API_KEY="your_key_here" > .env

# 2. Activate venv (Windows)
.venv\Scripts\activate

# 3. Install deps
pip install -r requirements.txt

# 4. Verify or restore the licensed sound library
python -m tools.build_assets
```

### Start the API Server

```bash
uvicorn app.main:app --reload --port 8000
```

### Quick Connectivity Test

```bash
python test.py
# Calls the Luna text route and prints a 50-word detective cat story
```

### Smoke Test (no HTTP, drives graph directly)

```bash
# Text stages only - stops before voice_cast, no TTS API calls
python -m tools.smoke text

# Full pipeline - TTS + mixing, uses API quota, takes several minutes
python -m tools.smoke full
```

The smoke test uses a built-in horror story idea (night-shift nurse + ghost) and auto-approves all stages except:
- clarify: submits empty answers
- ep_config: sets 1 episode, 5 minutes

**Verified output (text mode):**
```
[REVIEW] stage=extract        payload_keys=['genre', 'theme', 'tone', 'language', 'setting', 'logline', 'characters']
[REVIEW] stage=clarify        payload_keys=['questions']
[REVIEW] stage=blueprint      payload_keys=['blueprint', 'characters']
[REVIEW] stage=ep_config      payload_keys=['recommended_ep_count', 'rationale', 'minutes_bounds']
[REVIEW] stage=episode_plan   payload_keys=['episodes', 'ep_count', 'ep_minutes']
[REVIEW] stage=script         payload_keys=['scripts']
[REVIEW] stage=voice_cast     payload_keys=['voice_cast', 'reasons', 'voices']
== stopping at voice_cast (not approving) ==
```

### Manual API Walkthrough

```bash
# 1. Create a series
curl -X POST http://localhost:8000/series \
  -H "Content-Type: application/json" \
  -d '{"idea": "A detective who can hear the last words of murder victims..."}'

# Response: {"series_id": "abc123", "status": "awaiting_review", "stage": "extract", ...}

# 2. Approve extract stage
curl -X POST http://localhost:8000/series/abc123/approve

# 3. Submit clarification answers
curl -X POST http://localhost:8000/series/abc123/submit \
  -H "Content-Type: application/json" \
  -d '{"data": {"clarification_answers": []}}'

# 4. Approve blueprint
curl -X POST http://localhost:8000/series/abc123/approve

# 5. Set episode config
curl -X POST http://localhost:8000/series/abc123/edit \
  -H "Content-Type: application/json" \
  -d '{"data": {"ep_count": 6, "ep_minutes": 10}}'

# 6. Approve remaining stages (episode_plan, script, voice_cast, sound_design)
curl -X POST http://localhost:8000/series/abc123/approve
# (repeat for each stage)

# 7. Download episode audio after mix completes
curl http://localhost:8000/series/abc123/episodes/1/audio -o ep01.wav

# 8. Health check
curl http://localhost:8000/health
```

### Regenerate With Guidance

```bash
curl -X POST http://localhost:8000/series/abc123/regenerate \
  -H "Content-Type: application/json" \
  -d '{"note": "Make the characters more morally ambiguous and the tone darker"}'
```

---

## 14. Human-in-the-Loop Contract

Every reviewable stage follows this exact pattern:

```
gen_X: LLM call -> writes result to state
    |
    v
review_X: calls interrupt(payload)
    |   (graph pauses; FastAPI returns payload to client)
    v
client sends one of:
  APPROVE    -> merge nothing extra; advance to gen_next
  EDIT       -> merge cmd.data (filtered by ALLOWED_EDIT_KEYS); advance
  SUBMIT     -> merge cmd.data (clarification answers, ep config); advance
  REGENERATE -> set feedback = cmd.note; go back to gen_X
```

**Critical:** Resuming after an interrupt never re-runs the LLM. The gen_X node already wrote its result to state. review_X only does routing. On APPROVE/EDIT, the LLM result is kept as-is (possibly with creator overrides merged in).

On REGENERATE, gen_X runs again with state.feedback populated so the prompt includes the creator's guidance via the feedback block.

---

## 15. Continuation and Memory

The MemorySaver checkpointer persists the entire SeriesState per series_id (= LangGraph thread_id).

**Extending a series:**

```bash
curl -X POST http://localhost:8000/series/abc123/continue \
  -H "Content-Type: application/json" \
  -d '{"plot": "A new villain from the protagonist past emerges..."}'
```

This:
1. Appends the new plot text to the arcs list.
2. Clears feedback and approvals.
3. Re-enters at gen_blueprint via `Command(goto="gen_blueprint", update=...)`.
4. gen_blueprint receives the full arcs list; the prompt instructs the LLM to update the storyline and add new characters the plot introduces.
5. The full pipeline continues from there: episode_plan -> script -> voice_cast -> audio -> sound_design -> mix -> deliver.

**Continuity is maintained** because every subsequent node receives the same SeriesState including prior episode summaries, character profiles, relationships, and tone.

---

## 16. Caching and Rate Limiting

### TTS Content-Hash Cache

- Cache directory: `output/<series_id>/tts_cache/`
- Key: `SHA256(TTS_MODEL|voice_id|text)[:16].wav`
- On regeneration, only lines whose text actually changed are re-billed.
- Unchanged lines are served from cache with a file copy, no API call.

### Rate Limiting

Free-tier Gemini TTS allows ~3 requests per minute. TTS_MIN_INTERVAL_SEC = 21 spaces calls out automatically.

To disable rate limiting on a paid tier, add to .env:
```
TTS_MIN_INTERVAL_SEC=0
```

TTS_MAX_RETRIES = 6 retries on 429 responses with backoff.

---

## 17. Key Design Decisions

### No Preset Character Count
Characters are inferred from the story idea in Stage 1, not fixed upfront. Some stories have 2 characters, some have 10. The ExtractResult.characters list is always derived from the idea text. This propagates through the whole pipeline - blueprint refines them, continuation can add new ones.

### Emotion is Sparse, Not Constant
The script prompt explicitly caps emotion tags at ~1 in 3-4 lines and only on lines where emotion genuinely peaks or shifts (reveals, threats, breakdowns). This prevents theatrical over-performance. The restraint is stated in the prompt AND documented in the ScriptLine.text field description.

### Sound Design Restraint Enforced in Code
The LLM is prompted to be sparse, but the Python _enforce() function in audio.py guarantees it: invalid keys are dropped, SFX are spaced to 6s minimum, music coverage is capped at 55%. The LLM cannot accidentally create wall-to-wall sound even if it tries.

### Auto vs. Reviewable Stages
Audio rendering (audio) and mixing (mix) are auto stages - they produce artifacts without human gates because there is nothing meaningful to approve at the raw render level. Sound design gets a review because creators may want to remove, change, or preview specific cues.

### Single-Speaker TTS Per Line
Multi-speaker Gemini TTS is limited to 2 voices and drifts on long sessions. Per-line single-speaker renders are stable, support unlimited distinct characters, and allow cheap single-line regeneration on any script edit.

### MemorySaver vs. Persistent Checkpointer
MemorySaver stores state in-process RAM - sufficient for a hackathon demo where the server stays up. For production, swap to SqliteSaver or PostgresSaver from langgraph.checkpoint with the same API and no other code changes required.

---

*Generated from full codebase analysis + live smoke test. See also: plan.md for implementation rationale and IDEA.MD for the original product concept.*
