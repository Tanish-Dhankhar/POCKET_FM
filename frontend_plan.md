# AI Creator Copilot — Frontend Plan

> **Goal:** a minimal, intentional, fluid **React + JavaScript** frontend over the existing
> LangGraph/FastAPI backend. Basic on purpose — clean structure now, restyle later.
> **Read with:** `plan.md` (product/pipeline rationale) and `backend.md` (API contract).

---

## 1. Design Principles

The brief is *minimal, clean, intentional, not congested, fluid*. Concretely:

| Principle | How it shows up |
|---|---|
| **One decision per screen** | Never stack the idea editor, questions, and confirm card at once. They're sequential steps in the same page shell. |
| **Generous negative space** | Max content width ~720px for reading/writing surfaces, ~1100px for the ideaboard grid. Nothing edge-to-edge. |
| **Few type sizes, few colors** | 5-step type scale, 1 accent color, near-monochrome surfaces. No decorative gradients or drop shadows. |
| **Motion explains, never decorates** | Transitions carry continuity (a card grows into a page, a step slides in). 180–320ms, one easing curve. |
| **Progressive disclosure** | Character details, episode plot, and sound cues live behind a click — not on the surface. |
| **Honest loading** | Generation takes real time (LLM + TTS). Loading screens are a designed state, not a spinner afterthought. |

**Anti-goals:** no sidebars, no dense toolbars, no dashboards-with-widgets, no modal stacking.

---

## 2. Stack

| Concern | Choice | Why |
|---|---|---|
| Language | **JavaScript (JSX)** — no TypeScript | Per your call. Faster to write; no build-time type friction. |
| Build | **Vite + React 18** | Fast, zero-config. |
| Routing | **React Router v6** | 7 pages, nested episode route. |
| Server state | **TanStack Query** | Generation is async and polled; caching + invalidation for free. |
| Wizard state | **Zustand** (one small store) | The write/mic flow spans steps and must survive step changes without prop-drilling. |
| Animation | **Framer Motion** | Layout animations + `AnimatePresence` for page/step transitions. This is the "fluid" requirement. |
| Styling | **Tailwind CSS** | Enforces the constrained token set; fastest path to a clean minimal look. |
| Audio | native `<audio>` + a thin custom player | Basic preview only; no waveform library needed yet. |
| Mic capture | `MediaRecorder` API | Records to webm/opus blob, uploaded for transcription. |

No component library. A handful of hand-rolled primitives keeps it minimal and un-generic.

**Because there is no TypeScript**, the API layer is the only place that knows response
shapes, and it must be **defensive**: default every optional field (`data.characters ?? []`,
`ep.audio?.final`). §6 documents the shapes as a reference contract instead of as types.

---

## 3. The 7 Pages

| # | Route | Page | Purpose |
|---|---|---|---|
| 1 | `/` | **Dashboard** | All series as cards (title + genre + episode count). Click → ideaboard. Plus a prominent "New series". |
| 2 | `/new` | **New Series** | Two large choices: **Write** and **Mic**. Nothing else. |
| 3 | `/new/write` | **Write** | Fullscreen text editor → Next → **4 questions** (same page) → confirm card (same page). |
| 4 | `/new/mic` | **Mic** | Recording UI → transcript → **4 questions** as cards → confirm card. |
| 5 | `/new/building` | **Loading** | Typing-text animation with witty lines while the blueprint + episode plan generate. |
| 6 | `/series/:id` | **Ideaboard** | Plot/tone/theme/setting cards, character cards (with voice picker popup), episode list. |
| 7 | `/series/:id/episodes/:n` | **Episode** | Audio player on top, generated script in an editor below. |

Pages 3 and 4 are **the same wizard with two entry modes** — they converge on identical
question + confirm steps. Implemented as one `<IdeaWizard mode="write" | "mic" />`.

---

## 4. Two API Surfaces (the core mental model)

The backend exposes **two very different kinds of endpoint**, and confusing them is the
easiest way to break this app:

