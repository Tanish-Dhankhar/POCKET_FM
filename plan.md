# AI Creator Copilot — Implementation Plan

> Turn a single **plain-text story idea** into a publish-ready, multi-voice audio series.
> **Stack:** Python · LangGraph · FastAPI (JSON backend) · Gemini `gemini-3.1-flash-lite` (text) · `gemini-3.1-flash-tts-preview` (TTS) · pydub (audio assembly).
> **Scope note:** Video generation (IDEA.MD Step 9) is **deferred** for now.

---

## 1. Product Goal

A collaborative copilot that takes **one detailed story idea in plain text** and walks the creator through: extract & confirm metadata → clarify → series blueprint → episode config → episode plan → script → voices → audio (emotion + per-character voices + background music & SFX). The creator **reviews, edits, approves, or regenerates** at every stage. Everything downstream is **derived from the creator's initial idea** — including *how many characters exist and who they are*. The AI **remembers everything** so the series can be extended later with continuity.

---

## 2. The End-to-End Flow (authoritative)

This is the exact pipeline the app implements. Each stage has an approve / edit / regenerate gate.

| #  | Stage                        | What happens                                                                                                                                                                                                                                                | Creator control                              |
| -- | ---------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------- |
| 0  | **Idea Input**         | Creator pastes the**entire story idea in detail** as plain text. That's the only required input.                                                                                                                                                      | —                                           |
| 1  | **Extract & Confirm**  | LLM reads the idea and**extracts** genre, theme, tone, language, setting, and a first pass at the **characters it detected in the story** (count + who they are is inferred from the idea, not fixed). Shown back for confirmation.             | Change any field / confirm                   |
| 2  | **Clarify**            | If anything is unclear/missing, LLM asks**up to 5 questions**, each with multiple-choice options **and** a free-text box (or both).                                                                                                             | Answer via options or text                   |
| 3  | **Series Blueprint**   | LLM writes the**overall plot / story world / main storyline**, plus **character descriptions & relationships** (the character set comes from the idea + clarifications), tone, and theme.                                                       | Edit any section / regenerate part / approve |
| 4  | **Episode Config**     | LLM**recommends an episode count** based on the depth/scope of the story, and the creator sets the final **number of episodes** + **average episode length (5–15 min)**.                                                                 | Accept recommendation or override            |
| 5  | **Episode Plan**       | LLM divides the story into episodes — per episode: title, summary, main events,**emotional focus**, and an **ending cliffhanger**.                                                                                                             | Edit summaries / reorder / repace / approve  |
| 6  | **Script Generation**  | LLM writes the full**dialogue for each character + narrator** (narrator only if the story needs one). **Emotion tags are added only on lines where the emotion genuinely shifts** — most lines carry no tag and are read in the voice's natural delivery.                                                                                             | Edit any line / regenerate / approve         |
| 7  | **Voice Casting**      | Creator assigns a**distinct Gemini voice to each character** (and the narrator). LLM suggests a fit per character.                                                                                                                                    | Choose / change any voice                    |
| 8  | **Audio Generation**   | TTS renders each line in the assigned voice (with emotion only where tagged); per-character clips are stitched into the episode with natural pauses.                                                                                                                                                | Preview / re-render a line                   |
| 9  | **Sound Design & Mix** | LLM picks**sparse, subtle background music & SFX** from a prebuilt CC0 library and places them only where they add something (romantic scene → soft romantic bed; lightning → thunder SFX). **Many stretches stay dialogue-only or silent** so sound never feels wall-to-wall. Mixed low under the voices.                                                                       | Preview / change / remove any cue            |
| ↺ | **Continue the Story** | Creator writes a**new plot in plain text**; the same pipeline runs — clarify if needed, **update the general story, update/add characters if mentioned**, and generate **new episodes** using the *same theme* and full prior context. | Full control again                           |

**Key correction vs. a fixed cast:** there is **no preset number of characters**. The character list and count are *inferred from the initial story idea* in Stage 1, refined in clarification (Stage 2), and finalized in the blueprint (Stage 3). Continuation can add new characters when the new plot introduces them.

