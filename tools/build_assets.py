"""Generate a starter music + SFX library and its manifest.

These are lightweight SYNTHESISED placeholders (pure stdlib) so the whole audio
pipeline runs offline out of the box. Replace any file under assets/music or
assets/sfx with a real CC0 clip of the same name and the manifest still applies.

Run:  python -m tools.build_assets
"""
from __future__ import annotations

import json
import math
import random
import struct
import wave
from pathlib import Path

SR = 24_000  # match Gemini TTS output so pydub mixes without resampling
ROOT = Path(__file__).resolve().parent.parent
MUSIC = ROOT / "assets" / "music"
SFX = ROOT / "assets" / "sfx"
MANIFEST = ROOT / "assets" / "sound_manifest.json"


def _write(path: Path, samples: list[float]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    peak = max((abs(s) for s in samples), default=1.0) or 1.0
    norm = 0.9 / peak
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SR)
        wf.writeframes(b"".join(
            struct.pack("<h", int(max(-1.0, min(1.0, s * norm)) * 32767)) for s in samples
        ))


def _chord(freqs: list[float], seconds: float, tremolo: float = 0.0) -> list[float]:
    n = int(SR * seconds)
    out = []
    for i in range(n):
        t = i / SR
        v = sum(math.sin(2 * math.pi * f * t) for f in freqs) / len(freqs)
        if tremolo:
            v *= 1.0 + tremolo * math.sin(2 * math.pi * 4.0 * t)
        # gentle loop-friendly envelope (fade edges)
        env = min(1.0, t / 0.4, (seconds - t) / 0.4)
        out.append(v * 0.5 * env)
    return out


def _noise(seconds: float, lp: float = 1.0, decay: bool = False) -> list[float]:
    n = int(SR * seconds)
    rnd = random.Random(1234)
    out, prev = [], 0.0
    for i in range(n):
        white = rnd.uniform(-1, 1)
        prev = prev + lp * (white - prev)   # simple one-pole low-pass
        v = prev
        if decay:
            v *= math.exp(-3.0 * (i / n))
        out.append(v)
    return out


# --- music beds (loopable ~8s) ------------------------------------------------
MUSIC_DEFS = {
    "romantic":  (lambda: _chord([261.63, 329.63, 392.00], 8, 0.05), ["love", "tender", "warm"]),
    "emotional": (lambda: _chord([220.00, 261.63, 329.63], 8, 0.03), ["sad", "reflective", "soft"]),
    "hopeful":   (lambda: _chord([293.66, 369.99, 440.00], 8, 0.04), ["uplifting", "bright"]),
    "tense":     (lambda: _chord([146.83, 155.56, 220.00], 8, 0.12), ["suspense", "anxious"]),
    "horror":    (lambda: _chord([110.00, 116.54, 164.81], 8, 0.18), ["scary", "dread", "creepy"]),
    "mystery":   (lambda: _chord([196.00, 233.08, 293.66], 8, 0.08), ["intrigue", "noir"]),
    "action":    (lambda: _chord([130.81, 196.00, 261.63], 8, 0.15), ["battle", "chase", "fight"]),
    "ambient":   (lambda: _chord([174.61, 261.63, 349.23], 8, 0.02), ["calm", "neutral", "background"]),
}

# --- one-shot SFX -------------------------------------------------------------
SFX_DEFS = {
    "thunder":    (lambda: _noise(3.0, lp=0.02, decay=True), ["lightning", "storm"]),
    "rain":       (lambda: _noise(6.0, lp=0.30), ["rainfall", "drizzle"]),
    "wind":       (lambda: _noise(6.0, lp=0.05), ["breeze", "gale"]),
    "footsteps":  (lambda: _noise(2.0, lp=0.08, decay=False), ["walking", "steps"]),
    "door_creak": (lambda: _chord([180, 190], 1.5, 0.4), ["door", "hinge", "open"]),
    "birds":      (lambda: _chord([2200, 2600, 3000], 5, 0.5), ["forest", "nature", "morning"]),
    "heartbeat":  (lambda: _noise(3.0, lp=0.01, decay=False), ["pulse", "fear", "tension"]),
    "clock_tick": (lambda: _noise(4.0, lp=0.5), ["deadline", "time"]),
    "sword_clash":(lambda: _noise(1.0, lp=0.4, decay=True), ["battle", "fight", "metal"]),
    "glass_break":(lambda: _noise(1.2, lp=0.6, decay=True), ["shatter", "crash"]),
    "crowd":      (lambda: _noise(5.0, lp=0.06), ["market", "people", "festival"]),
    "phone_ring": (lambda: _chord([440, 480], 2.0, 0.9), ["call", "ringtone"]),
}


def main() -> None:
    manifest: dict[str, dict] = {"music": {}, "sfx": {}}

    for name, (gen, keywords) in MUSIC_DEFS.items():
        rel = f"music/{name}.wav"
        _write(MUSIC / f"{name}.wav", gen())
        manifest["music"][name] = {
            "file": rel, "loopable": True, "keywords": keywords,
            "license": "PLACEHOLDER-synth (replace with CC0)",
        }

    for name, (gen, keywords) in SFX_DEFS.items():
        rel = f"sfx/{name}.wav"
        _write(SFX / f"{name}.wav", gen())
        manifest["sfx"][name] = {
            "file": rel, "keywords": keywords,
            "license": "PLACEHOLDER-synth (replace with CC0)",
        }

    MANIFEST.write_text(json.dumps(manifest, indent=2))
    print(f"Wrote {len(manifest['music'])} music beds, {len(manifest['sfx'])} sfx")
    print(f"Manifest: {MANIFEST}")


if __name__ == "__main__":
    main()
