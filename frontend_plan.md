# AI Creator Copilot — Frontend Plan

> **Goal:** a minimal, intentional, fluid React + TypeScript frontend over the existing
> LangGraph/FastAPI backend. Basic on purpose — clean structure now, restyle later.
> **Read with:** `plan.md` (product/pipeline rationale) and `backend.md` (API contract).

---

## 1. Design Principles

The brief is *minimal, clean, intentional, not congested, fluid*. Concretely:

| Principle                                  | How it shows up                                                                                                    |
| ------------------------------------------ | ------------------------------------------------------------------------------------------------------------------ |
| **One decision per screen**          | Never stack the idea editor, questions, and confirm card at once. They're sequential steps in the same page shell. |
| **Generous negative space**          | Max content width ~720px for reading/writing surfaces, ~1100px for the ideaboard grid. Nothing edge-to-edge.       |
| **Few type sizes, few colors**       | 5-step type scale, 1 accent color, near-monochrome surfaces. No decorative gradients or drop shadows.              |
| **Motion explains, never decorates** | Transitions carry continuity (a card grows into a page, a step slides in). 180–320ms, one easing curve.           |
| **Progressive disclosure**           | Character details, episode plot, and sound cues live behind a click — not on the surface.                         |
| **Honest loading**                   | Generation takes real time (LLM + TTS). Loading screens are a designed state, not a spinner afterthought.          |

**Anti-goals:** no sidebars, no dense toolbars, no dashboards-with-widgets, no modal stacking.

---

## 2. Stack

| Concern      | Choice                                   | Why                                                                                                |
| ------------ | ---------------------------------------- | -------------------------------------------------------------------------------------------------- |
| Build        | **Vite + React 18 + TypeScript**   | Fast, zero-config, standard.                                                                       |
| Routing      | **React Router v6**                | 7 pages, nested episode route.                                                                     |
| Server state | **TanStack Query**                 | Generation is async and polled; caching + invalidation for free.                                   |
| Wizard state | **Zustand** (one small store)      | The write/mic flow spans steps and must survive step changes without prop-drilling.                |
| Animation    | **Framer Motion**                  | Layout animations +`AnimatePresence` for page/step transitions. This is the "fluid" requirement. |
| Styling      | **Tailwind CSS**                   | Enforces the constrained token set; fastest path to a clean minimal look.                          |
| Audio        | native`<audio>` + a thin custom player | Basic preview only; no waveform library needed yet.                                                |
| Mic capture  | `MediaRecorder` API                    | Records to webm/opus blob, uploaded for transcription.                                             |

No component library. A handful of hand-rolled primitives keeps it minimal and un-generic.

---

## 3. The 7 Pages

| # | Route                       | Page                 | Purpose                                                                                                |
| - | --------------------------- | -------------------- | ------------------------------------------------------------------------------------------------------ |
| 1 | `/`                       | **Dashboard**  | All series as cards (name + genre + episode count). Click → ideaboard. Plus a prominent "New series". |
| 2 | `/new`                    | **New Series** | Two large choices:**Write** and **Mic**. Nothing else.                                     |
| 3 | `/new/write`              | **Write**      | Fullscreen text editor → Next → 5 questions (same page) → confirm card (same page).                 |
| 4 | `/new/mic`                | **Mic**        | Recording UI → transcript → 5 questions as cards → confirm card.                                    |
| 5 | `/new/building`           | **Loading**    | Typing-text animation with witty lines while the blueprint + episode plan generate.                    |
| 6 | `/series/:id`             | **Ideaboard**  | Plot/tone/theme/setting cards, character cards (with voice picker popup), episode list.                |
| 7 | `/series/:id/episodes/:n` | **Episode**    | Audio player on top, generated script in an editor below.                                              |

Pages 3 and 4 are **the same wizard with two entry modes** — they converge on identical
question + confirm steps. Implemented as one `<IdeaWizard mode="write" \| "mic">`.

---

## 4. Flow → Backend Mapping (the critical part)

The backend is a staged human-in-the-loop graph:

```
extract → clarify → blueprint → ep_config → episode_plan → script → voice_cast → audio → sound_design → mix → deliver
```

Your UX doesn't visit those stages one-for-one. The mapping:

| UI step                    | Backend action                                                                                                                  | Notes                                                                                                                                       |
| -------------------------- | ------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------- |
| Submit idea (write or mic) | `POST /series {idea}` → pauses at **extract** review                                                                   | Response payload holds genre/setting/logline/characters. Frontend**caches it** for the confirm card.                                  |
| — (invisible)             | `POST /series/{id}/approve` → pauses at **clarify** review                                                             | Extract is auto-approved; the user never sees a separate "confirm metadata" screen. Its data resurfaces in the confirm card.                |
| 5 questions                | Render`payload.questions` (0–5, each with `options[]` + `allow_free_text`)                                               | If the LLM returns 0 questions the backend**auto-skips** clarify — the UI must handle "no questions" by jumping straight to confirm. |
| Confirm card               | `POST /series/{id}/submit {data:{clarification_answers}}` + edits                                                             | Then the graph runs blueprint → pauses at**blueprint** review.                                                                       |
| Loading screen             | auto-`approve` blueprint → **ep_config** → `submit {ep_count, ep_minutes}` → **episode_plan** → `approve` | Three round-trips happen behind the typing animation.                                                                                       |
| Ideaboard                  | `GET /series/{id}/state`                                                                                                      | Reads`blueprint`, `characters`, `episodes`. **Pipeline intentionally rests here.**                                              |
| Character voice pick       | `POST /series/{id}/edit {data:{voice_cast}}`                                                                                  | Stored before any episode is generated.                                                                                                     |
| "Generate episode"         | **NEW** per-episode endpoint                                                                                              | See §5 — the stock graph does all episodes at once, which we must not do.                                                                 |
| Episode page               | `GET /series/{id}/state` + audio URL                                                                                          | Script from`scripts["N"]`, audio from `audio_manifest["N"]`.                                                                            |

### Key architectural decision: stop the graph at `episode_plan`

The stock graph generates **scripts for every episode**, then **TTS for every line of every
episode**, in one unstoppable run. That is wrong for this UI (which has a per-episode
"Generate" button) and catastrophic on the free tier (TTS is ~3 requests/minute).

**So:** the wizard drives the graph only through `extract → clarify → blueprint → ep_config → episode_plan`.
Everything after (script, voices, audio, sound design, mix) becomes an **on-demand,
per-episode service** that reuses the exact same node functions scoped to one episode.
Voice casting moves onto the ideaboard character cards instead of being its own gate.

---

## 5. Backend Status — what now exists

The backend stores everything in a per-series folder (`output/<series_id>/`) which is the
**source of truth**; `/studio/*` endpoints read and write it directly. See `plan.md` §4a.

### Built — the frontend can use these today

| Endpoint | Purpose |
|---|---|
| `GET /studio/series` | Dashboard list: `series_id, title, genre, stage, episode_count, generated_count, updated_at` |
| `GET /studio/series/{id}` | Everything the ideaboard needs: `index`, `input`, `blueprint`, `characters`, `episodes[{number,status,...outline}]` |
| `PATCH /studio/series/{id}` | Edit `title`, `include_narrator`, `ep_count`, `ep_minutes` |
| `DELETE /studio/series/{id}` | Remove a series |
| `GET/PATCH /studio/series/{id}/blueprint` | Read / merge-edit `plot.json`, `theme.json`, `genre.json` |
| `GET /studio/series/{id}/characters` | All character files (narrator first, then alphabetical) |
| `PATCH /studio/series/{id}/characters/{key}` | Edit one character — incl. **`voice_id`** and **`gender`**. `key` is the slug or `narrator`. Renames move the file. |
| `GET /studio/series/{id}/episodes` | Episode rows with **`status`** |
| `GET /studio/series/{id}/episodes/{n}` | `outline`, `script`, `sound_plan`, `audio`, `status` |
| `PUT /studio/series/{id}/episodes/{n}/script` | Save creator script edits (**auto-marks audio stale**) |
| `PUT /studio/series/{id}/episodes/{n}/outline` | Save outline edits |
| `GET /studio/series/{id}/episodes/{n}/audio` | Stream / download the episode WAV |
| `GET /studio/voices` | All 30 voices as `{id, style}` |
| `GET /studio/voices/{id}/sample` | Voice preview clip (503 until pre-generated) |
| `POST /studio/series/{id}/input/audio` | Store a raw mic recording into `input/` |