| | `/series/*` — **the pipeline** | `/studio/*` — **the disk** |
|---|---|---|
| Backend file | `app/main.py` → `app/graph.py` → `app/nodes/*` | `app/api_store.py` → `app/store.py` |
| Costs money | **Yes — every call can trigger an LLM/TTS run** | No. Pure file I/O. |
| Stateful | **Yes.** Resumes a paused LangGraph; order matters | No. Call any time, any order |
| Latency | Seconds to minutes | Milliseconds |
| Safe to retry | **No** — it advances the graph | Yes, idempotent |
| Use for | Creating a series and walking the wizard | Everything the UI reads/edits afterwards |

**Rule of thumb:** the wizard (pages 3–5) talks to `/series/*`. Everything else
(pages 1, 6, 7) talks to `/studio/*`. Once a series reaches the ideaboard, the graph rests
and the UI works against the folder on disk.

### The pipeline, and where the wizard stops

```
extract → clarify → blueprint → ep_config → episode_plan │ script → voice_cast → audio → sound_design → mix
└──────────── the wizard drives this ─────────────────────┘ └──── per-episode, on demand ────┘
```

The stock graph would generate **scripts for every episode then TTS every line of every
episode** in one unstoppable run. That contradicts the per-episode Generate button and, at
the free tier's ~3 TTS req/min, would take hours. So the wizard **stops at `episode_plan`**,
and the rest runs per-episode via a job (§5 B2).

---

## 4a. The Clarification Contract (exactly 4 questions, always)

The clarify stage is now **deterministic**, which removes the old "0 questions" edge case:

- **Always exactly 4 questions.** Not "up to 5", not "0 if clear". The backend schema pins
  `min_length=4, max_length=4`, and a post-generation guard pads or trims to 4 so a
  misbehaving model can never break the UI's fixed 4-step flow.
- **Every question has 3–4 options**, each with a `label` and a one-line `detail`.
- **Exactly one option per question is `recommended: true`.** The UI marks it and
  **pre-selects it**, so the user can simply press through with sensible defaults.
- **Every question also accepts free text** (`allow_free_text` is always `true`) — the
  "write your own idea" escape hatch from IDEA.MD.
- Questions are derived from *that specific story idea* — they name its characters, setting,
  and premise. They are never generic ("What genre?" is banned; the genre was already
  extracted in stage 1).

```js
// clarify payload — shape is now guaranteed
{
  questions: [                      // exactly 4
    {
      question: "How does Maya first realise the letters are from the future?",
      options: [                    // 3-4 of these
        { label: "A postmark dated tomorrow", detail: "Quiet dread; she checks it twice.",
          recommended: true },      // exactly one true
        { label: "It predicts a death",       detail: "Immediate, high stakes.",
          recommended: false },
      ],
      allow_free_text: true,        // always true
    },
    // ...3 more
  ]
}
```

**Why this matters for the UI:** the wizard can render a fixed 4-card sequence with
`1 of 4` progress, every card arrives with a valid default selected, and "Next" is never
blocked. The answer submitted per question is `{question, answer}` where `answer` is either
the chosen option's `label` or the user's own text.

---

Everything lives in a per-series folder (`output/<series_id>/`) which is the **source of
truth**; `/studio/*` reads and writes it directly. See `plan.md` §4a.

### Built — usable today

