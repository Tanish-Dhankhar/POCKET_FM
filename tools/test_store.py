"""Verify the on-disk series layout and the store-backed API round-trip.

Uses fabricated data (no LLM calls) so it's fast and free — the point is to prove
the folder structure, reads, and writes, not the generation quality.

Run:  python -m tools.test_store
"""
from __future__ import annotations

import shutil

from fastapi.testclient import TestClient

from app import config, store
from app.main import app

SID = "_layouttest"


def seed() -> None:
    store.delete_series(SID)
    store.save_idea(SID, "A lighthouse keeper receives letters from the future.",
                    transcript="spoken version of the idea")
    store.save_clarification(SID, {"questions": [
        {"question": "How does he learn the truth?",
         "options": [{"label": "A. Slowly", "detail": "Dawning dread."}],
         "allow_free_text": True}]})
    store.save_clarification_answers(SID, [{"question": "How does he learn the truth?",
                                            "answer": "A. Slowly"}])
    store.save_blueprint(SID, {
        "logline": "A keeper reads tomorrow's mail.",
        "story_world": "A storm-battered island lighthouse, 1953.",
        "main_storyline": "Each letter predicts a death he might prevent.",
        "tone": "Haunting", "theme": "Fate versus choice",
        "characters": [
            {"name": "Thomas Vane", "role": "protagonist", "gender": "male",
             "description": "The keeper.", "personality": "Stoic, guilt-ridden",
             "relationships": ["Estranged from his brother"],
             "vocal_signature": "Low, unhurried, weathered", "is_narrator": False},
            {"name": "The Sea", "role": "narrator", "gender": "neutral",
             "description": "Narrates.", "personality": "Patient, vast",
             "relationships": [], "vocal_signature": "Slow, resonant",
             "is_narrator": True},
        ],
    }, meta={"genre": "Supernatural Mystery", "setting": "Island, 1953",
             "language": "English", "theme": "Fate versus choice"})
    for n, title in ((1, "The First Letter"), (2, "Tomorrow's Name")):
        store.save_episode_outline(SID, {
            "number": n, "title": title, "summary": f"Summary {n}.",
            "main_events": ["An event"], "emotional_focus": "Dread",
            "cliffhanger": "The next envelope bears his own name.",
        })
    store.save_episode_script(SID, 1, [
        {"type": "narration", "speaker": "The Sea", "text": "The lamp turned.",
         "sfx": [], "music": None},
        {"type": "dialogue", "speaker": "Thomas Vane",
         "text": "[Fear] This is my handwriting.", "sfx": [], "music": None},
    ])
    store.save_index(SID, title="The Keeper's Correspondence",
                     genre="Supernatural Mystery", stage="script")


def main() -> None:
    seed()
    c = TestClient(app)

    print("=== FOLDER LAYOUT ===")
    root = store.series_dir(SID)
    for p in sorted(root.rglob("*")):
        rel = p.relative_to(root.parent)
        print(("  " if p.is_file() else "  ") + str(rel) + ("" if p.is_file() else "/"))

    print("\n=== API READS ===")
    lst = c.get("/studio/series").json()["series"]
    card = next(s for s in lst if s["series_id"] == SID)
    print(f"list      : title={card['title']!r} episodes={card['episode_count']} "
          f"ready={card['generated_count']}")

    full = c.get(f"/studio/series/{SID}").json()
    print(f"series    : chars={[ch['name'] for ch in full['characters']]}")
    print(f"            episodes={[(e['number'], e['status']) for e in full['episodes']]}")
    print(f"input     : idea={full['input']['idea'][:32]!r}... "
          f"answers={len(full['input']['clarification_answers'])}")
    print(f"blueprint : genre={full['blueprint']['genre']!r} "
          f"theme={full['blueprint']['theme']!r}")

    ep = c.get(f"/studio/series/{SID}/episodes/1").json()
    print(f"episode 1 : status={ep['status']} script_lines={len(ep['script'])}")

    print("\n=== API WRITES (frontend edits) ===")
    r = c.patch(f"/studio/series/{SID}/characters/thomas-vane",
                json={"voice_id": "Algenib", "personality": "Stoic, haunted"})
    print(f"character : voice_id={r.json()['voice_id']} -> "
          f"persisted={store.load_voice_cast(SID)}")

    r = c.patch(f"/studio/series/{SID}/blueprint",
                json={"plot": {"main_storyline": "EDITED storyline."}})
    print(f"blueprint : main_storyline={r.json()['main_storyline']!r}")

    r = c.put(f"/studio/series/{SID}/episodes/1/script", json={"lines": [
        {"type": "dialogue", "speaker": "Thomas Vane",
         "text": "[Whisper] Edited by the creator.", "sfx": [], "music": None}]})
    print(f"script    : {r.json()}")
    print(f"            on disk={store.load_episode(SID, 1)['script'][0]['text']!r}")

    r = c.patch(f"/studio/series/{SID}", json={"title": "Renamed Series"})
    print(f"index     : title={r.json()['title']!r}")

    print("\n=== HYDRATE (disk -> pipeline state) ===")
    h = store.hydrate(SID)
    print(f"idea      : {h['idea'][:40]!r}...")
    print(f"characters: {[c_['name'] for c_ in h['characters']]}")
    print(f"voice_cast: {h['voice_cast']}")
    print(f"episodes  : {[e['number'] for e in h['episodes']]}")
    print(f"scripts   : keys={list(h['scripts'])}")
    print(f"blueprint : {h['blueprint']['main_storyline']!r}")

    store.delete_series(SID)
    print(f"\ncleanup   : removed={not store.series_dir(SID).exists()}")


if __name__ == "__main__":
    main()
