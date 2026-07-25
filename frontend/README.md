# Storywave frontend

## Run locally

Open two terminals from the repository root.

Backend:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

Frontend:

```powershell
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`.

The frontend defaults to `http://localhost:8000`. To use another API host, copy
`.env.example` to `.env` and change `VITE_API_BASE`.

## Audio generation

Open a series, expand an episode, then select **Generate episode**. The backend runs
script generation, per-line TTS, sparse sound design, and mixing in a background job.
The Gemini free tier limits TTS throughput, so a full episode can take several minutes.
Progress remains visible on the episode row.
