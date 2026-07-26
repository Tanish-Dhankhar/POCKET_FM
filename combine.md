# Frontend Combination and Backend Integration Plan

## 1. Goal

Combine the visual direction of `frontend_reference/` with the real, working flows in `frontend/`.

The result will:

- use the reference frontend's black, crimson, white, and charcoal design language;
- keep the current frontend's working API calls, four-question wizard, editable confirmation cards, voice picker, and file-backed persistence;
- use the reference layouts for Dashboard, Write, Ideaboard, and Episode pages;
- add real backend generation for SWOT analysis, genre distribution, theme distribution, story refinement, and episode evaluation;
- never depend on mock series data, fake timers, or browser-only state for persisted content;
- use no images on the Dashboard. Series cards will use typography, borders, and restrained CSS gradients only;
- keep emotion, music, and sound effects sparse. Natural dialogue, silence, and dry scenes remain the default. THIS IS FOR THE FRONTEND ONLY

`frontend_reference/` is a visual and interaction reference. `frontend/` remains the application that is built and run.

## 2. Source-of-truth rules

The combined application will follow these ownership rules:

| Concern                                      | Source of truth                                   |
| -------------------------------------------- | ------------------------------------------------- |
| Visual theme and page composition            | `frontend_reference/src/`                       |
| Routing and live frontend application        | `frontend/src/`                                 |
| Server state fetching and cache invalidation | Current TanStack Query API layer                  |
| Temporary create-series wizard state         | Current Zustand wizard store                      |
| Series, blueprint, characters, and episodes  | `output/<series_id>/` files                     |
| Long-running generation progress             | Backend job API                                   |
| Character voice selection                    | Character JSON file through the current voice API |
| Audio playback timing                        | Episode`audio.json` manifest                    |

The reference `AppContext`, mock series objects, placeholder episode generation, and simulated timeouts will not replace the current real data flow.

## 3. Design system

### 3.1 Colors

Use the reference palette consistently:

```css
--canvas: #000000;
--surface: #0a0a0a;
--surface-raised: #101010;
--surface-soft: #151515;
--border: #262626;
--border-strong: #3a3a3a;
--text: #ffffff;
--text-muted: #a3a3a3;
--text-faint: #737373;
--accent: #e61c38;
--accent-hover: #ff2948;
--accent-soft: rgba(230, 28, 56, 0.12);
--danger: #e61c38;
```

Crimson is reserved for primary actions, active playback, selected options, important status, and small glows. Large solid-red areas should be rare.

### 3.2 Typography

- Use DM Sans or the existing clean sans-serif stack for normal UI.
- Use JetBrains Mono for story editor text, script lines, generated analysis, and board labels where the reference uses it.
- Keep headings large but compact. Avoid placing many headings, chips, and controls in the same row.
- The Ideaboard title can retain the reference's display treatment, but the application must remain readable if the display font is unavailable.

### 3.3 Surfaces and spacing

- Page background: pure black.
- Primary cards: `#0a0a0a`, one-pixel neutral border, 16-24px radius.
- Use generous page gutters and 24-32px card gaps on desktop.
- Keep descriptions short and collapse secondary information until the user opens a card or episode.
- Do not add decorative cover images. CSS gradients and subtle glows are allowed.

### 3.4 Motion

Use Framer Motion for quick, fluid, slightly bubbly transitions:

- button press: 90-140ms scale to `0.97`;
- card hover: 160-220ms, 2-4px lift, border brightening, restrained red glow;
- modal enter: 180-240ms opacity plus 8-14px vertical movement;
- accordion: spring animation with low bounce and no layout jump;
- page content: short stagger only on the first load;
- loading illustrations: continuous, smooth, and not visually frantic.

Every motion component must respect `prefers-reduced-motion`. Reduced-motion mode keeps fades and progress text but removes looping transforms.

## 4. Dependencies and architecture

Keep the current React JavaScript stack:

- React and Vite;
- React Router;
- TanStack Query;
- Zustand;
- Framer Motion;
- Tailwind/CSS already used by the current frontend.

Add:

- `lucide-react` for the reference icon language;
- `recharts` for the genre radar and theme bars.

Do not convert the project to TypeScript. All new frontend files remain `.jsx` or `.js`.

## 5. Route plan