---

## 3. High-Level Architecture

```
┌──────────────────────────────────────────────────────────────┐
│              FastAPI backend  (JSON, headless)                 │
│   POST /series  ·  /series/{id}/advance  ·  /approve  ·  /edit │
│         (any frontend can drive the approve/edit/regen loop)   │
└───────────────────────────┬──────────────────────────────────┘
                            │  (human-in-the-loop interrupts)
┌───────────────────────────▼──────────────────────────────────┐
│                      LangGraph Orchestrator                    │
│  StateGraph + Checkpointer (persistent series memory)          │
│                                                                │
│  idea → extract → clarify → blueprint → ep_config →            │
│    → episode_plan → script → voice_cast → tts →                │
│      → sound_design → mix → deliver                            │
└───────────────────────────┬──────────────────────────────────┘
              ┌─────────────┼───────────────┐
              ▼             ▼               ▼
      ┌──────────────┐ ┌──────────┐ ┌──────────────────┐
      │ Gemini Flash │ │ Gemini   │ │ Audio Engine     │
      │ Lite (text)  │ │ Flash TTS│ │ pydub: mix, duck,│
      │ structured   │ │ per-line │ │ loop, SFX, export│
      │ JSON output  │ │ voices   │ │                  │
      └──────────────┘ └──────────┘ └──────────────────┘
                                          ▲
                                   ┌──────┴───────┐
                                   │ Prebuilt CC0 │
                                   │ music + SFX  │
                                   └──────────────┘
```

**Why LangGraph:** the workflow is a stateful graph with approval gates. It gives us (1) explicit nodes per stage, (2) `interrupt()` for human-in-the-loop approve/edit/regenerate exposed over FastAPI, and (3) a **checkpointer** that persists the whole series state — which doubles as the "AI remembers everything" continuity engine for extending the series later.

---

## 4. Project Structure

```
POCKET_FM/
├── .env                       # GEMINI_API_KEY (already added)
├── plan.md                    # this file
├── tts.py                     # working TTS reference (keep as scratch)
├── requirements.txt
├── app/
│   ├── main.py                # FastAPI app + routes
│   ├── config.py              # model ids, paths, tunables
│   ├── llm.py                 # Gemini text client + structured-output helper
│   ├── tts.py                 # Gemini TTS client (per-line rendering)
│   ├── state.py               # LangGraph State schema
│   ├── graph.py               # StateGraph wiring + checkpointer
│   ├── nodes/
│   │   ├── extract.py         # Stage 1: extract+confirm genre/theme/chars
│   │   ├── clarify.py         # Stage 2: up to 5 clarification questions
│   │   ├── blueprint.py       # Stage 3: series blueprint (+ characters)
│   │   ├── ep_config.py       # Stage 4: recommend & set ep count + length
│   │   ├── episode_plan.py    # Stage 5: episode breakdown
│   │   ├── script.py          # Stage 6: dialogue w/ emotion tags
│   │   ├── voice_cast.py      # Stage 7: assign a Gemini voice per character
│   │   ├── audio.py           # Stage 8: TTS render per line
│   │   ├── sound_design.py    # Stage 9a: LLM picks music/SFX cues
│   │   └── mix.py             # Stage 9b: assemble voices + music + SFX
│   ├── prompts/               # prompt templates (one file per node)
│   ├── schemas/               # Pydantic models for each structured output
│   └── audio_engine.py        # pydub helpers: overlay, duck, loop, export
├── assets/
│   ├── music/                 # curated CC0 tracks, by mood
│   │   ├── romantic/  horror/  action/  emotional/  ambient/  tense/
│   ├── sfx/                    # curated CC0 one-shots + ambiences
│   │   ├── thunder.wav rain.wav footsteps.wav door.wav birds.wav ...
│   └── sound_manifest.json    # mood/keyword → file mapping + metadata
└── output/
    └── <series_id>/
        ├── series.json         # snapshot of persisted state
        ├── ep01/
        │   ├── script.json
        │   ├── lines/          # per-line rendered wavs
        │   ├── ep01_voices.wav # stitched dialogue+narration
        │   └── ep01_final.wav  # + music + SFX
        └── ...
```

