"""End-to-end test of the per-episode generation job.

Seeds a tiny 3-line episode so the TTS cost is bounded (free tier is ~3 req/min,
so this takes roughly a minute), then runs the real job and reports progress.

Run:  python -m tools.test_episode_job
"""
from __future__ import annotations

import time

from fastapi.testclient import TestClient

from app import store
from app.main import app

SID = "_jobtest"


def seed() -> None:
    store.delete_series(SID)
    store.save_idea(SID, "A lighthouse keeper receives letters from the future.")
    store.save_blueprint(SID, {
        "logline": "A keeper reads tomorrow's mail.",
        "story_world": "A storm-battered island lighthouse, 1953.",
        "main_storyline": "Each letter predicts a death he might prevent.",
        "tone": "Haunting", "theme": "Fate versus choice",
        "characters": [
            {"name": "Thomas", "role": "protagonist", "gender": "male",
             "description": "The keeper.", "personality": "Stoic",
             "relationships": [], "vocal_signature": "Low, weathered",
             "is_narrator": False, "voice_id": "Algenib"},
            {"name": "Narrator", "role": "narrator", "gender": "neutral",
             "description": "Narrates.", "personality": "Patient",
             "relationships": [], "vocal_signature": "Slow, resonant",
             "is_narrator": True, "voice_id": "Charon"},
        ],
    }, meta={"genre": "Supernatural Mystery", "setting": "Island, 1953",
             "language": "English", "theme": "Fate versus choice"})
    store.save_episode_outline(SID, {
        "number": 1, "title": "The First Letter", "summary": "A letter arrives.",
        "main_events": ["The letter arrives"], "emotional_focus": "Dread",
        "cliffhanger": "The next envelope bears his own name.",
    })
    # Pre-seed the script so the job skips the LLM pass and we only pay for TTS.
    store.save_episode_script(SID, 1, [
        {"type": "narration", "speaker": "Narrator",
         "text": "The lamp turned through the fog.", "sfx": [], "music": None},
        {"type": "dialogue", "speaker": "Thomas",
         "text": "[Fear] This is my own handwriting.", "sfx": [], "music": None},
        {"type": "narration", "speaker": "Narrator",
         "text": "Outside, the sea kept its counsel.", "sfx": [], "music": None},
    ])
    store.save_index(SID, title="The Keeper's Correspondence",
                     genre="Supernatural Mystery", stage="script")


def main() -> None:
    seed()
    c = TestClient(app)

    print(f"status before : {store.episode_status(SID, 1)}")
    r = c.post(f"/studio/series/{SID}/episodes/1/generate")
    print(f"POST generate : {r.status_code}")
    job = r.json()
    job_id = job["id"]
    print(f"job           : {job_id} state={job['state']} steps={job.get('steps')}")

    # A second click must rejoin, not duplicate.
    again = c.post(f"/studio/series/{SID}/episodes/1/generate").json()
    print(f"re-click      : same job? {again['id'] == job_id}")

    seen = []
    t0 = time.time()
    while True:
        job = c.get(f"/studio/jobs/{job_id}").json()
        line = f"{job['step']:<7} {job['done']}/{job['total']} {job['message']}"
        if line not in seen:
            seen.append(line)
            print(f"  [{time.time()-t0:5.1f}s] {line}")
        if job["state"] in ("done", "error"):
            break
        time.sleep(2)

    print(f"\nfinal state   : {job['state']}")
    if job["state"] == "error":
        print(f"error         : {job['error']}")
    else:
        print(f"result        : {job['result']}")

    print(f"status after  : {store.episode_status(SID, 1)}")
    ep = c.get(f"/studio/series/{SID}/episodes/1").json()
    print(f"sound_plan    : music={len(ep['sound_plan'].get('music', []))} "
          f"sfx={len(ep['sound_plan'].get('sfx', []))}")
    a = c.get(f"/studio/series/{SID}/episodes/1/audio")
    print(f"audio GET     : {a.status_code} {len(a.content)} bytes")

    print("\nfiles on disk:")
    root = store.series_dir(SID)
    for p in sorted(store.episode_dir(SID, 1).rglob("*")):
        if p.is_file():
            print(f"  {p.relative_to(root)}  ({p.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