| Route                                         | Screen                    | Main behavior                                                    |
| --------------------------------------------- | ------------------------- | ---------------------------------------------------------------- |
| `/`                                         | Dashboard                 | Lists persisted series and the New Series card                   |
| `/new`                                      | New Series                | Choose Write or Mic                                              |
| `/new/write`                                | Write                     | Enter idea, answer four questions, confirm metadata and tags     |
| `/new/mic`                                  | Voice input               | Keep current voice-recording UI and behavior                     |
| `/new/building`                             | Initial generation loader | Build blueprint and episode plan, then open Ideaboard            |
| `/series/:seriesId`                         | Ideaboard                 | Inspect/edit blueprint, characters, voices, and episodes         |
| `/series/:seriesId/refining?job=:jobId`     | Refinement loader         | Poll the real refinement job and return to the updated Ideaboard |
| `/series/:seriesId/episodes/:episodeNumber` | Episode page              | Edit script, play audio, inspect outline and AI evaluation       |

Episode generation uses a full-screen loader overlay on the Ideaboard. Its job ID is also written into the URL query string so a browser refresh can resume polling instead of starting a duplicate generation job.

## 6. Page-by-page frontend plan

### 6.1 Dashboard

Base the page on `frontend_reference/src/pages/DashboardPage.jsx`.

Required layout:

- retain the reference heading and spacious grid;
- fetch real cards with `GET /studio/series`;
- render the New Series action as the first dashed series card, matching the reference add-card treatment;
- remove the separate New Series button;
- clicking the add card navigates to `/new`;
- clicking a persisted series card navigates to `/series/:seriesId`;
- show title, genre/type, updated time, episode progress, and a compact overflow menu if supported;
- do not render `<img>` elements or remote/local cover art.

Series cards use a deterministic, subtle CSS accent generated from the genre or series ID so the grid has rhythm without introducing images.

States:

- loading: six neutral skeleton cards with no fake titles;
- empty: only the New Series card plus one short invitation;
- error: inline retry state without replacing the whole page;
- deleting a series, if retained, must require confirmation before the existing delete endpoint is called.

### 6.2 New Series

Combine `frontend_reference/src/pages/StudioHomePage.jsx` with the current `frontend/src/pages/NewSeries.jsx`.

Use the reference's centered, icon-led Speak/Write selection and palette, while retaining the current frontend's clearer descriptions and large click targets.

The page contains:

- one compact heading and supporting sentence;
- two equal cards: Write and Mic;
- Lucide icons, not images;
- a subtle crimson spotlight behind the hovered/keyboard-focused option;
- an obvious back link to Dashboard;
- responsive stacking on narrow screens.

The full card is clickable. Write navigates to `/new/write`; Mic navigates to `/new/mic`.

### 6.3 Write page

Base the editor shell on `frontend_reference/src/pages/WritePage.jsx`:

- full-height black page;
- subtle crimson radial background;
- centered large dark editor surface;
- monospaced story text;
- word/character feedback kept visually quiet;
- bottom action bar with Next/Send to AI as the only dominant action.

The page continues to use the current live wizard APIs. It does not use reference mock questions.

#### Question flow

The backend always returns exactly four questions based on the user's actual idea. Each question contains 2-4 options, exactly one recommended option, and free-text support.

Use the modal shell, overlay, and animation from `frontend_reference/src/components/StoryQuestionsModal.jsx`. Inside that shell:

- keep the current `QuestionCard.jsx` structure and behavior exactly;
- keep the recommended badge, selectable options, and custom-answer field;
- change only its colors, borders, focus rings, and hover effects to the reference palette;
- show progress as `Question 1 of 4`;
- prevent advancing until the current question has an answer.

#### Confirmation flow

After all four answers, use the current `ConfirmCard.jsx` structure and behavior, recolored to the reference palette.

The confirmation card includes editable:

- title;
- primary genre;
- setting;
- narrator yes/no;
- number of episodes;
- average episode length from 5 to 15 minutes;
- exactly four genre tags;
- exactly four theme tags.

The recommended episode count and duration remain visibly marked. Tags are generated by the LLM from the initial idea plus the four clarification answers. Users can rename, remove, or replace tags, but cannot continue until there are exactly four non-empty, unique genre tags and four non-empty, unique theme tags.

Confirmed values are passed into the build request and become the persisted starting point for the analysis call.