**Episode `status`** drives the ideaboard row UI and is derived from disk, so it survives
reloads: `planned` -> `scripted` -> `voiced` -> `ready`.

`POST /series` now also accepts `title` and `transcript`, and seeds the folder before the
first LLM call, so a series exists on disk even if generation fails.

### Still missing — build before the relevant phase

| # | Need | Proposed | Blocks |
|---|---|---|---|
| 1 | **Voice sample generation** | `tools/build_voice_samples.py` rendering all 30 voices offline into `assets/voice_samples/`. The endpoint exists but 503s until this runs. **Must be offline** — 30 live TTS calls would blow the ~3 req/min limit instantly. | Voice picker (§8.6) |
| 2 | **Mic -> text** | `POST /studio/transcribe` (multipart). `gemini-3.1-flash-lite` accepts audio input, so no extra model. | Mic page (§8.4) |
| 3 | **Per-episode generate** | `POST /studio/series/{id}/episodes/{n}/generate` -> `202` + job id. The node functions are **already refactored** for this: `gen_script_for_episode`, `render_episode_audio(progress=...)`, `design_episode_sound`, `mix_episode` each operate on ONE episode and persist themselves. | Generate button (§8.6) |
| 4 | **Job status** | `GET /studio/jobs/{job_id}` -> `{state, step, done, total, message}`. `render_episode_audio` already accepts a `progress(done, total)` callback to feed it. | Progress UI |
| 5 | **Confirm-card data** | `POST /studio/series/{id}/confirm-card` — one cheap Flash-Lite call returning `{title, genre, setting, narrator_suggested, recommended_ep_count, recommended_ep_minutes}`, because `ep_config` only runs *after* the blueprint. | Confirm step (§8.3) |
| 6 | **`include_narrator` honoured** | The field is storable and patchable, but the blueprint prompt does not yet consume it. | Narrator toggle |

> **Still true:** the wizard must **stop the pipeline at `episode_plan`**. The stock graph's
> `script` / `audio` / `mix` stages run over *all* episodes at once, which contradicts the
> per-episode Generate button and would blow the TTS quota.


## 6. TypeScript Types (mirror of backend schemas)

`src/api/types.ts` — hand-mirrored from `app/schemas.py` / `app/state.py`.

```ts
export type Stage =
  | 'extract' | 'clarify' | 'blueprint' | 'ep_config' | 'episode_plan'
  | 'script' | 'voice_cast' | 'audio' | 'sound_design' | 'mix' | 'deliver';

export type Action = 'approve' | 'edit' | 'submit' | 'regenerate';

export interface CommandBody {
  action: Action;
  note?: string;
  data?: Record<string, unknown> | null;
}

export interface ReviewResponse {
  series_id: string;
  status: 'awaiting_review';
  stage: Stage;
  payload: Record<string, unknown>;
}
export interface DoneResponse {
  series_id: string;
  status: 'done';
  stage: Stage;
  audio_manifest: Record<string, AudioManifestEntry>;
}
export type AdvanceResponse = ReviewResponse | DoneResponse;

export interface CharacterProfile {
  name: string;
  role: string;
  description: string;
  personality: string;
  relationships: string[];
  vocal_signature: string;   // pace/pitch/tics
  is_narrator: boolean;
  gender?: string;           // NEW (backend addition #9)
}

export interface ClarifyOption { label: string; detail: string; }
export interface ClarifyQuestion {
  question: string;
  options: ClarifyOption[];      // may be empty → free-text only
  allow_free_text: boolean;
}

export interface Blueprint {
  logline: string;
  story_world: string;
  main_storyline: string;
  tone: string;
  theme: string;
  characters: CharacterProfile[];
}

export interface EpisodePlanItem {
  number: number;
  title: string;
  summary: string;
  main_events: string[];
  emotional_focus: string;
  cliffhanger: string;
}

export interface ScriptLine {
  type: 'narration' | 'dialogue';
  speaker: string;               // character name or "Narrator"
  text: string;                  // may START with an [Emotion] tag; usually none
  sfx: string[];                 // usually []
  music: string | null;          // usually null
}

export interface AudioManifestEntry {
  voices: string;
  final?: string;
  offsets?: number[];
  total_ms?: number;
  line_files?: string[];
}

/** scripts and audio_manifest are keyed by episode number AS A STRING. */
export interface SeriesState {
  series_id: string;
  idea: string;
  title?: string;                // NEW
  include_narrator?: boolean;    // NEW
  genre: string; theme: string; tone: string; language: string; setting: string;
  logline: string;
  characters: CharacterProfile[];
  clarification: { questions: ClarifyQuestion[] };
  clarification_answers: Array<{ question: string; answer: string }>;
  blueprint: Blueprint;
  recommended_ep_count: number;
  ep_count: number;
  ep_minutes: number;            // 5–15
  episodes: EpisodePlanItem[];
  scripts: Record<string, ScriptLine[]>;
  voice_cast: Record<string, string>;   // character → voice id
  sound_plans: Record<string, unknown>;
  arcs: string[];
  stage: Stage;
  approvals: Record<string, boolean>;
  audio_manifest: Record<string, AudioManifestEntry>;
}
```