| Endpoint | Purpose |
|---|---|
| `GET /studio/series` | Dashboard list: `series_id, title, genre, stage, episode_count, generated_count, updated_at` |
| `GET /studio/series/{id}` | Everything the ideaboard needs: `index`, `input`, `blueprint`, `characters`, `episodes[]` |
| `PATCH /studio/series/{id}` | Edit `title`, `include_narrator`, `ep_count`, `ep_minutes` |
| `DELETE /studio/series/{id}` | Remove a series |
| `GET/PATCH /studio/series/{id}/blueprint` | Read / merge-edit `plot.json`, `theme.json`, `genre.json` |
| `GET /studio/series/{id}/characters` | All character files (narrator first, then alphabetical) |
| `PATCH /studio/series/{id}/characters/{key}` | Edit one character — incl. **`voice_id`** and **`gender`**. `key` is the slug or `narrator`. Renames move the file. |
| `GET /studio/series/{id}/episodes` | Episode rows with **`status`** |
| `GET /studio/series/{id}/episodes/{n}` | `outline`, `script`, `sound_plan`, `audio`, `status` |
| `PUT /studio/series/{id}/episodes/{n}/script` | Save script edits (**auto-marks audio stale**) |
| `PUT /studio/series/{id}/episodes/{n}/outline` | Save outline edits |
| `GET /studio/series/{id}/episodes/{n}/audio` | Stream / download the episode WAV |
| `GET /studio/voices` | All 30 voices as `{id, style}` |
| `POST /studio/series/{id}/input/audio` | Store a raw mic recording into `input/` |
| `POST /series`, `/approve`, `/edit`, `/submit`, `/regenerate`, `/continue`, `GET /state` | The pipeline surface |

**Episode `status`** is derived from disk so it survives reloads:
`planned` → `scripted` → `voiced` → `ready`.

### To build first (backend)

| # | Need | Endpoint / file | Blocks |
|---|---|---|---|
| **B1** | Job runner | `app/jobs.py` — thread + in-memory status dict | Anything long-running |
| **B2** | Per-episode generate | `POST /studio/series/{id}/episodes/{n}/generate` → `202 {job_id}`; `GET /studio/jobs/{id}`. Chains the already-refactored `gen_script_for_episode` → `render_episode_audio(progress=…)` → `design_episode_sound` → `mix_episode` | Generate button |
| **B3** | Confirm-card data | `POST /studio/series/{id}/confirm-card` — one cheap Flash-Lite call → `{title, genre, setting, narrator_suggested, recommended_ep_count, recommended_ep_minutes}`, because `ep_config` only runs *after* the blueprint | Confirm step |
| **B4** | Voice samples | `GET /studio/voices/{id}/sample` renders on demand (1 TTS call) then caches to `assets/voice_samples/{voice}.wav` | Voice picker |
| **B5** | Transcription | `POST /studio/transcribe` (multipart). Flash-Lite accepts audio input, so no extra model | Mic page |
| **B6** | Honour `include_narrator` | Feed the flag into the script prompt (hard-forbid narration) | Narrator toggle |

---

## 6. Data Shapes (reference, not types)

No TypeScript, so these are the shapes the API layer must normalise. Keys that bite:

**Three contract traps:**
1. `scripts` and `audio_manifest` are keyed by **strings** (`"1"`), not numbers.
2. Character count is **never fixed** — always render the array as-is.
3. Most `ScriptLine.text` has **no** emotion tag. Parse optionally, never require it.

```js
// GET /studio/series  → { series: [ IndexCard ] }
IndexCard = {
  series_id, title, genre, stage,
  episode_count, generated_count,      // derived from disk
  created_at, updated_at,
}

// GET /studio/series/{id}
SeriesBundle = {
  index:      IndexCard,
  input:      { idea, transcript, clarification: {questions:[]}, clarification_answers: [] },
  blueprint:  { logline, story_world, main_storyline, theme, tone, genre, setting, language,
                characters: [Character] },
  characters: [Character],
  episodes:   [ { ...EpisodeOutline, number, status } ],
}

Character = {
  name, role, description, personality,
  gender,                     // may be absent on older series
  relationships: [String],
  vocal_signature,            // pace / pitch / tics
  is_narrator: Boolean,
  voice_id,                   // absent until cast
}

EpisodeOutline = { number, title, summary, main_events: [String],
                   emotional_focus, cliffhanger }

// GET /studio/series/{id}/episodes/{n}
EpisodeDetail = {
  number, status,             // planned | scripted | voiced | ready
  outline:    EpisodeOutline,
  script:     [ScriptLine],
  sound_plan: { music: [{start_line,end_line,mood,start_ms,end_ms}],
                sfx:   [{line,name,at_ms}] },
  audio:      { voices, final, offsets: [ms], total_ms, line_files: [], stale },
}

ScriptLine = {
  type: 'narration' | 'dialogue',
  speaker,                    // character name, or "Narrator"
  text,                       // may START with "[Fear] "; usually no tag
  sfx: [String],              // usually []
  music: String | null,       // usually null
}

// Pipeline responses (POST /series and the command endpoints)
AwaitingReview = { series_id, status: 'awaiting_review', stage, payload }
Done           = { series_id, status: 'done', stage, audio_manifest }

// Command body for /approve /edit /submit /regenerate
Command = { action: 'approve'|'edit'|'submit'|'regenerate', note: '', data: {} | null }

// Per-stage `payload` shapes
extract      → { genre, theme, tone, language, setting, logline, characters }
clarify      → { questions: [{question, options:[{label,detail,recommended}], allow_free_text}] }  // exactly 4, see §4a
blueprint    → { blueprint, characters }
ep_config    → { recommended_ep_count, rationale, minutes_bounds: [5,15] }
episode_plan → { episodes, ep_count, ep_minutes }
voice_cast   → { voice_cast, reasons, voices }
```