### 6.4 Voice input page

Keep the current voice page unchanged in layout and interaction.

Only shared global colors/fonts may be inherited if they do not alter recording controls. Its output follows the same four-question and confirmation sequence as Write:

1. source audio is saved;
2. transcript is generated and saved;
3. four LLM questions are generated;
4. answers and metadata/tags are confirmed;
5. the initial generation loader opens.

### 6.5 Initial loading page

Combine the reference `AILoadingScreen.jsx` with the current `Building.jsx` and `TypingText.jsx`.

Keep:

- the reference black/crimson cinematic composition;
- the reference processing/reveal animation;
- the current witty rotating lines, rewritten for clean spelling and tone;
- real API error/retry handling;
- real backend progress text where available.

Suggested rotating lines include:

- `Making you the next Shakespeare...`
- `Adding just enough salt to the story...`
- `Teaching your cliffhangers to misbehave...`
- `Giving every character a secret...`
- `Finding the moment nobody skips...`

The loader starts the build once, polls/awaits the real pipeline, and navigates only after files have been persisted. Reloading must not accidentally create a second series.

### 6.6 Ideaboard

Base the page on `frontend_reference/src/pages/IdeaboardPage.jsx`, while replacing every mock value with API data.

Desktop composition:

- top project/header bar;
- left bento area for story, genre, theme, and characters;
- sticky right Episodes panel around 340px wide;
- fixed or sticky bottom refinement box with safe spacing so it does not cover content.

Tablet/mobile composition:

- cards become one column;
- episodes become a normal full-width section after the board;
- refinement input becomes a bottom sheet-like bar with sufficient page padding;
- modals become scrollable full-height panels.

#### General Plot card and modal

Match the reference Plot & Structure visual and modal. It includes:

- Story Line: logline, main storyline, and structured story beats;
- Setting: time, place, world rules, and atmosphere;
- SWOT Analysis in a 2x2 grid:
  - Strengths;
  - Weaknesses;
  - Opportunities;
  - Threats.

Each SWOT quadrant contains 2-4 concise points generated by a structured LLM call. The UI must label this as creative story analysis, not business certainty.

Edits to story line or setting use `PATCH /studio/series/:id/blueprint`. Direct manual edits mark the SWOT and classifications as stale and offer an explicit Regenerate Analysis action. They do not silently spend another LLM call.

#### Genre card and modal

Match the reference Genre card and genre modal.

Display:

- primary genre;
- short genre description;
- exactly four confirmed genre tags;
- a seven-axis radar/web graph.

The seven axes are fixed and always displayed in this order:

1. Action
2. Drama
3. Comedy
4. Sci-fi
5. Horror
6. Thriller
7. Romance

The backend returns integer percentages from 0-100 and normalizes all seven values to a total of 100. The frontend never invents or randomizes missing values; absent values render as zero. The Recharts implementation uses the reference crimson line/fill, dark polygon grid, readable labels, and restrained glowing vertices.

#### Theme card and modal

Match the reference Theme card and modal, with two deliberate removals:

- no Make Changes button;
- no emotional curve.

Display exactly four theme tags and their percentages as read-only animated bars. Theme percentages are derived from the persisted general plot, are integers from 0-100, and sum to 100. Show a short theme description above the bars.

#### Character cards and popup

Use the reference character grid and popup styling. No generated character pictures are required; use initials, restrained CSS fields, or neutral silhouettes.

Each popup contains:

- Personality;
- Details;
- Physical Persona;
- Backstory;
- Vocal direction;
- Relationships.

Keep the current working voice picker design and behavior inside the reference popup. Voice samples continue to come from the current preview endpoint, and selection persists immediately to that character's JSON file.

The popup must clearly separate editable story information from voice selection. A failed voice update should not discard unsaved text edits.

#### Episodes sidebar

Match the reference right-side episode list.

- Episode 1 is open by default.
- Only one episode needs to be expanded at a time.
- The open card shows summary, emotional focus, cliffhanger, and concise event beats.
- `planned` shows Generate Episode.
- `scripted`, `voiced`, or stale states show the appropriate Continue/Regenerate action.
- `ready` shows Preview Episode.
- generation state is tied to a backend job, not a timeout.

Clicking Generate Episode calls the existing episode-generation endpoint and opens the dedicated generation loader described below.

