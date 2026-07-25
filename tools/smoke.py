"""Drive the graph through its interrupts locally (no HTTP). For manual testing.

Usage:
  python -m tools.smoke text     # run text stages, stop at voice_cast review
  python -m tools.smoke full     # full pipeline incl. TTS + mix (uses API + time)
"""
from __future__ import annotations

import sys

from langgraph.types import Command

from app.graph import GRAPH
from app.state import new_state

IDEA = (
    "A night-shift nurse in a small hospital realises that a patient who flatlined "
    "keeps reappearing in the security footage, always pointing at room 4B. She has "
    "three nights before the room is demolished."
)


def _command(stage: str) -> dict:
    if stage == "clarify":
        return {"action": "submit", "data": {"clarification_answers": []}}
    if stage == "ep_config":
        return {"action": "submit", "data": {"ep_count": 1, "ep_minutes": 5}}
    return {"action": "approve"}


def drive(stop_at: str | None) -> None:
    sid = "smoke"
    cfg = {"configurable": {"thread_id": sid}}
    res = GRAPH.invoke(new_state(sid, IDEA), cfg)
    while "__interrupt__" in res:
        stage = res["__interrupt__"][0].value["stage"]
        payload = res["__interrupt__"][0].value["payload"]
        keys = list(payload.keys())
        print(f"[REVIEW] stage={stage} payload_keys={keys}")
        if stop_at and stage == stop_at:
            print(f"== stopping at {stage} (not approving) ==")
            return
        res = GRAPH.invoke(Command(resume=_command(stage)), cfg)
    print(f"[DONE] final stage={res.get('stage')}")
    for num, info in res.get("audio_manifest", {}).items():
        print(f"  ep{num}: final={info.get('final')}")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "text"
    drive(stop_at="voice_cast" if mode == "text" else None)