---

## 5. LangGraph State Schema (`state.py`)

A single state object flows through the graph and is checkpointed per `series_id`.

```python
class CharacterProfile(TypedDict):
    name: str
    description: str
    personality: str
    relationships: list[str]     # ties to other characters
    is_narrator: bool            # narrator only if the story needs one
    voice_id: str                # Gemini voice, assigned in voice_cast
    vocal_signature: str         # pace/pitch/tics — guides emotion tags

class SeriesState(TypedDict):
    series_id: str
    # Stage 0 — the ONLY required input
    idea: str
    # Stage 1 — extracted from idea, then confirmed
    genre: str; theme: str; tone: str; language: str; setting: str
    characters: list[CharacterProfile]   # COUNT + who = derived from idea
    # Stage 2
    clarification_qa: list[dict]          # {question, options[], answer}
    # Stage 3
    blueprint: dict                       # plot, world, storyline, tone, theme
    # Stage 4
    recommended_ep_count: int             # LLM suggestion from story depth
    ep_count: int; ep_minutes: int        # ep_minutes ∈ [5, 15]
    # Stage 5
    episodes: list[dict]                  # title, summary, events, emotion, cliffhanger
    # Stage 6
    scripts: dict[int, list[dict]]        # ep -> ordered lines (see §8)
    # Stage 7
    voice_cast: dict[str, str]            # character name -> voice_id
    # Stage 9
    sound_cues: dict[int, list[dict]]     # ep -> cues (music/sfx w/ timing)
    # continuation
    arcs: list[str]                       # each appended plain-text plot
    # bookkeeping
    stage: str
    approvals: dict[str, bool]            # stage -> approved?
    feedback: str                         # latest edit/regenerate instruction
```

**Continuity / memory:** the checkpointer persists `SeriesState`. "Continue the Story" re-enters the graph with the existing state; blueprint + character list + prior-episode summaries are fed to the LLM for every new arc so tone/relationships/plot stay consistent, and **new characters are appended** to `characters` when the new plot introduces them.

---

## 6. Human-in-the-Loop Pattern (approve / edit / regenerate)

Every generative node follows the same contract, surfaced over FastAPI:

```
generate  →  interrupt(present result via JSON)  →  receive command:
   • APPROVE          → approvals[stage]=True, continue
   • EDIT(payload)    → merge creator's manual edits into state, continue
   • REGENERATE(note) → store note in feedback, loop back to same node
```

Implemented with LangGraph `interrupt()` + a conditional edge that routes back to the node on `REGENERATE`. Nothing advances until `approvals[stage]` is true.

### FastAPI surface (indicative)

- `POST /series` — submit the plain-text idea → runs to first interrupt (Stage 1 confirm).
- `GET  /series/{id}/state` — current stage + payload awaiting review.
- `POST /series/{id}/approve` — approve current stage.
- `POST /series/{id}/edit` — submit edits for current stage.
- `POST /series/{id}/regenerate` — regenerate with a note.
- `POST /series/{id}/continue` — submit a new plain-text plot (continuation).
- `GET  /series/{id}/episodes/{n}/audio` — download `epNN_final.wav`.

---

## 7. Text Generation with Gemini Flash Lite (`llm.py`)

- SDK: `google-genai` (`from google import genai`).
- Model: `gemini-3.1-flash-lite` (GA; 1M context; configurable thinking).
- **Structured output** (Pydantic schemas in `app/schemas/`) so every node returns validated JSON.
- `thinking_level="high"` for extract / blueprint / episode-plan / script (creative + consistency-heavy); `"low"` for mechanical steps (sound-cue tagging).