#### Refine textbox

Add the reference refinement textbox to the bottom of the Ideaboard.

Behavior:

1. user writes a concrete story change;
2. frontend calls `POST /studio/series/:id/refine`;
3. backend records the request before starting work;
4. frontend navigates to `/series/:id/refining?job=:jobId`;
5. loader polls the job;
6. backend updates the blueprint, analysis, characters, and episode plan;
7. completed loader invalidates series queries and returns to the Ideaboard.

The submit action is disabled for empty text and while a job is being created. The UI states that existing generated episodes may become stale if the underlying story changes.

### 6.7 Episode-generation loader

Base this full-screen experience on `frontend_reference/src/components/IdeaRefiningLoader.jsx`.

It should show story fragments becoming structured script/audio, a compact waveform, typewriter copy, and real job stages:

- Writing the script
- Checking sparse emotion direction
- Casting voices
- Planning silence, music, and effects
- Rendering character voices in parallel
- Mixing the episode
- Evaluating the finished script

The loader receives `seriesId`, `episodeNumber`, and `jobId`; polls `GET /studio/jobs/:jobId`; displays backend progress; handles failed jobs with Retry and Back actions; and navigates to the Episode page when ready.

No raw private prompt, API key, or sensitive model output is displayed in the animated text stream.

### 6.8 Episode page

Base the page on `frontend_reference/src/pages/EpisodePage.jsx`.

Keep:

- reference top navigation and title treatment;
- large Audio Preview card;
- crimson play/pause control;
- waveform/progress visualization;
- editable script/dialogue panel;
- Episode Outline panel;
- AI Evaluator Judge panel.

Remove the Emotional Curve panel entirely.

#### Playback-linked script highlighting

As audio plays:

- elapsed waveform bars turn crimson;
- the currently playing dialogue/narration line uses bright crimson text and a subtle accent background;
- completed lines use a dim crimson state;
- upcoming lines remain white/gray;
- seeking immediately recomputes the active line;
- pausing preserves the current highlight;
- stopping resets it.

The frontend uses the actual offsets in `audio.json`, not an estimated words-per-minute timer. A binary search or equivalent lookup maps `audio.currentTime * 1000` to the active rendered line.

#### Script editing

The current working editor and save endpoint remain authoritative. Save behavior:

- saves the full structured line list;
- marks existing audio stale because timing/content no longer matches;
- marks the evaluator result stale;
- offers Regenerate Audio rather than pretending the old audio is current.

#### Emotion tags

Emotion direction is sparse. Most lines have no tag.

An emotion tag is added only when delivery needs to differ meaningfully from the character's established natural voice, for example a sudden break, suppressed panic, an intentional whisper, or an emotional reversal. It is not added merely because a scene has a mood.

The editor renders emotion as a small removable chip beside the speaker rather than visually polluting dialogue text. At the TTS boundary, the backend composes the approved emotion direction into the Gemini TTS prompt. Existing legacy inline `[Emotion]` prefixes remain readable during migration.

#### AI Evaluator Judge

The evaluator is real backend output, not reference mock text. It takes the latest saved script plus the episode outline and returns 3-6 concise, actionable points covering areas such as:

- opening hook;
- character voice consistency;
- pacing and repetition;
- emotional escalation;
- clarity in audio-only form;
- cliffhanger strength.

The panel displays when it was generated and whether it is stale. Users can request a refresh; the result is persisted and survives reloads.

## 7. Persisted folder structure

All generated and edited values continue to live below the series folder:

```text
output/
  <series_id>/
    series.json
    input/
      idea.txt
      source.<ext>                 # only for microphone/audio input
      transcript.txt               # only for microphone/audio input
      clarification.json
      clarification_answers.json
      confirmations.json
      refinements.json
    blueprint/
      plot.json
      swot.json
      genre.json
      theme.json
      characters/
        <character-slug>.json
        narrator.json               # only when used
    episodes/
      ep01/
        outline.json
        script.json
        sound_plan.json
        evaluation.json
        audio.json
        lines/
        final.wav
```

`series.json` remains the lightweight dashboard index. The frontend never reads these paths directly; it uses `/studio` endpoints, which read and atomically update the files.

### 7.1 Confirmation file

`input/confirmations.json` records the user-approved values:

```json
{
  "title": "The Last Signal",
  "genre": "Sci-fi Thriller",
  "setting": "Near-future coastal India",
  "include_narrator": true,
  "episode_count": 8,
  "episode_minutes": 10,
  "genre_tags": ["Survival", "Conspiracy", "Technology", "Isolation"],
  "theme_tags": ["Trust", "Grief", "Identity", "Sacrifice"]
}
```

### 7.2 Plot and SWOT

`blueprint/plot.json`:

```json
{
  "logline": "...",
  "main_storyline": "...",
  "story_world": "...",
  "setting": {
    "time": "...",
    "place": "...",
    "world_rules": ["..."],
    "atmosphere": "..."
  },
  "story_beats": [
    { "label": "Inciting incident", "summary": "..." }
  ],
  "revision": 1
}
```

`blueprint/swot.json`:

```json
{
  "strengths": ["..."],
  "weaknesses": ["..."],
  "opportunities": ["..."],
  "threats": ["..."],
  "source_revision": 1,
  "generated_at": "ISO-8601 timestamp",
  "stale": false
}
```

### 7.3 Genre and theme

`blueprint/genre.json`:

```json
{
  "genre": "Sci-fi Thriller",
  "description": "...",
  "tags": ["Survival", "Conspiracy", "Technology", "Isolation"],
  "distribution": {
    "Action": 10,
    "Drama": 20,
    "Comedy": 0,
    "Sci-fi": 30,
    "Horror": 5,
    "Thriller": 30,
    "Romance": 5
  },
  "source_revision": 1
}
```

`blueprint/theme.json`:

```json
{
  "theme": "Trust under pressure",
  "description": "...",
  "tone": "Tense, intimate, and grounded",
  "tags": [
    { "label": "Trust", "percentage": 35 },
    { "label": "Grief", "percentage": 25 },
    { "label": "Identity", "percentage": 20 },
    { "label": "Sacrifice", "percentage": 20 }
  ],
  "source_revision": 1
}
```

The backend validates exact tag counts and normalizes distributions. The frontend displays the persisted values without changing them.

### 7.4 Character files

Each character JSON is extended without losing current voice fields:

```json
{
  "id": "stable-character-id",
  "name": "Mira Rao",
  "role": "Protagonist",
  "gender": "Woman",
  "personality": "Observant, guarded, stubbornly compassionate",
  "details": "...",
  "physical_persona": "...",
  "backstory": "...",
  "vocal_direction": "Measured pace; warmth emerges under pressure",
  "relationships": ["..."],
  "voice_id": "Kore",
  "is_narrator": false
}
```

During refinement, characters are matched by stable ID first and normalized name second. Existing `voice_id` values are preserved unless the character is removed or the user changes the voice.

### 7.5 Script and audio timing

New scripts store emotion separately:

```json
[
  {
    "id": "line-001",
    "type": "dialogue",
    "speaker": "Mira Rao",
    "text": "The signal is coming from inside the station.",
    "emotion": "suppressed panic",
    "sfx": [],
    "music": null
  },
  {
    "id": "line-002",
    "type": "dialogue",
    "speaker": "Arun",
    "text": "Then we stop listening.",
    "emotion": null,
    "sfx": [],
    "music": null
  }
]
```

`audio.json` contains line mapping:

```json
{
  "final": "absolute-or-server-resolved-path",
  "total_ms": 612430,
  "segments": [
    { "line_id": "line-001", "line_index": 0, "start_ms": 420, "end_ms": 3810 },
    { "line_id": "line-002", "line_index": 1, "start_ms": 4260, "end_ms": 6410 }
  ],
  "stale": false
}
```

Silences, SFX, or music-only spans do not falsely activate a dialogue line. The most recent spoken line may remain dimly completed until the next line starts.

### 7.6 Evaluator result

`episodes/epNN/evaluation.json`:

```json
{
  "points": [
    { "category": "Hook", "assessment": "...", "suggestion": "..." },
    { "category": "Pacing", "assessment": "...", "suggestion": "..." }
  ],
  "script_hash": "sha256-of-current-script",
  "generated_at": "ISO-8601 timestamp",
  "stale": false
}
```

## 8. Backend schema and LangGraph changes

### 8.1 Confirmation schemas

Extend the confirmation model with:

- `genre_tags`: exactly four unique strings;
- `theme_tags`: exactly four unique strings.