**`data` keys the backend will accept** (anything else is silently dropped):
`genre theme tone language setting logline characters clarification
clarification_answers blueprint recommended_ep_count ep_count ep_minutes
episodes scripts voice_cast sound_plans`

---

## 7. Wiring: which file calls what

`VITE_API_BASE` (default `http://localhost:8000`) is the only config. The backend already
allows CORS from `localhost:5173`, so no Vite proxy is needed.

### 7a. The API layer

| File | Owns | Talks to |
|---|---|---|
| `src/api/client.js` | `get/post/put/patch/del` + `apiUrl()`. Normalises errors into `{status, message}`; detects 429 as a rate-limit error | — |
| `src/api/studio.js` | All **disk** reads/writes. Cheap, retryable | `/studio/*` → `app/api_store.py` |
| `src/api/series.js` | All **pipeline** calls. Expensive, ordered | `/series/*` → `app/main.py` |
| `src/api/flow.js` | The **wizard driver** — chains `series.js` calls in the right order and returns the payload the UI needs. The only place that knows the stage sequence | both |

### 7b. Page → function → endpoint → backend → what it costs

| UI action | Frontend | HTTP | Backend entry | Triggers LLM/TTS? | Writes on disk |
|---|---|---|---|---|---|
| Dashboard loads | `Dashboard.jsx` → `studio.listSeries()` | `GET /studio/series` | `api_store.list_series` → `store.list_series` | No | — |
| Delete a series | `Dashboard.jsx` → `studio.deleteSeries(id)` | `DELETE /studio/series/{id}` | `store.delete_series` | No | removes folder |
| Submit the idea | `IdeaWizard` → `flow.startSeries({idea})` | `POST /series` | `main.create_series` → `gen_extract` | **LLM** (extract) | `input/idea.txt`, `blueprint/*.json`, `characters/*.json`, `series.json` |
| (immediately after) | `flow.startSeries` auto-approves | `POST /series/{id}/approve` | `review_extract` → `gen_clarify` | **LLM** (clarify) | `input/clarification.json` |
| Answer the 4 questions | `flow.submitAnswers(id, answers)` | `POST /series/{id}/submit` | `review_clarify` → `gen_blueprint` | **LLM** (blueprint) | `input/clarification_answers.json`, `blueprint/*`, `characters/*` |
| Confirm card shown | `ConfirmCard` → `studio.confirmCard(id)` | `POST /studio/.../confirm-card` | **B3** | **LLM** (1 cheap call) | `series.json` (title) |
| Confirm pressed | `Building.jsx` → `flow.buildSeries(id, {ep_count, ep_minutes})` | `approve` → `submit` → `approve` (3 calls) | `gen_ep_config`, then `gen_episode_plan` | **LLM** ×2 | `episodes/epNN/outline.json` for every episode |
| Ideaboard loads | `Ideaboard.jsx` → `studio.getSeries(id)` | `GET /studio/series/{id}` | `api_store.get_series` | No | — |
| Voice list opens | `VoicePicker` → `studio.listVoices()` | `GET /studio/voices` | `config.VOICES` | No | — |
| ▶ preview a voice | `VoicePicker` → `studio.voiceSampleUrl(v)` in an `<audio>` | `GET /studio/voices/{v}/sample` | **B4** | **TTS** first time only, then cached | `assets/voice_samples/{v}.wav` |
| Pick a voice | `CharacterCard` → `studio.patchCharacter(id, key, {voice_id})` | `PATCH /studio/.../characters/{key}` | `store.save_character` | No | that character's JSON |
| Edit character text | same | same | same | No | that character's JSON |
| Edit plot/theme | `Ideaboard` → `studio.patchBlueprint(id, {...})` | `PATCH /studio/.../blueprint` | merge into `plot/theme/genre.json` | No | those files |
| **Generate episode** | `EpisodeRow` → `studio.generateEpisode(id, n)` | `POST /studio/.../episodes/{n}/generate` | **B2** → `jobs.start(...)` | **LLM** (script, sound) + **TTS** (every line) | `script.json`, `lines/*.wav`, `epNN_voices.wav`, `sound_plan.json`, `epNN_final.wav`, `audio.json` |
| Poll progress | `EpisodeRow` → `studio.getJob(jobId)` every 2s | `GET /studio/jobs/{id}` | in-memory dict | No | — |
| Episode page loads | `Episode.jsx` → `studio.getEpisode(id, n)` | `GET /studio/.../episodes/{n}` | `store.load_episode` | No | — |
| Play the audio | `AudioPlayer` `src={studio.audioUrl(id,n)}` | `GET /studio/.../episodes/{n}/audio` | `FileResponse` | No | — |
| Save script edits | `ScriptEditor` → `studio.putScript(id, n, lines)` | `PUT /studio/.../episodes/{n}/script` | `store.save_episode_script` | No | `script.json`; **drops `final`, sets `stale`** |
| Re-render audio | `EpisodeRow`/`Episode` → `studio.generateEpisode(id, n)` | same as Generate | **B2** | **TTS** for *changed lines only* (content-hash cache) | as above |
| Mic: stop recording | `MicPage` → `studio.transcribe(blob)` | `POST /studio/transcribe` | **B5** | **LLM** (audio→text) | — |
| Mic: keep the audio | `studio.uploadInputAudio(id, blob)` | `POST /studio/.../input/audio` | `store.save_source_audio` | No | `input/source.wav` |