**Three contract traps to respect:**

1. `scripts` and `audio_manifest` keys are **strings** (`"1"`), not numbers.
2. Character count is **never fixed** — always render the array as-is.
3. Most `ScriptLine.text` values have **no** emotion tag. Parse tags optionally, never require them.

---

## 7. Folder Structure

```
frontend/
├── index.html
├── vite.config.ts
├── tailwind.config.ts
├── tsconfig.json
└── src/
    ├── main.tsx                # router + QueryClient providers
    ├── index.css               # tailwind + design tokens
    ├── api/
    │   ├── client.ts           # fetch wrapper, base URL, error normalisation
    │   ├── types.ts            # §6
    │   ├── series.ts           # create/state/approve/edit/submit/regenerate/continue
    │   ├── studio.ts           # list, transcribe, voices, samples, episode generate, jobs
    │   └── flow.ts             # the wizard driver (auto-advance logic, §4)
    ├── store/
    │   └── wizard.ts           # zustand: mode, idea, extract cache, answers, confirm draft
    ├── components/
    │   ├── primitives/         # Button, Card, Field, Chip, Sheet, Popover, Spinner
    │   ├── motion/             # PageTransition, StepTransition, TypingText
    │   ├── QuestionCard.tsx
    │   ├── ConfirmCard.tsx
    │   ├── CharacterCard.tsx
    │   ├── VoicePickerPopover.tsx
    │   ├── EpisodeRow.tsx
    │   ├── AudioPlayer.tsx
    │   └── ScriptEditor.tsx
    ├── pages/
    │   ├── Dashboard.tsx
    │   ├── NewSeries.tsx
    │   ├── IdeaWizard.tsx      # serves /new/write and /new/mic
    │   ├── Building.tsx
    │   ├── Ideaboard.tsx
    │   └── Episode.tsx
    └── lib/
        ├── emotion.ts          # parse/strip [Emotion] tags for display
        └── witty.ts            # loading-screen lines
```

---

## 8. Page Specs

### 8.1 Dashboard `/`

- `GET /studio/series` → grid of cards: **title**, genre chip, `n episodes`, relative updated-at.
- Empty state: a single centered line + "Create your first series".
- One primary action: **New series** → `/new`.
- Motion: cards stagger-fade in (40ms apart). Clicking a card uses a shared `layoutId` so it
  expands into the ideaboard header — the continuity cue.

### 8.2 New Series `/new`

- Two full-height choice panels: **Write** (type it) / **Mic** (speak it), each with a one-line
  descriptor. Hover raises and desaturates the sibling. Nothing else on screen.

### 8.3 Write `/new/write`

Three sequential steps in one shell, `AnimatePresence` crossfade+slide between them:

1. **Editor** — fullscreen textarea, no chrome, placeholder prompting for detail. Live word count
   bottom-right. Sticky **Next** enables at a sane minimum (~40 words).
2. **Questions** — `POST /series` runs on Next; render returned `payload.questions` as one card at
   a time (option chips + a free-text field when `allow_free_text`). Progress dots, 1‑of‑N.
3. **Confirm** — `POST /studio/series/{id}/confirm-card`; editable fields:
   **title, genre, setting, narrator (toggle), episode count (stepper), avg length (slider 5–15)**.
   Confirm → §8.5.