The confirmation LLM prompt receives the original idea and all four answers. It must return one recommendation per editable field and tags grounded in the story rather than generic labels.

### 8.2 Character schema

Extend `CharacterProfile` with:

- stable `id`;
- `details`;
- `physical_persona`;
- `backstory`;
- `vocal_direction`.

For migration, existing `description` maps to `details` and `vocal_signature` maps to `vocal_direction`. API responses may temporarily expose aliases so older files still load.

### 8.3 Story analysis schema

Add a single structured `StoryAnalysis` contract containing:

- SWOT quadrants, each 2-4 points;
- genre description;
- the fixed seven-category genre distribution;
- four confirmed genre tags;
- theme description;
- four theme tags with percentages.

One analysis LLM call runs after the general blueprint exists. Combining these related outputs in one validated call keeps them internally consistent and avoids unnecessary repeated context/token use.

Validation rules:

- the genre keys are fixed and cannot be renamed;
- genre values are non-negative integers and normalized to 100;
- theme contains exactly four unique labels;
- theme percentages are non-negative integers and normalized to 100;
- confirmed user tags are preserved unless the refinement prompt explicitly asks to alter them;
- malformed output is retried through the existing structured-output mechanism.

### 8.4 Graph order

The initial creation path becomes:

```text
idea/transcript
  -> extract metadata
  -> generate exactly four questions
  -> collect four answers
  -> generate and confirm title/genre/setting/narrator/episode settings/tags
  -> generate blueprint and characters
  -> generate structured story analysis
  -> generate episode plan
  -> persist all files
  -> Ideaboard
```

The analysis stage runs automatically after blueprint approval. It does not add another mandatory review page; all values remain editable from the Ideaboard.

### 8.5 Emotion prompt rules

Update script prompts and validation:

- `emotion` defaults to `null`;
- only use it for an intentional delivery change from the speaker's established baseline;
- never tag every line in a tense, romantic, sad, or frightening scene;
- avoid adjacent identical emotion tags;
- do not use emotion tags as scene labels;
- keep natural dialogue untagged;
- preserve pauses and silence through timing/sound planning rather than fake emotion tags.

The validator may warn when emotion density is too high. It should not remove a necessary creative direction blindly.

## 9. API contract additions and changes

### 9.1 Existing APIs retained

- `GET /studio/series`
- `GET /studio/series/:id`
- `PATCH /studio/series/:id`
- `GET/PATCH /studio/series/:id/blueprint`
- `GET /studio/series/:id/characters`
- `PATCH /studio/series/:id/characters/:key`
- `GET /studio/series/:id/episodes/:number`
- `PUT /studio/series/:id/episodes/:number/script`
- `POST /studio/series/:id/episodes/:number/generate`
- `GET /studio/jobs/:jobId`

Existing response models are extended rather than replaced so the current frontend can be upgraded incrementally.

### 9.2 Story analysis

```http
POST /studio/series/:id/analysis/regenerate
```

Trigger: explicit user request after manual plot edits, or the automatic initial/refinement pipeline.

Writes:

- `blueprint/swot.json`;
- analysis fields in `blueprint/genre.json`;
- analysis fields in `blueprint/theme.json`.

For an explicit request, return a job ID if the model call may take long enough to require polling.

### 9.3 Story refinement

```http
POST /studio/series/:id/refine
Content-Type: application/json

{ "instruction": "Make the mentor secretly responsible for the first signal." }
```

Returns `202` and a job ID.

The job:

1. appends the request to `input/refinements.json`;
2. hydrates the current story from disk;
3. applies the instruction while preserving accepted canon not contradicted by it;
4. updates plot and character profiles;
5. reruns structured story analysis;
6. replans affected episode outlines;
7. preserves voice assignments for surviving characters;
8. marks affected generated scripts/audio/evaluations stale rather than deleting them;
9. increments the story revision and updates `series.json`.

If a refinement fails, previous accepted files remain intact. Use temporary files and atomic replacement only after validated output is ready.

### 9.4 Episode evaluation

```http
POST /studio/series/:id/episodes/:number/evaluate
```

Input is loaded from the latest persisted outline and script. Output is validated, saved to `evaluation.json`, and returned.