### 7c. `flow.js` — the only stateful client code

The wizard's three backend touchpoints, each awaited in order (never fire-and-forget: every
call resumes a paused graph):

```js
// 1. On "Next" in the editor. Returns the clarify questions (possibly []).
startSeries({ idea, transcript })
  → POST /series                       // stage: extract
  → POST /series/{id}/approve          // stage: clarify
  → { seriesId, questions }            // always exactly 4 (see §4a)

// 2. After all 4 questions are answered.
submitAnswers(seriesId, answers)
  → POST /series/{id}/submit {data:{clarification_answers}}
  → { stage: 'blueprint' }             // blueprint now exists on disk

// 3. On Confirm. Runs behind the loading screen.
buildSeries(seriesId, { ep_count, ep_minutes })
  → POST /approve                      // blueprint → ep_config
  → POST /submit {data:{ep_count, ep_minutes}}   // → episode_plan
  → POST /approve                      // plan approved; STOP HERE
  → { done: true }                     // ideaboard is ready
```

**After step 3 the wizard never calls `/series/*` again.** The ideaboard and episode pages
are entirely `/studio/*`. Two consequences worth knowing:
- A backend restart mid-wizard loses the in-flight graph (the folder survives, the *paused
  interrupt* does not) → the UI must offer "start over" rather than hang.
- Once on the ideaboard, a restart is harmless.

### 7d. Query keys & invalidation

| Key | Source | Invalidated by |
|---|---|---|
| `['series']` | `studio.listSeries()` | create, delete, any episode completion |
| `['series', id]` | `studio.getSeries(id)` | character/blueprint patch, episode completion |
| `['episode', id, n]` | `studio.getEpisode(id, n)` | script save, episode completion |
| `['voices']` | `studio.listVoices()` | never (static) |
| `['job', jobId]` | `studio.getJob()` | polled at 2s while `running`; stops on `done`/`error` |

