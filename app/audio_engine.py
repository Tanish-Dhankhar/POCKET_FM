"""pydub audio assembly: concatenate voice lines, duck music, place SFX, export.

Kept deliberately small and declarative — the *decisions* (which cue, where) are
made upstream in sound_design; this module just realises them as audio.
"""
from __future__ import annotations

from pathlib import Path

from pydub import AudioSegment

from . import config


def load(path: str | Path) -> AudioSegment:
    return AudioSegment.from_file(str(path))


def concat_lines(line_paths: list[str | Path],
                 pause_ms: int = config.PAUSE_BETWEEN_LINES_MS
                 ) -> tuple[AudioSegment, list[int]]:
    """Concatenate per-line WAVs with a natural pause between them.

    Returns the stitched track and the start offset (ms) of each line, so the
    mixer can place music/SFX against the same timeline.
    """
    track = AudioSegment.silent(duration=0)
    offsets: list[int] = []
    pause = AudioSegment.silent(duration=pause_ms)
    for i, p in enumerate(line_paths):
        offsets.append(len(track))
        track += load(p)
        if i != len(line_paths) - 1:
            track += pause
    return track, offsets


def _loop_to(seg: AudioSegment, length_ms: int) -> AudioSegment:
    if len(seg) == 0:
        return AudioSegment.silent(duration=length_ms)
    reps = (length_ms // len(seg)) + 1
    return (seg * reps)[:length_ms]


def place_music(base: AudioSegment, bed_path: str | Path,
                start_ms: int, end_ms: int,
                duck_db: int = config.MUSIC_DUCK_DB,
                fade_ms: int = config.MUSIC_FADE_MS) -> AudioSegment:
    """Loop a music bed under [start_ms, end_ms), ducked below the voice."""
    span = max(0, end_ms - start_ms)
    if span <= 0:
        return base
    bed = _loop_to(load(bed_path), span) + duck_db          # attenuate (dB)
    bed = bed.fade_in(min(fade_ms, span)).fade_out(min(fade_ms, span))
    return base.overlay(bed, position=start_ms)


def place_sfx(base: AudioSegment, sfx_path: str | Path,
              at_ms: int, gain_db: int = config.SFX_GAIN_DB) -> AudioSegment:
    """Overlay a one-shot SFX at a point on the timeline."""
    sfx = load(sfx_path) + gain_db
    return base.overlay(sfx, position=max(0, at_ms))


def export(seg: AudioSegment, out_path: str | Path, fmt: str = "wav") -> Path:
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    seg.export(str(out_path), format=fmt)
    return out_path
