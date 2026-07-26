"""Drive the full pipeline against the real OpenAI and Gemini APIs.

This is the end-to-end acceptance run: real text generation, real TTS, real mix.
It approves each review stage automatically and then asserts that everything the
backend promised actually exists on disk and is internally consistent.

Run:
  python -m tools.live_run                 # 1 episode, ~5 min of story
  python -m tools.live_run --episodes 2
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import wave
from pathlib import Path

from langgraph.types import Command

from app import assets, config
from app.graph import GRAPH
from app.state import new_state

IDEA = (
    "A night-shift nurse in a small county hospital realises that a patient who "
    "flatlined last winter keeps reappearing in the security footage, always "
    "pointing at room 4B. She has three nights before the room is demolished."
)


# --------------------------------------------------------------------------- #
# driving
# --------------------------------------------------------------------------- #
def _command(stage: str, ep_count: int, ep_minutes: int) -> dict:
    """Auto-answer each review gate the way a creator would."""
    if stage == "clarify":
        # Take the first offered option for every question, as a creator might.
        return {"action": "submit", "data": {"clarification_answers": []}}
    if stage == "ep_config":
        return {"action": "submit",
                "data": {"ep_count": ep_count, "ep_minutes": ep_minutes}}
    return {"action": "approve"}


def _answer_clarify(state: dict) -> dict:
    """Answer the clarification questions by picking the first option each time."""
    answers = []
    for q in state.get("clarification", {}).get("questions", []):
        opts = q.get("options") or []
        answers.append({
            "question": q.get("question"),
            "answer": opts[0]["label"] if opts else "Surprise me.",
        })
    return {"action": "submit", "data": {"clarification_answers": answers}}


def run(series_id: str, ep_count: int, ep_minutes: int) -> dict:
    cfg = {"configurable": {"thread_id": series_id}}
    started = time.time()

    print(f"\n{'='*72}\nLIVE RUN  series_id={series_id}  "
          f"episodes={ep_count} x {ep_minutes}min")
    print(f"text_hard={config.TEXT_MODEL_HARD}  text_easy={config.TEXT_MODEL_EASY}  "
          f"tts={config.TTS_MODEL}\n{'='*72}\n")

    t0 = time.time()
    res = GRAPH.invoke(new_state(series_id, IDEA), cfg)

    while "__interrupt__" in res:
        stage = res["__interrupt__"][0].value["stage"]
        print(f"  [{time.time()-started:6.1f}s] review: {stage:<14} "
              f"(+{time.time()-t0:5.1f}s)")
        t0 = time.time()

        values = GRAPH.get_state(cfg).values
        if stage == "clarify":
            cmd = _answer_clarify(values)
            n = len(cmd["data"]["clarification_answers"])
            print(f"           -> answered {n} clarification question(s)")
        else:
            cmd = _command(stage, ep_count, ep_minutes)

        if stage == "script":
            total = sum(len(v) for v in values.get("scripts", {}).values())
            print(f"           -> {total} script lines; voicing starts next "
                  f"(~18s/line)")

        res = GRAPH.invoke(Command(resume=cmd), cfg)

    print(f"\n  [{time.time()-started:6.1f}s] final stage: {res.get('stage')}\n")
    return GRAPH.get_state(cfg).values


# --------------------------------------------------------------------------- #
# verification
# --------------------------------------------------------------------------- #
class Checker:
    def __init__(self) -> None:
        self.failures: list[str] = []

    def check(self, label: str, ok: bool, detail: str = "") -> bool:
        mark = "PASS" if ok else "FAIL"
        print(f"  [{mark}] {label}" + (f" — {detail}" if detail else ""))
        if not ok:
            self.failures.append(label)
        return ok


def _wav_seconds(path: Path) -> float:
    with wave.open(str(path), "rb") as wf:
        return wf.getnframes() / wf.getframerate()


def verify(state: dict) -> int:
    c = Checker()
    sid = state["series_id"]
    out = config.OUTPUT_DIR / sid

    print("-" * 72)
    print("VERIFYING TEXT ARTIFACTS")
    print("-" * 72)
    c.check("genre/theme/tone extracted",
            all(state.get(k) for k in ("genre", "theme", "tone")),
            f"{state.get('genre')} / {state.get('tone')}")
    c.check("logline present", bool(state.get("logline")))

    bp = state.get("blueprint") or {}
    c.check("blueprint has world + storyline",
            bool(bp.get("story_world") and bp.get("main_storyline")))
    chars = state.get("characters", [])
    c.check("characters have vocal signatures",
            bool(chars) and all(ch.get("vocal_signature") for ch in chars),
            f"{len(chars)} characters")

    eps = state.get("episodes", [])
    c.check("episode plan matches requested count",
            len(eps) == state.get("ep_count"),
            f"{len(eps)} episodes")
    c.check("every episode has a cliffhanger",
            bool(eps) and all(e.get("cliffhanger") for e in eps))
    c.check("episode numbers are sequential",
            [e["number"] for e in eps] == list(range(1, len(eps) + 1)))

    scripts = state.get("scripts", {})
    c.check("a script exists for every episode",
            set(scripts) == {str(e["number"]) for e in eps},
            f"{sum(len(v) for v in scripts.values())} total lines")

    # Emotion tags should be present but sparse (the craft rule in prompts.py).
    all_lines = [ln for v in scripts.values() for ln in v]
    tagged = [ln for ln in all_lines if "[" in (ln.get("text") or "")]
    ratio = len(tagged) / max(1, len(all_lines))
    c.check("emotion tags used sparingly", ratio <= 0.6,
            f"{len(tagged)}/{len(all_lines)} lines tagged ({ratio:.0%})")

    speakers = {ln["speaker"] for ln in all_lines}
    cast = state.get("voice_cast", {})
    c.check("voice cast is non-empty", bool(cast), f"{len(cast)} roles cast")
    c.check("all cast voices are real Gemini voices",
            set(cast.values()) <= set(config.VOICE_NAMES),
            ", ".join(f"{k}={v}" for k, v in list(cast.items())[:4]))
    c.check("cast voices are distinct",
            len(set(cast.values())) == len(cast))
    c.check("every speaking role is cast",
            speakers <= set(cast),
            f"uncast: {speakers - set(cast) or 'none'}")

    print()
    print("-" * 72)
    print("VERIFYING AUDIO ARTIFACTS")
    print("-" * 72)
    manifest = state.get("audio_manifest", {})
    c.check("audio manifest covers every episode", set(manifest) == set(scripts))

    for num in sorted(manifest, key=int):
        info = manifest[num]
        print(f"\n  episode {num}:")
        lines = info.get("line_files", [])
        c.check(f"ep{num}: one WAV per script line",
                len(lines) == len(scripts[num]),
                f"{len(lines)} line files")
        c.check(f"ep{num}: all line WAVs exist and are non-empty",
                all(Path(p).exists() and Path(p).stat().st_size > 1000 for p in lines))

        voices = Path(info["voices"])
        c.check(f"ep{num}: stitched voice track exists", voices.exists(),
                f"{_wav_seconds(voices):.1f}s" if voices.exists() else "missing")

        final = Path(info.get("final", ""))
        ok_final = final.exists()
        c.check(f"ep{num}: final mix exists", ok_final,
                f"{_wav_seconds(final):.1f}s, "
                f"{final.stat().st_size/1_000_000:.1f} MB" if ok_final else "missing")

        if ok_final:
            v_len, f_len = _wav_seconds(voices), _wav_seconds(final)
            c.check(f"ep{num}: mix preserves the voice timeline",
                    abs(v_len - f_len) < 0.5, f"{v_len:.1f}s vs {f_len:.1f}s")
            c.check(f"ep{num}: episode has real duration", f_len > 30,
                    f"{f_len/60:.1f} min")

        offsets = info.get("offsets", [])
        c.check(f"ep{num}: line offsets are monotonic",
                offsets == sorted(offsets) and offsets[0] == 0)

        plan = state.get("sound_plans", {}).get(num, {})
        music, sfx = plan.get("music", []), plan.get("sfx", [])
        c.check(f"ep{num}: music moods are all real assets",
                all(m["mood"] in assets.music_moods() for m in music),
                f"{len(music)} beds")
        c.check(f"ep{num}: sfx keys are all real assets",
                all(s["name"] in assets.sfx_keys() for s in sfx),
                f"{len(sfx)} cues")

        total_ms = info.get("total_ms", 1)
        covered = sum(m["end_ms"] - m["start_ms"] for m in music)
        c.check(f"ep{num}: music coverage within the restraint cap",
                covered <= config.MAX_MUSIC_COVERAGE * total_ms + 1,
                f"{covered/max(1,total_ms):.0%} of episode "
                f"(cap {config.MAX_MUSIC_COVERAGE:.0%})")

        times = [s["at_ms"] for s in sfx]
        spaced = all((b - a) / 1000 >= config.MIN_SECONDS_BETWEEN_SFX
                     for a, b in zip(times, times[1:]))
        c.check(f"ep{num}: sfx are spaced out", spaced)

    print()
    print("-" * 72)
    print("VERIFYING SAVED STATE")
    print("-" * 72)
    snapshot = out / "series.json"
    c.check("series.json written", snapshot.exists())
    if snapshot.exists():
        data = json.loads(snapshot.read_text(encoding="utf-8"))
        c.check("series.json is complete",
                all(data.get(k) for k in
                    ("blueprint", "episodes", "scripts", "voice_cast", "audio_manifest")),
                f"{snapshot.stat().st_size/1000:.0f} KB")
        c.check("series.json round-trips the cast", data.get("voice_cast") == cast)

    cache = out / "tts_cache"
    c.check("tts cache populated for reuse", cache.exists() and any(cache.iterdir()),
            f"{len(list(cache.glob('*.wav')))} cached clips" if cache.exists() else "")

    print()
    print("=" * 72)
    if c.failures:
        print(f"RESULT: {len(c.failures)} CHECK(S) FAILED")
        for f in c.failures:
            print(f"  - {f}")
    else:
        print("RESULT: ALL CHECKS PASSED")
    print("=" * 72)
    return 1 if c.failures else 0


# --------------------------------------------------------------------------- #
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--episodes", type=int, default=1)
    ap.add_argument("--minutes", type=int, default=5)
    ap.add_argument("--series-id", default="live")
    args = ap.parse_args()

    state = run(args.series_id, args.episodes, args.minutes)
    code = verify(state)

    manifest = state.get("audio_manifest", {})
    if manifest:
        print("\nListen to:")
        for num in sorted(manifest, key=int):
            print(f"  {manifest[num].get('final')}")
    return code


if __name__ == "__main__":
    sys.exit(main())