---

## 8. Folder Structure

```
frontend/
├── index.html
├── vite.config.js
├── tailwind.config.js
├── postcss.config.js
├── package.json
└── src/
    ├── main.jsx                # router + QueryClient providers
    ├── App.jsx                 # routes + AnimatePresence shell
    ├── index.css               # tailwind + design tokens
    ├── api/
    │   ├── client.js           # fetch wrapper, base URL, error normalisation
    │   ├── studio.js           # /studio/* — disk reads & writes
    │   ├── series.js           # /series/*  — pipeline calls
    │   └── flow.js             # wizard driver (§7c)
    ├── store/
    │   └── wizard.js           # zustand: mode, idea, transcript, questions, answers, draft
    ├── components/
    │   ├── ui/                 # Button, Card, Field, Chip, Popover, Spinner, Toggle, Slider
    │   ├── TypingText.jsx
    │   ├── QuestionCard.jsx
    │   ├── ConfirmCard.jsx
    │   ├── CharacterCard.jsx
    │   ├── VoicePicker.jsx
    │   ├── EpisodeRow.jsx
    │   ├── AudioPlayer.jsx
    │   └── ScriptEditor.jsx
    ├── pages/
    │   ├── Dashboard.jsx
    │   ├── NewSeries.jsx
    │   ├── IdeaWizard.jsx      # serves /new/write and /new/mic
    │   ├── Building.jsx
    │   ├── Ideaboard.jsx
    │   └── Episode.jsx
    └── lib/
        ├── emotion.js          # split "[Fear] text" → {tag, text}
        └── witty.js            # loading-screen lines
```

---

## 9. Page Specs

### 9.1 Dashboard `/`
- `studio.listSeries()` → grid of cards: **title**, genre chip, `n episodes`, `n ready`, relative time.
- Empty state: one centered line + "Create your first series".
- One primary action: **New series** → `/new`.
- Motion: cards stagger-fade in (40ms apart); shared `layoutId` expands a card into the ideaboard header.

### 9.2 New Series `/new`
- Two full-height panels: **Write** (type it) / **Mic** (speak it), each with a one-line descriptor. Hover raises one and desaturates the other. Nothing else on screen.

### 9.3 Write `/new/write`
Three steps in one shell, `AnimatePresence` slide+fade between them:
1. **Editor** — fullscreen textarea, no chrome. Live word count. **Next** enables at ~40 words.
2. **Questions** — Next calls `flow.startSeries()`; render the **4** question cards one at a time (option chips + a free-text field). The **recommended option is pre-selected**, so Next is never blocked. Progress dots show `1 of 4`.
3. **Confirm** — `studio.confirmCard()` fills: **title, genre, setting, narrator toggle, episode count stepper, avg length slider (5–15)**. Confirm → `/new/building`.

### 9.4 Mic `/new/mic`
- `MediaRecorder` starts after a permission state. Centered record indicator with an amplitude ring from an `AnalyserNode` — the one ornament that's actually informative.
- Stop → `studio.transcribe(blob)` → editable transcript → the **identical** 4-question + confirm steps (options rendered as cards, recommended one pre-selected).

### 9.5 Loading `/new/building`
- Runs `flow.buildSeries()` (3 sequential calls).
- `TypingText` cycles witty lines (~45ms/char, 1.2s hold, backspace out): *"Making you the next Shakespeare…" · "Adding salt to your story…" · "Auditioning your characters…" · "Teaching the villain to whisper…" · "Hiding a cliffhanger in episode 3…"*
- Thin **indeterminate** bar — no fake percentage.
- Done → `/series/:id`. Error → inline retry, never a dead end.

