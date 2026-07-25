# Storywave Studio — Start Guide

This project has two local services:

- FastAPI backend: `http://localhost:8000`
- React frontend: `http://localhost:5173`

Run both services from the project root:

```powershell
cd "C:\Users\happy\Desktop\college\hackathons\POCKET_FM"
```

## 1. Configure Gemini

Make sure the root `.env` file contains:

```env
GEMINI_API_KEY=your_gemini_api_key
```

For faster TTS, provide multiple comma-separated keys. Each key receives its own
rate-limit lane and one line can be rendered per key in parallel:

```env
GEMINI_API_KEY=your_primary_key
GEMINI_API_KEYS=key_1,key_2,key_3
TTS_PARALLEL_WORKERS=3
```

`TTS_PARALLEL_WORKERS` should normally be no greater than the total number of unique
keys. The application automatically removes duplicate keys.

The project uses:

- `gemini-3.1-flash-lite` for story generation and transcription
- `gemini-3.1-flash-tts-preview` for voices

## 2. Start the backend

Use the existing virtual environment:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

Verify it is running:

- Health check: [http://localhost:8000/health](http://localhost:8000/health)
- API documentation: [http://localhost:8000/docs](http://localhost:8000/docs)

## 3. Start the frontend

Open a second PowerShell window:

```powershell
cd "C:\Users\happy\Desktop\college\hackathons\POCKET_FM\frontend"
npm install
npm run dev
```

Open the application at [http://localhost:5173](http://localhost:5173).

The frontend automatically connects to `http://localhost:8000`. To use another backend
URL, create `frontend/.env`:

```env
VITE_API_BASE=http://localhost:8000
```

## 4. Use the application

1. Select **New series**.
2. Choose **Write** or **Speak**.
3. Submit the story idea.
4. Answer the four generated questions. Each question includes a recommended option.
5. Review the generated title, genre, setting, narrator choice, episode count, and length.
6. Wait for the idea board to load.
7. Expand an episode and select **Generate episode**.
8. Open the generated episode to preview or download the audio.

All series data is saved under:

```text
output/<series_id>/
```

The folder contains the original input, clarification answers, blueprint, characters,
episode outlines, scripts, sound plans, voice clips, and final audio.

## 5. Audio-generation notes

Episode generation runs in the background. The frontend polls the job and displays its
current step:

```text
script → voices → sound → mix
```

Gemini’s free-tier TTS quota is rate-limited per key or project. With multiple independent
keys, episode lines are distributed across the key pool and rendered concurrently. A
single key is still throttled safely, and retryable quota errors rotate to another key.
Avoid repeatedly clicking Generate while a job is already running.

## 6. Production build check

To build the frontend without starting the dev server:

```powershell
cd frontend
npm run build
```

The compiled files are written to `frontend/dist/`.

## 7. Run backend tests

From the project root:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```