```python
client = genai.Client()  # reads GEMINI_API_KEY from .env
resp = client.models.generate_content(
    model="gemini-3.1-flash-lite",
    contents=prompt,
    config=types.GenerateContentConfig(
        thinking_config=types.ThinkingConfig(thinking_level="high"),
        response_mime_type="application/json",
        response_schema=BlueprintSchema,
    ),
)
```

### Node-by-node text tasks

| Node         | Input                                                 | Structured output                                                     |
| ------------ | ----------------------------------------------------- | --------------------------------------------------------------------- |
| extract      | plain-text idea                                       | genre, theme, tone, language, setting,**detected characters[]** |
| clarify      | idea + extracted meta                                 | ≤5 questions, each MCQ options + free-text allowed                   |
| blueprint    | idea + clarifications                                 | plot, world, storyline, characters[] + relationships, tone, theme     |
| ep_config    | blueprint                                             | **recommended_ep_count** + rationale                            |
| episode_plan | blueprint + ep_count + minutes                        | per-ep: title, summary, events, emotional focus, cliffhanger          |
| script       | episode outline + character profiles + prior-ep recap | ordered lines w/ speaker + emotion tags (§8)                         |
| sound_design | script + manifest keys                                | per-line music/SFX cues (§10)                                        |

---

## 8. Captivating Script Generation (Stage 6) — the core craft

Rules baked into the script prompt (`prompts/script.py`), tuned for the Pocket-FM serialized format:

1. **Hook in the first 60 seconds**; treat the **first 3 episodes as critical** — front-load the strongest material.
2. **End every episode on an emotionally-driven cliffhanger** calibrated to the protagonist's emotional state (not a mechanical jump-scare).
3. **Characters carry long-form engagement** — enforce distinct *vocal signatures* (pace, pitch, tics) so voices are instantly distinguishable in audio.
4. **2–4 speaking characters per scene** is the sweet spot; >5 confuses listeners with no visuals.
5. **Write for the ear** — natural spoken rhythm, short beats, active tension.
6. **Cliffhanger toolkit:** withhold consequences, foreshadow, raise emotional stakes, shift perspective, add a ticking-clock deadline.
7. **Narrator is optional** — include a narrator line-type only when the story needs scene-setting/transitions.
8. **Emotion is sparse, not constant** — the prompt instructs the LLM to tag a line **only when the emotion genuinely changes or peaks** (a reveal, a threat, a breakdown). Neutral/expository lines get **no tag** and are read in the voice's natural delivery. Over-tagging makes every line sound theatrical, so a soft cap (~1 in 3–4 lines carries a tag) is stated in the prompt and sanity-checked after generation.
9. **Continuity:** every script call receives the blueprint, character profiles, and a recap of prior episodes.

### Script line format (with emotion + sound hints)

Each episode script is an **ordered list of typed lines** — consumed by both TTS and the mixer:

```json
[
  {"type": "narration", "speaker": "Narrator",
   "text": "Rain tapped the tin roof. Maya hadn't moved in an hour.",
   "sfx": ["rain"], "music": "emotional"},

  {"type": "dialogue", "speaker": "Maya",
   "text": "You said you'd call when you landed.",
   "sfx": [], "music": null},

  {"type": "dialogue", "speaker": "Ravi",
   "text": "I know. I'm sorry.",
   "sfx": [], "music": null},

  {"type": "dialogue", "speaker": "Ravi",
   "text": "[Whisper] They know about the girl.",
   "sfx": [], "music": null},

  {"type": "dialogue", "speaker": "Maya",
   "text": "[Fear] What did you just say?",
   "sfx": [], "music": null}
]
```

- **Most lines have no emotion tag and no sound** (`sfx: []`, `music: null`) — they're plain dialogue in the voice's natural delivery. Tags appear only where the beat turns (here: the whispered reveal and the fearful reaction).
- **Emotion** = inline bracket tags the TTS model reads and performs — matching the style proven in `tts.py`: `[Calm]`, `[Curious]`, `[Whisper]`, `[Fear]`, `[Panic]`, `[Anger]`, `[Relief]`, `[Joy]`, plus `[pause]` and pacing cues. Used sparingly (see rule 8).
- `sfx` / `music` are optional hints per line, refined against the real asset library in Stage 9; leaving them empty is the default.
- Creator can edit any line's `text`, `speaker`, or tags before production.