### 8.4 Mic `/new/mic`

- Auto-starts `MediaRecorder` on mount (after a permission prompt state). Big centered
  record indicator with an amplitude ring driven by `AnalyserNode` — the one piece of
  ornament that's actually informative.
- Stop → upload to `POST /studio/transcribe` → show editable transcript for a beat → then the
  **identical** questions + confirm steps as Write (`options` rendered as cards, per the brief).

### 8.5 Loading `/new/building`

- Runs the auto-advance chain (§4): approve blueprint → submit ep_config → approve episode_plan.
- `TypingText` cycles witty lines, ~45ms/char, 1.2s hold, backspace out:
  > "Making you the next Shakespeare…" · "Adding salt to your story…" · "Auditioning your
  > characters…" · "Teaching the villain to whisper…" · "Hiding a cliffhanger in episode 3…"
  >
- A thin indeterminate progress bar; **no percentage** (we can't honestly estimate it).
- On completion → `/series/:id`. On error → inline retry, never a dead end.

### 8.6 Ideaboard `/series/:id`

Two-column on desktop, single column on mobile.

- **Left (story):** cards for **Plot** (`blueprint.main_storyline`), **Theme**, **Genre**, **Tone**,
  **Setting** (`story_world`). Long text clamps to 4 lines with "more" — this is the main
  anti-congestion lever.
- **Characters:** responsive card grid. Card face = name + role + gender. Click → expands
  (shared-layout) to reveal **personality, tone/vocal signature, description, relationships**,
  and a **voice row**: current voice + "Change".
  - **Voice popover** — the 30 voices from `GET /studio/voices` as a scrollable list of
    `name · style` rows, each with a ▶ that plays the pre-generated sample. Selecting writes
    through `POST /series/{id}/edit {data:{voice_cast}}` (optimistic update).
- **Episodes:** ordered rows — number, title, one-line summary, state chip.
  - Expand a row → summary, main events, emotional focus, cliffhanger.
  - Action per row: **Generate episode** → `POST /studio/.../generate` (202 + job id) → row shows
    inline step progress from `GET /studio/jobs/{id}` (writing script → voicing lines → adding
    sound → mixing). When done the button becomes **Preview episode** → `/series/:id/episodes/:n`.
  - Row state derives from `scripts[n]` + `audio_manifest[n].final` so it survives reloads.

### 8.7 Episode `/series/:id/episodes/:n`

- **Top:** audio player — play/pause, scrubber, time, download. Source =
  `GET /series/{id}/episodes/{n}/audio`.
- **Below:** script editor — one row per `ScriptLine`: speaker label (color-keyed per character),
  editable text, and emotion tag shown as a small chip parsed off the front of `text`
  (`lib/emotion.ts`), so tags read as metadata rather than literal `[Fear]` noise.
- Save → `POST /series/{id}/edit {data:{scripts}}`. Editing a line marks the episode
  **stale**, offering **Re-generate audio** (TTS caching means only changed lines are re-billed).

---

## 9. Design Tokens

```
Type    12 / 14 / 16 / 20 / 32px   — one sans (Inter), weights 400/500/600 only
Space   4 / 8 / 12 / 16 / 24 / 40 / 64
Radius  10px cards · 8px controls · 999px chips
Color   bg #0B0B0C · surface #141416 · border #232327
        text #ECECEE · muted #8A8A93 · accent #6C7BFF
        (dark-first: an audio-production tool reads better dark; one accent only)
Motion  fast 180ms · base 240ms · slow 320ms · ease [0.22, 1, 0.36, 1]
```

**Animation inventory** (deliberately small):

| Where                       | Motion                                                     |
| --------------------------- | ---------------------------------------------------------- |
| Route change                | 8px slide + fade, 240ms                                    |
| Wizard step                 | horizontal slide + fade via`AnimatePresence mode="wait"` |
| Dashboard card → ideaboard | shared`layoutId` expand                                  |
| Character card expand       | shared-layout height/size morph                            |
| Popover / sheet             | scale 0.97→1 + fade, 180ms                                |
| Loading                     | typing + caret blink; indeterminate bar sweep              |
| List entry                  | stagger children 40<br />ms                                |

Respect `prefers-reduced-motion`: swap all of the above for plain opacity fades.

---

## 10. Async & Error Strategy

- **TanStack Query** keys: `['series']`, `['series', id]`, `['job', jobId]`, `['voices']`.
- Wizard chain calls are **sequential and awaited**, driven by `api/flow.ts` — never fire-and-forget,
  because each backend call resumes a paused graph and order matters.
- Episode generation polls `['job', id]` at 2s while `running`; stops on `done`/`error`;
  invalidates `['series', id]` on completion.
- **Rate limits are a first-class error.** Free-tier TTS is ~3 req/min, so a 429 must surface as
  "Voice generation is rate-limited — retrying in Ns", not a generic failure.
- Every mutation has an explicit error surface inline next to its control. No global toast-only errors.
- `MemorySaver` means **backend restarts lose in-flight series**. The dashboard reads the
  on-disk index, so it must tolerate a listed series whose graph state is gone → show it as
  "needs rebuild" rather than crashing on a 404.

---

## 11. Build Phases

| Phase | Deliverable |
|---|---|
| **0** | Backend §5 remaining: voice samples (#1), confirm-card call (#5). Everything else in §5 is **done**. |
| **1** | Vite + TS + Tailwind + Router scaffold, design tokens, primitives, `api/client.ts` + `types.ts`. |
| **2** | Dashboard + New Series — `GET /studio/series` is live, so this works against real data. |
| **3** | Write wizard: editor → questions → confirm, with `api/flow.ts` auto-advance (needs #5). |
| **4** | Loading screen + typing animation; land on ideaboard. |
| **5** | Ideaboard: story cards, character cards, voice popover (`GET /studio/voices` live; needs #1 for previews). |
| **6** | Backend #3/#4 per-episode generate + jobs; episode rows with progress. |
| **7** | Episode page: player + script editor (`PUT .../script` live, already marks audio stale). |
| **8** | Mic flow (needs #2 transcribe; raw-audio upload already live). |
| **9** | Motion polish, reduced-motion, empty/error states. |

Phases 2–7 deliver a fully usable product with the Write path; Mic is intentionally last
because it depends on the only genuinely new AI capability (transcription).

---

## 12. Risks & Honest Limitations

| Risk | Impact | Mitigation |
|---|---|---|
| **Free-tier TTS ~3 req/min** | A 30-line episode ≈ 10 min to voice | Per-episode (not per-series) generation; job progress UI; pre-generate the 30 voice samples offline; surface 429s as real state. |
| `MemorySaver` is in-process | Server restart loses **graph** state | **Largely solved:** the series folder is the source of truth and `store.hydrate()` rebuilds state from disk, so reads/edits survive a restart. Only an *in-flight, mid-interrupt* wizard run is lost. `SqliteSaver` would close the gap. |
| Confirm card wants pre-blueprint recommendations | Backend can't provide them at that point | Extra cheap Flash-Lite call (§5 #5). |
| Graph does all episodes at once | Wrong UX + quota blowout | Stop the graph at `episode_plan`; per-episode functions already exist and persist themselves. |
| Clarify may return 0 questions | Wizard step would render empty | Detect and skip straight to confirm. |
| Long LLM steps with no progress signal | Loading feels broken | Designed loading state; indeterminate bar, never a fake percentage. |
| Script edits invalidate rendered audio | Stale audio silently served | **Handled:** `PUT .../script` drops `final` and sets `stale`, so the UI can offer a re-render. TTS caching re-bills only changed lines. |
| No auth / multi-user | Everything is global | Acceptable for a hackathon; note it rather than fake it. |

---

## 13. Open Questions

1. **Series title** — the confirm card edits it, but should the dashboard show `title` or `logline`  - it should be automatically updated 
   as the primary label? (Plan assumes `title`, falling back to `logline`.)
2. **Voice samples** — one fixed sample sentence for all 30 voices, or a line from the user's own
   script? (Plan assumes fixed + pre-generated, for rate-limit safety.)
3. **Narrator toggle** — if the user says "no narrator" but the story needs scene-setting, do we
   hard-forbid narration lines or just discourage it in the prompt? (Plan assumes hard-forbid.)
4. **Continue the story** — the backend supports it (`POST /series/{id}/continue`) but the brief's
   7 pages have no entry point. Add it to the ideaboard later?