The normal Generate Episode job also runs evaluation automatically, ideally after the script is finalized and in parallel with voice rendering where safe. A manual Refresh Judge action calls the endpoint again.

### 9.5 Episode payload

Extend `GET /studio/series/:id/episodes/:number` to return:

- outline;
- script with stable line IDs and sparse `emotion`;
- sound plan;
- audio manifest/URL and segment timings;
- evaluation and stale state;
- overall episode status.

Do not expose raw filesystem paths to the browser. Return API URLs for playable files and keep disk paths server-side.

## 10. Refinement and invalidation rules

Content dependencies are:

```text
Plot/characters
  -> SWOT + genre/theme analysis
  -> episode outlines
  -> scripts
  -> voice renders + sound plan
  -> final audio
  -> evaluator result
```

Rules:

- changing voice only invalidates that character's rendered lines and final mix;
- changing a script invalidates audio timing, final audio, and evaluation;
- changing an episode outline invalidates that episode's script, audio, and evaluation;
- changing plot/characters directly marks analysis and affected episodes stale;
- a refinement job determines affected episodes, but preserving old files is safer than deleting them;
- stale content is clearly labelled and remains recoverable until regenerated.

Frontend TanStack Query invalidation should be scoped:

- series list after title/progress changes;
- series detail after blueprint, character, refinement, or generation changes;
- episode detail after script, audio, or evaluation changes.

## 11. Frontend component plan

Recommended current-frontend structure:

```text
frontend/src/
  components/
    layout/
      AppHeader.jsx
      PageTransition.jsx
    loaders/
      StoryBuildLoader.jsx
      EpisodeGenerationLoader.jsx
      TypewriterStatus.jsx
    board/
      PlotCard.jsx
      PlotModal.jsx
      GenreCard.jsx
      GenreModal.jsx
      GenreRadarChart.jsx
      ThemeCard.jsx
      ThemeModal.jsx
      ThemeBreakdownChart.jsx
      CharacterGrid.jsx
      CharacterModal.jsx
      EpisodeSidebar.jsx
      RefineBar.jsx
    episode/
      AudioPreview.jsx
      ScriptEditor.jsx
      ScriptLine.jsx
      EpisodeOutline.jsx
      EvaluatorPanel.jsx
    QuestionCard.jsx           # retain current behavior
    ConfirmCard.jsx            # retain current behavior; add tag editors
    VoicePicker.jsx            # retain current design and behavior
  pages/
    Dashboard.jsx
    NewSeries.jsx
    IdeaWizard.jsx
    Building.jsx
    Ideaboard.jsx
    Episode.jsx
  api/
    client.js
    flow.js
    series.js
    studio.js
    analysis.js
    refinement.js
```

Reference files should be adapted into these components instead of copied wholesale. Remove reference mock state, hard-coded stories, simulated loaders, unused image assets, and emotional-curve imports.

## 12. Accessibility and responsiveness

- Every clickable card must also be keyboard accessible.
- All modal dialogs require focus trapping, Escape close, labelled title, and focus restoration.
- Crimson text must not be used on black at tiny sizes where contrast becomes weak; use white text with crimson accents.
- Charts need text summaries or accessible lists of the same percentages.
- Audio controls need clear play/pause labels and keyboard support.
- Active dialogue highlighting cannot rely on color alone; include a small active marker and `aria-current`.
- Textareas and tag editors need visible focus rings.
- Never autoplay generated episode audio.
- Mobile layouts must not let the fixed Refine bar cover the final episode or character card.

## 13. Error and recovery behavior

- API errors appear near the action that failed.
- Loading pages include Retry only after the backend job reports failure or becomes unreachable.
- Retrying with an existing job ID re-polls/rejoins when possible; it does not blindly create duplicate jobs.
- Invalid LLM analysis never overwrites the last valid JSON.
- Audio generation errors identify failed lines and allow regeneration.
- Missing audio timing falls back to waveform-only progress and disables line-sync with a small explanation; it does not fake synchronization.
- Existing older series files are migrated/defaulted on read so the redesign does not make them inaccessible.

## 14. Implementation sequence

### Phase 1: data contracts and migration

1. Extend Pydantic models for confirmation tags, expanded characters, structured analysis, sparse emotion, and evaluator output.
2. Add backward-compatible store readers and atomic writers for the new files.
3. Add stable character and script-line IDs.
4. Add tests for seven-category and four-theme percentage normalization.