### 9.6 Ideaboard `/series/:id`
Two columns on desktop, one on mobile.
- **Story cards:** Plot (`main_storyline`), Theme, Genre, Tone, Setting (`story_world`). Long text clamps to 4 lines with "more" — the main anti-congestion lever.
- **Characters:** card grid. Face = name + role + gender. Click expands (shared layout) to personality, vocal signature, description, relationships, and a **voice row**.
  - **Voice picker popover:** 30 `name · style` rows, each with ▶ playing `voiceSampleUrl`. Selecting → `studio.patchCharacter(..., {voice_id})`, optimistic.
- **Episodes:** rows of number, title, one-line summary, status chip.
  - Expand → summary, main events, emotional focus, cliffhanger.
  - **Generate episode** → `studio.generateEpisode()` → poll `['job']` → inline steps (*writing script → voicing lines 4/28 → adding sound → mixing*). When `ready`, the button becomes **Preview** → episode page.
  - Status comes from disk, so progress survives a reload.

### 9.7 Episode `/series/:id/episodes/:n`
- **Top:** audio player — play/pause, scrubber, time, download. `src = studio.audioUrl(id, n)`.
- **Below:** script editor — one row per line: speaker label (color-keyed per character), editable text, and the emotion tag as a **chip** parsed off the front (`lib/emotion.js`) so tags read as metadata, not literal `[Fear]` noise.
- Save → `studio.putScript()`. That marks audio `stale`, revealing **Re-render audio** (only changed lines are re-billed, thanks to the content-hash cache).

---

## 10. Design Tokens

```
Type    12 / 14 / 16 / 20 / 32px   — one sans (Inter), weights 400/500/600 only
Space   4 / 8 / 12 / 16 / 24 / 40 / 64
Radius  10px cards · 8px controls · 999px chips
Color   bg #0B0B0C · surface #141416 · border #232327
        text #ECECEE · muted #8A8A93 · accent #6C7BFF
        (dark-first: an audio tool reads better dark; one accent only)
Motion  fast 180ms · base 240ms · slow 320ms · ease [0.22, 1, 0.36, 1]
```

| Where | Motion |
|---|---|
| Route change | 8px slide + fade, 240ms |
| Wizard step | horizontal slide + fade, `AnimatePresence mode="wait"` |
| Dashboard card → ideaboard | shared `layoutId` expand |
| Character card expand | shared-layout size morph |
| Popover | scale 0.97→1 + fade, 180ms |
| Loading | typing + caret blink; indeterminate bar sweep |
| List entry | stagger children 40ms |

Respect `prefers-reduced-motion`: swap all of it for plain opacity fades.

---

## 11. Async & Error Strategy

- Wizard calls are **sequential and awaited** in `flow.js` — each resumes a paused graph, so order matters and retries are unsafe.
- Episode generation polls `['job', id]` at 2s while `running`, stops on `done`/`error`, then invalidates `['series', id]` and `['episode', id, n]`.
- **Rate limits are a first-class state.** Free-tier TTS is ~3 req/min; a 429 surfaces as *"Voice generation is rate-limited — retrying"*, not a generic failure. The backend already retries with backoff, so the job simply takes longer.
- Every mutation shows its error inline, next to its control. No toast-only failures.
- A listed series whose graph state is gone (restart) must render as **"needs rebuild"**, never crash on a 404.

---

## 12. Risks & Honest Limitations

| Risk | Impact | Mitigation |
|---|---|---|
| **Free-tier TTS ~3 req/min** | A 30-line episode ≈ 10 min to voice | Per-episode generation; job progress with line counts; on-demand voice samples; 429 as real state |
| `MemorySaver` is in-process | Restart loses **graph** state | **Largely solved:** the folder is the source of truth and `store.hydrate()` rebuilds state. Only an in-flight, mid-interrupt wizard run is lost. `SqliteSaver` would close the gap |
| Confirm card wants pre-blueprint recommendations | Not available at that point | Extra cheap Flash-Lite call (B3) |
| Graph does all episodes at once | Wrong UX + quota blowout | Wizard stops at `episode_plan`; per-episode functions already exist and persist themselves |
| Clarify count drifting from 4 | Wizard's fixed 4-step flow breaks | **Solved:** schema pins exactly 4 + a backend guard pads/trims. One option is always `recommended` and pre-selected |
| Long LLM steps with no progress signal | Loading feels broken | Designed loading state; indeterminate bar, never a fake percentage |
| Script edits invalidate rendered audio | Stale audio silently served | **Handled:** `PUT .../script` drops `final`, sets `stale`; UI offers re-render |
| No TypeScript | Shape drift fails at runtime, not build | Confine shape knowledge to `src/api/*`; default every optional field |
| No auth / multi-user | Everything is global | Fine for a hackathon; noted rather than faked |