---

## 9. Voice Casting (Stage 7) & Emotion

- Gemini TTS provides **30 named voices** with style labels (e.g. `Puck`=upbeat, `Enceladus`=breathy, `Kore`=firm, `Charon`=informative, `Gacrux`=mature, `Sulafat`=warm, `Aoede`=breezy, `Fenrir`=excitable).
- `voice_cast` maps **each character + narrator to a distinct voice**, guided by that character's `vocal_signature`; the LLM suggests a fit and the creator overrides freely.
- Emotion works on two layers together: **(a)** a voice whose baseline temperament matches the character (carries most lines with no tag needed), and **(b)** occasional bracket tags only on the lines where emotion peaks or turns.

---

## 10. Sound Design (Stage 9) — subtle music & SFX

### 10a. Prebuilt CC0 library (curated pack — one-time)

- **Pre-download a small, hand-picked set** of **CC0 / no-attribution** clips from Pixabay/Freesound into `assets/music/<mood>/` and `assets/sfx/`. Reliable, offline, demo-safe.
- Cover the IDEA.MD examples: romantic / horror / action / emotional / ambient / tense music; thunder, rain, footsteps, door, birds, battle, forest, etc.
- Hand-write `assets/sound_manifest.json`: each entry `{file, type, mood/keywords, loopable, default_gain_db, license}`. This is the **closed vocabulary** the LLM must choose from.

### 10b. LLM cue selection (`sound_design.py`)

- Prompt: *given the script lines and the manifest's allowed keywords, choose music/SFX per beat.* Output constrained to manifest keys (structured output + validation) so the LLM can't invent files.
- **Restraint is enforced, not hoped for:**
  - **Silence is a valid, common choice.** Not every scene gets music, and many beats run on dialogue alone. The prompt explicitly tells the LLM it may (and often should) return no cue for a beat.
  - Background music changes only on **scene/mood shifts**, not per line (romantic scene → soft romantic bed spanning the scene), and a **minimum gap** between music cues prevents constant bed-swapping.
  - SFX only on concrete, script-mentioned events (lightning → thunder, door → creak, footsteps → steps) — never as decoration.
  - A rule-check caps overall density: **≤1 SFX per N seconds**, a ceiling on the **fraction of an episode covered by music** (e.g. ≤~50%), and it drops duplicates and back-to-back cues.
- Creator can preview / change / remove any cue.

---

## 11. Audio Generation (Stage 8) — `app/tts.py`

**Reference:** the working `tts.py` in the repo. It uses `generate_content` with `response_modalities=["AUDIO"]` + `SpeechConfig` and reads emotion from bracket tags — we adopt exactly this call, one **single-speaker call per line**.

**Why per-line single-speaker:** Gemini multi-speaker TTS is limited to **2 speakers per call** and quality drifts past a few minutes. Rendering one line at a time with that character's voice gives us unlimited distinct voices, clean per-line SFX insertion, short stable outputs, and cheap single-line regeneration.

```python
def render_line(text, voice_id, out_path):
    resp = client.models.generate_content(
        model="gemini-3.1-flash-tts-preview",
        contents=text,                        # includes [Emotion] bracket tags
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
    with wave.open(out_path, "wb") as wf:     # 1ch, 24kHz, 16-bit PCM
        wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(24000)
        wf.writeframes(pcm)
```

- Loop over episode lines → `lines/0001_Narrator.wav`, `0002_Maya.wav`, …
- **Cache by content hash** so unchanged lines aren't re-billed on regeneration.
- Concatenate with short natural pauses → `epNN_voices.wav`.

---

## 12. Mixing (Stage 9 assembly) — `audio_engine.py` (pydub)