### Phase 2: backend generation

1. Update confirmation generation to return four genre tags and four theme tags.
2. Add the structured analysis LLM node/service.
3. Persist SWOT, genre distribution, and theme distribution.
4. Add the refinement job and stale-content rules.
5. Add the episode evaluator call and persistence.
6. Add segment timing/line mapping to `audio.json`.
7. Tighten sparse-emotion prompts and validation.

### Phase 3: shared visual foundation

1. Port reference color tokens, type, card surfaces, and motion defaults into current global styles.
2. Add Lucide and Recharts.
3. Create shared modal, transition, and reduced-motion behavior.
4. Verify current Voice page and VoicePicker are not visually or functionally broken.

### Phase 4: creation flow

1. Rebuild Dashboard from the reference without images.
2. Make New Series a Dashboard grid card.
3. Combine the New Series choice screens.
4. Rebuild Write shell and reference modal shell.
5. Preserve/recolor current QuestionCard and ConfirmCard, adding exact-four tag editors.
6. Combine the initial loaders and connect them to real work.

### Phase 5: Ideaboard

1. Port reference board layout and episode sidebar.
2. Add plot/setting/SWOT modal.
3. Add fixed seven-axis genre radar.
4. Add read-only four-theme chart.
5. Add expanded character popup with existing VoicePicker.
6. Add real refinement bar and route.
7. Add real episode generation loader.

### Phase 6: Episode page

1. Port the reference Episode page composition.
2. Remove Emotional Curve and all related imports.
3. Connect real audio and waveform progress.
4. Add segment-based dialogue highlighting.
5. Preserve script editing and stale-audio behavior.
6. Add real AI Evaluator Judge points.

### Phase 7: verification and polish

1. Run backend unit/API tests and frontend production build.
2. Test old and newly generated series.
3. Test Write and Mic flows end-to-end.
4. Test refinement success, failure, reload, and stale markers.
5. Test episode generation with multiple voices and parallel TTS.
6. Test playback seeking and exact active-line changes.
7. Test desktop, tablet, and mobile layouts.
8. Test keyboard, screen-reader labels, reduced motion, and color contrast.

## 15. Acceptance checklist

### Dashboard and creation

- [ ] Dashboard visually follows the reference.
- [ ] Dashboard contains no images.
- [ ] New Series is a dashed series card, not a separate button.
- [ ] New Series page combines reference composition with current clarity.
- [ ] Write page follows the reference editor design.
- [ ] Exactly four story-specific questions are always shown.
- [ ] Every question has options, exactly one recommendation, and free text.
- [ ] Current QuestionCard and ConfirmCard behavior is preserved with reference colors.
- [ ] Four genre tags and four theme tags are confirmed before build.
- [ ] Voice input page remains functionally unchanged.

### Ideaboard

- [ ] Plot modal includes Story Line, Setting, and persisted SWOT.
- [ ] Genre radar always has the exact seven required categories.
- [ ] Genre values and theme values are generated by the backend and saved in JSON.
- [ ] Genre shows exactly four tags.
- [ ] Theme shows exactly four weighted tags.
- [ ] Theme has no Make Changes button and no emotional curve.
- [ ] Character popup has all six required information sections.
- [ ] Existing VoicePicker works inside the character popup.
- [ ] Episodes appear on the right and Episode 1 starts open.
- [ ] Refinement reruns the real pipeline and opens a real loading page.
- [ ] Episode generation opens the reference-style generation loader.

### Episode page

- [ ] Page follows the reference layout.
- [ ] Audio waveform and script lines track actual playback.
- [ ] Active/played dialogue turns crimson with a non-color active marker.
- [ ] Emotional Curve is absent.
- [ ] AI Evaluator Judge is generated by the backend and persisted.
- [ ] Emotion tags appear only for meaningful non-natural delivery.
- [ ] Script edits correctly mark audio and evaluation stale.

### Reliability

- [ ] No reference mock data or fake generation timer remains in production paths.
- [ ] All frontend edits persist to the correct series folder through the backend.
- [ ] Refinement preserves character voices where characters survive.
- [ ] Invalid LLM output cannot overwrite valid saved files.
- [ ] Loading jobs can recover after a browser refresh.
- [ ] UI is clean, responsive, fast, and honors reduced motion.