---

## 13. Resolved Decisions

1. **Series title — auto-generated, auto-updated.** The LLM derives it; the user never has to invent one. Produced by the confirm-card call, stored in `series.json`, and **refreshed whenever the blueprint changes** so a regenerated story gets a matching title. Still editable via `PATCH /studio/series/{id}`. Dashboard shows `title`, falling back to `logline`, then the id.
2. **Voice samples — one fixed sentence, rendered on demand, cached forever.** Pre-generating all 30 would take ~10 min at the free-tier rate. The first preview of a voice renders it (1 call) and caches to `assets/voice_samples/{voice}.wav`; later previews are instant. A tools script can warm all 30 offline.
3. **Narrator toggle — hard-forbid.** "No narrator" makes the script prompt forbid `narration` lines outright; scene-setting must be carried by dialogue. Honouring it loosely would make the control meaningless.
4. **Continue the story — deferred.** The backend supports it, but it isn't one of the 7 pages. The ideaboard gets a quiet "Extend series" affordance later.

---

## 14. Build Order

Goal: **a working app where you can generate real audio yourself.** The per-episode
generate path is therefore not optional — it's the point.

| Step | What | Why now |
|---|---|---|
| **B1** | `app/jobs.py` — thread + status dict | Episode generation takes minutes; HTTP can't block |
| **B2** | `POST .../episodes/{n}/generate` + `GET /studio/jobs/{id}` | The Generate button and its progress UI |
| **B3** | `POST .../confirm-card` | Confirm needs title + recommended count before the blueprint |
| **B4** | On-demand cached voice samples | Previews without a 10-minute warm-up |
| **F1** | Vite + React + Tailwind + Router + Query + Zustand + Framer Motion; tokens, `ui/` primitives, `api/` layer | Foundation |
| **F2** | Dashboard + New Series | Entry points; works against real data immediately |
| **F3** | Write wizard + `flow.js` | The idea path |
| **F4** | Building screen + typing animation | Covers the 3-call chain |
| **F5** | Ideaboard: story cards, characters, voice picker, episode rows + generate/progress | The core screen |
| **F6** | Episode page: player + script editor | **Hear the result** |
| **B5/F7** | `POST /studio/transcribe` + Mic page | Last; only genuinely new AI capability |

**Deliberately deferred:** reduced-motion polish, continuation UI, sound-cue editing,
per-line re-render, auth.

---

## 15. Implementation Status

The basic frontend is now implemented in `frontend/` using React + JavaScript.

- **Built:** all seven routes, dashboard, write and mic entry paths, exact-four-question
  wizard, confirmation card, loading screen, ideaboard, inline blueprint editing,
  character voice selection and previews, per-episode background generation with job
  polling, episode audio playback/download, and script editing/re-rendering.
- **Connected:** `/series/*` only drives the ordered creation wizard. `/studio/*` reads
  and edits the durable series folder, casts voices, starts episode jobs, serves audio,
  and transcribes microphone input.
- **Important correction:** `flow.buildSeries()` stops when `episode_plan` is returned.
  It does **not** approve that review, because approving it would run the legacy
  all-episode script node. The Generate button is the only trigger for script + TTS.
- **Verified:** `npm run build` succeeds and the Python backend suite passes. The Vite
  app and FastAPI health endpoint both respond locally.
- **Multi-key TTS:** `GEMINI_API_KEYS` supplies a de-duplicated key pool. Every key has
  its own client, lock, and throttle clock; episode lines render concurrently through a
  bounded worker pool and are reassembled in original script order.