1. **Timeline:** concatenate per-line voice clips, tracking each line's start offset (ms).
2. **SFX:** `.overlay(sfx, position=line_offset)` at mapped moments.
3. **Music:** loop the mood track under the relevant scene span; **duck under speech** with `gain_during_overlay=-12` (or slice-and-attenuate for true sidechain) so voices stay clear.
4. Normalize levels, gentle fades between music changes; export `epNN_final.wav`.
5. Keep beds subtle (~ −15 to −18 dB under voice) — *enhance, don't overpower*.
6. **Preserve silence:** beats with no cue play as clean dialogue (or a brief held pause between lines). Don't backfill quiet stretches with ambience — the quiet is intentional pacing.

> Perf note: pydub `.overlay()` is pure-Python; overlay whole clips (not per-sample) and keep counts reasonable.

---

## 13. Continuing the Story

- Creator submits a **new plot in plain text** (`POST /series/{id}/continue`).
- Same pipeline re-enters: clarify if needed → **update the general story/blueprint** → **update existing characters and add new ones the plot introduces** → generate **new episodes** using the *same theme* and full prior context (events, relationships, tone, prior summaries).
- New episodes flow through script → voices → audio → mix unchanged.

---

## 14. Tech Stack & Dependencies (`requirements.txt`)

```
google-genai          # Gemini text + TTS
langgraph             # orchestration + checkpointer
langchain-core        # message/type helpers (as needed)
fastapi               # JSON backend
uvicorn               # ASGI server
pydantic              # structured-output schemas (already present)
pydub                 # audio assembly  (needs ffmpeg on PATH)
python-dotenv         # load GEMINI_API_KEY from .env
requests              # optional: one-time asset fetch script
```

System dep: **ffmpeg** (pydub backend). Python 3.13 venv already set up.

---

## 15. Build Phases

1. **Foundation** — `config.py`, `llm.py` (verify Flash-Lite structured output), `app/tts.py` (wrap the working `render_line`), `.env` loading.
2. **Text pipeline** — LangGraph skeleton + nodes: extract → clarify → blueprint → ep_config → episode_plan → script, with interrupt/approve/regenerate over FastAPI.
3. **Voice + audio** — voice_cast, per-line TTS render, concatenate to `epNN_voices.wav`.
4. **Sound design + mix** — build curated CC0 library + manifest, sound_design node, pydub mixing with ducking → `epNN_final.wav`.
5. **Continuity** — persist state, "continue the story" re-entry with character updates.
6. **Polish** — caching, level tuning, SFX-density guardrails, retries.
7. *(Later)* Video generation (Step 9) — out of scope now.

---

## 16. Open Decisions / Risks

- **TTS cost/latency:** per-line calls multiply requests — mitigated by content-hash caching and rendering only changed lines.
- **Voice drift:** keep line text tone aligned with the chosen voice's style; short clips reduce drift.
- **Asset licensing:** curated pack is CC0 / no-attribution; record per-file license in `sound_manifest.json`.
- **Language:** Gemini TTS supports 70+ languages; for non-English scripts, keep the `[Emotion]` bracket tags in English (model recommendation).
- **Episode length ceiling:** avg length capped at 5–15 min; long episodes are chunked for TTS stability.

---

### Sources

- [Gemini 3.1 Flash-Lite (text)](https://ai.google.dev/gemini-api/docs/models/gemini-3.1-flash-lite)
- [Gemini TTS speech generation](https://ai.google.dev/gemini-api/docs/speech-generation)
- [Writing serialized audio fiction (Pocket FM)](https://pocketfm.com/improve-skills) · [Cliffhangers &amp; hooks](https://fiveable.me/writing-the-episodic-drama/unit-1/cliffhangers-hooks/study-guide/Cuo8Qm8Wx7LsRLyN)
- [Pixabay CC0 sound effects](https://pixabay.com/sound-effects/) · [pydub API (overlay/ducking)](https://github.com/jiaaro/pydub/blob/master/API.markdown)
