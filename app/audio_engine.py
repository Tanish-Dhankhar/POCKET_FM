"""Fast, deterministic pydub audio editing and assembly.

Kept deliberately small and declarative — the *decisions* (which cue, where) are
made upstream; this module validates bounded edit values and realises them as
audio.  The original concat/music/SFX helpers remain for compatibility with the
current production path, while the dict-based helpers provide a lightweight
timeline backend for the cinematic editor.
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from pydub import AudioSegment
from pydub.silence import detect_leading_silence

from . import config


# Conservative automatic-edit bounds. Larger performance changes should be
# handled by resynthesising a take rather than heavily processing it here.
MIN_RATE = 0.90
MAX_RATE = 1.10
MIN_GAIN_DB = -12.0
MAX_GAIN_DB = 12.0
MAX_FADE_MS = 2_000
MAX_PAUSE_MS = 30_000
MAX_DUCK_DB = 30.0


def _clamp(value: Any, low: float, high: float, default: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(number):
        return default
    return min(high, max(low, number))


def _milliseconds(value: Any, *, maximum: int = MAX_PAUSE_MS,
                  default: int = 0) -> int:
    return int(round(_clamp(value, 0, maximum, default)))


def _silent_like(reference: AudioSegment, duration_ms: int) -> AudioSegment:
    """Return silence with the same basic PCM layout as ``reference``."""
    return (AudioSegment.silent(duration=max(0, duration_ms),
                                frame_rate=reference.frame_rate)
            .set_channels(reference.channels)
            .set_sample_width(reference.sample_width))


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


def trim_edge_silence(clip: AudioSegment,
                      settings: dict[str, Any] | None = None) -> AudioSegment:
    """Lightly remove silence from both edges of a clip.

    ``settings`` accepts ``silence_threshold_dbfs`` (default ``-45``),
    ``chunk_ms`` (default ``5``), ``max_trim_ms`` per edge (default ``200``),
    and ``keep_ms`` (default ``15``).  Trimming is deliberately capped and an
    entirely silent clip is returned unchanged.
    """
    if not clip or clip.dBFS == float("-inf"):
        return clip

    settings = settings or {}
    threshold = _clamp(settings.get("silence_threshold_dbfs", -45.0),
                       -80.0, -15.0, -45.0)
    chunk_ms = _milliseconds(settings.get("chunk_ms", 5), maximum=50, default=5) or 1
    max_trim_ms = _milliseconds(settings.get("max_trim_ms", 200),
                                maximum=2_000, default=200)
    keep_ms = _milliseconds(settings.get("keep_ms", 15), maximum=500, default=15)

    leading = detect_leading_silence(
        clip, silence_threshold=threshold, chunk_size=chunk_ms,
    )
    trailing = detect_leading_silence(
        clip.reverse(), silence_threshold=threshold, chunk_size=chunk_ms,
    )
    trim_start = max(0, min(leading, max_trim_ms) - keep_ms)
    trim_end = max(0, min(trailing, max_trim_ms) - keep_ms)

    # A malformed threshold must never erase a source take.
    if trim_start + trim_end >= len(clip):
        return clip
    end = len(clip) - trim_end if trim_end else len(clip)
    return clip[trim_start:end]


def apply_clip_edits(clip: AudioSegment,
                     edit: dict[str, Any] | None = None) -> AudioSegment:
    """Apply bounded rate, gain and edge fades from an edit dict.

    Recognised keys are ``rate`` (clamped to 0.90–1.10), ``gain_db`` (clamped
    to -12–+12), ``fade_in_ms`` and ``fade_out_ms`` (each clamped to the clip
    length and 2 seconds).  The pydub-only rate operation is a resampling-style
    playback-rate adjustment, so it changes pitch slightly as well as duration;
    large performance changes should be resynthesised instead.
    """
    if not clip:
        return clip
    edit = edit or {}
    rate = _clamp(edit.get("rate", 1.0), MIN_RATE, MAX_RATE, 1.0)
    gain_db = _clamp(edit.get("gain_db", 0.0), MIN_GAIN_DB, MAX_GAIN_DB, 0.0)

    result = clip
    if abs(rate - 1.0) > 1e-6:
        source_rate = result.frame_rate
        playback_rate = max(1, int(round(source_rate * rate)))
        result = result._spawn(
            result.raw_data, overrides={"frame_rate": playback_rate},
        ).set_frame_rate(source_rate)
    if gain_db:
        result = result + gain_db

    fade_in_ms = min(len(result), _milliseconds(
        edit.get("fade_in_ms", 0), maximum=MAX_FADE_MS,
    ))
    fade_out_ms = min(len(result), _milliseconds(
        edit.get("fade_out_ms", 0), maximum=MAX_FADE_MS,
    ))
    if fade_in_ms:
        result = result.fade_in(fade_in_ms)
    if fade_out_ms:
        result = result.fade_out(fade_out_ms)
    return result


def assemble_dialogue(
    items: list[dict[str, Any]],
    edits: list[dict[str, Any]] | None = None,
    *,
    default_pause_ms: int = 0,
) -> tuple[AudioSegment, list[dict[str, Any]], list[int]]:
    """Build independently generated line WAVs on a multivoice timeline.

    ``items`` are ordered dicts with ``line_index``, ``line_id``, ``path`` and
    optional ``speaker``. ``edits`` are keyed by 0-based ``line`` and accept::

        pause_before_ms, pause_after_ms, overlap_previous_ms, interrupt,
        trim_tail_ms, rate, gain_db, fade_in_ms, fade_out_ms

    ``overlap_ms`` is accepted as an alias for ``overlap_previous_ms``. Edge
    trimming is on by default; set ``trim_edge_silence`` false on an edit to
    disable it, or pass ``edge_trim`` settings for threshold/caps.

    The gap before a normal line is
    ``previous.pause_after_ms + pause_before_ms``. When neither adjacent line
    has an explicit pause field, ``default_pause_ms`` is used instead. A positive
    ``overlap_previous_ms`` means actual speech overlap: it ignores those pause
    fields and starts the line that many milliseconds before the previous end,
    bounded so it cannot start before the previous line starts.

    Returns ``(track, segments, offsets)``. Segment ``end_ms`` is the true clip
    end and never includes the following pause; offsets are the segment starts.
    """
    if not items:
        return AudioSegment.silent(duration=0, frame_rate=config.TTS_SAMPLE_RATE), [], []

    by_line: dict[int, dict[str, Any]] = {}
    for raw in edits or []:
        if "line" not in raw:
            continue
        try:
            line = int(raw["line"])
        except (TypeError, ValueError):
            continue
        # Multiple operations for one line compose deterministically; later
        # values replace earlier fields.
        by_line[line] = {**by_line.get(line, {}), **raw}

    prepared: list[tuple[AudioSegment, dict[str, Any], dict[str, Any]]] = []
    for order, item in enumerate(items):
        if "path" not in item:
            raise ValueError(f"dialogue item {order} has no path")
        try:
            line_index = int(item.get("line_index", order))
        except (TypeError, ValueError):
            line_index = order
        edit = {**item, **by_line.get(line_index, {})}
        clip = load(item["path"])
        if edit.get("trim_edge_silence", True):
            edge_settings = edit.get("edge_trim")
            clip = trim_edge_silence(
                clip, edge_settings if isinstance(edge_settings, dict) else None,
            )

        trim_tail_ms = _milliseconds(
            edit.get("trim_tail_ms", 0), maximum=max(0, len(clip) - 1),
        )
        if trim_tail_ms:
            clip = clip[:len(clip) - trim_tail_ms]
        clip = apply_clip_edits(clip, edit)
        prepared.append((clip, {**item, "line_index": line_index}, edit))

    scheduled: list[tuple[AudioSegment, int]] = []
    segments: list[dict[str, Any]] = []
    offsets: list[int] = []
    previous_start = 0
    previous_end = 0
    previous_edit: dict[str, Any] = {}
    default_pause_ms = _milliseconds(default_pause_ms)

    for order, (clip, item, edit) in enumerate(prepared):
        pause_before = _milliseconds(edit.get("pause_before_ms", 0))
        pause_after_previous = _milliseconds(previous_edit.get("pause_after_ms", 0))
        explicit_pause = (
            "pause_before_ms" in edit or "pause_after_ms" in previous_edit
        )
        gap = pause_before + pause_after_previous
        if order and not explicit_pause:
            gap = default_pause_ms

        requested_overlap = _milliseconds(
            edit.get("overlap_previous_ms", edit.get("overlap_ms", 0)),
        ) if order else 0
        # A requested overlap is the actual voiced overlap, not merely a
        # subtraction from an otherwise positive pause. Full simultaneity is
        # allowed, but a malformed value cannot reorder the two line starts.
        max_overlap = max(0, previous_end - previous_start)
        overlap = min(requested_overlap, max_overlap)
        if order == 0:
            start_ms = pause_before
        elif overlap:
            start_ms = previous_end - overlap
        else:
            start_ms = previous_end + gap
        end_ms = start_ms + len(clip)

        offsets.append(start_ms)
        scheduled.append((clip, start_ms))
        segments.append({
            "line_index": item["line_index"],
            "line_id": item.get("line_id") or f"line-{item['line_index'] + 1:04d}",
            "speaker": item.get("speaker", ""),
            "path": str(item["path"]),
            "start_ms": start_ms,
            "end_ms": end_ms,
            "duration_ms": len(clip),
            "pause_before_ms": pause_before,
            "pause_after_ms": _milliseconds(edit.get("pause_after_ms", 0)),
            "overlap_previous_ms": overlap,
            "interrupt": bool(edit.get("interrupt", False)),
            "trim_tail_ms": _milliseconds(
                edit.get("trim_tail_ms", 0), maximum=max(0, len(clip) - 1),
            ),
            "rate": _clamp(edit.get("rate", 1.0), MIN_RATE, MAX_RATE, 1.0),
            "gain_db": _clamp(
                edit.get("gain_db", 0.0), MIN_GAIN_DB, MAX_GAIN_DB, 0.0,
            ),
        })
        previous_start, previous_end, previous_edit = start_ms, end_ms, edit

    final_pause_ms = _milliseconds(previous_edit.get("pause_after_ms", 0))
    total_ms = max(end for _, end in (
        (position, position + len(clip)) for clip, position in scheduled
    )) + final_pause_ms
    canvas = _silent_like(scheduled[0][0], total_ms)
    for clip, position in scheduled:
        canvas = canvas.overlay(clip, position=position)
    return canvas, segments, offsets


def _loop_to(seg: AudioSegment, length_ms: int) -> AudioSegment:
    if len(seg) == 0:
        return AudioSegment.silent(duration=length_ms)
    reps = (length_ms // len(seg)) + 1
    return (seg * reps)[:length_ms]


def place_looped_ambience(base: AudioSegment,
                          cue: dict[str, Any]) -> AudioSegment:
    """Overlay a looped ambience cue without changing the base duration.

    ``cue`` requires ``path`` and accepts ``start_ms`` (default 0), ``end_ms``
    (default base end), ``gain_db`` (default -24), ``fade_in_ms`` and
    ``fade_out_ms`` (defaults 300). Invalid/out-of-range spans are no-ops.
    """
    if "path" not in cue or not base:
        return base
    start_ms = min(len(base), _milliseconds(cue.get("start_ms", 0),
                                            maximum=len(base)))
    end_ms = min(len(base), _milliseconds(cue.get("end_ms", len(base)),
                                          maximum=len(base), default=len(base)))
    span = end_ms - start_ms
    if span <= 0:
        return base

    ambience = _loop_to(load(cue["path"]), span)
    gain_db = _clamp(cue.get("gain_db", -24.0), -60.0, 6.0, -24.0)
    ambience = ambience + gain_db
    fade_in_ms = min(span, _milliseconds(
        cue.get("fade_in_ms", 300), maximum=MAX_FADE_MS, default=300,
    ))
    fade_out_ms = min(span, _milliseconds(
        cue.get("fade_out_ms", 300), maximum=MAX_FADE_MS, default=300,
    ))
    if fade_in_ms:
        ambience = ambience.fade_in(fade_in_ms)
    if fade_out_ms:
        ambience = ambience.fade_out(fade_out_ms)
    return base.overlay(ambience, position=start_ms)


def _dialogue_regions(dialogue_intervals: list[dict[str, Any]],
                      cue_start_ms: int, span_ms: int,
                      hold_ms: int) -> list[tuple[int, int]]:
    """Return sorted, merged voiced regions local to a cue."""
    regions: list[tuple[int, int]] = []
    cue_end_ms = cue_start_ms + span_ms
    for interval in dialogue_intervals:
        try:
            start = int(round(float(interval["start_ms"])))
            end = int(round(float(interval["end_ms"])))
        except (KeyError, TypeError, ValueError, OverflowError):
            continue
        start = max(cue_start_ms, start) - cue_start_ms
        end = min(cue_end_ms, end) - cue_start_ms
        if end > start:
            regions.append((start, end))
    regions.sort()

    merged: list[list[int]] = []
    for start, end in regions:
        if not merged or start > merged[-1][1] + hold_ms:
            merged.append([start, end])
        else:
            merged[-1][1] = max(merged[-1][1], end)
    return [(start, end) for start, end in merged]


def _apply_duck_envelope(music: AudioSegment,
                         regions: list[tuple[int, int]],
                         duck_db: float, attack_ms: int,
                         release_ms: int) -> AudioSegment:
    """Apply a non-overlapping piecewise gain envelope to a music segment."""
    if not regions or not music or duck_db >= 0:
        return music

    # Expand and merge regions so one release cannot collide with the next
    # attack; this also prevents audible pumping across short dialogue gaps.
    envelopes: list[list[int]] = []
    for speech_start, speech_end in regions:
        duck_start = max(0, speech_start - attack_ms)
        duck_end = min(len(music), speech_end + release_ms)
        if envelopes and duck_start <= envelopes[-1][3]:
            envelopes[-1][2] = max(envelopes[-1][2], speech_end)
            envelopes[-1][3] = max(envelopes[-1][3], duck_end)
        else:
            envelopes.append([duck_start, speech_start, speech_end, duck_end])

    result = music[:0]
    cursor = 0
    for duck_start, speech_start, speech_end, duck_end in envelopes:
        if duck_start > cursor:
            result += music[cursor:duck_start]

        attack = music[duck_start:speech_start]
        if attack:
            attack = attack.fade(from_gain=0.0, to_gain=duck_db,
                                 start=0, end=len(attack))
            result += attack

        core_start = max(speech_start, duck_start)
        core_end = max(core_start, min(speech_end, len(music)))
        if core_end > core_start:
            result += music[core_start:core_end] + duck_db

        release_start = max(core_end, speech_end)
        if duck_end > release_start:
            release = music[release_start:duck_end].fade(
                from_gain=duck_db, to_gain=0.0,
                start=0, end=duck_end - release_start,
            )
            result += release
        cursor = max(cursor, duck_end)

    if cursor < len(music):
        result += music[cursor:]
    # Millisecond slicing/fade rounding can differ by a frame; force the original
    # duration so overlays stay deterministic.
    return result[:len(music)] + _silent_like(music, max(0, len(music) - len(result)))


def place_music_ducked(base: AudioSegment, cue: dict[str, Any],
                       dialogue_intervals: list[dict[str, Any]]) -> AudioSegment:
    """Overlay looped music with a dialogue-aware, deterministic duck envelope.

    ``cue`` requires ``path`` and accepts ``start_ms``, ``end_ms``, ``gain_db``
    (default the legacy music level), ``duck_db`` (additional reduction,
    default -10), ``attack_ms`` (80), ``hold_ms`` (180), ``release_ms`` (420),
    and cue ``fade_in_ms`` / ``fade_out_ms`` (``fade_ms`` remains a backwards-
    compatible shorthand). ``dialogue_intervals`` are dicts containing ``start_ms``
    and ``end_ms``; the segment dicts returned by :func:`assemble_dialogue` can
    be passed directly.
    """
    if "path" not in cue or not base:
        return base
    start_ms = min(len(base), _milliseconds(cue.get("start_ms", 0),
                                            maximum=len(base)))
    end_ms = min(len(base), _milliseconds(cue.get("end_ms", len(base)),
                                          maximum=len(base), default=len(base)))
    span = end_ms - start_ms
    if span <= 0:
        return base

    music = _loop_to(load(cue["path"]), span)
    gain_db = _clamp(cue.get("gain_db", config.MUSIC_DUCK_DB),
                     -60.0, 6.0, float(config.MUSIC_DUCK_DB))
    duck_db = _clamp(cue.get("duck_db", -10.0),
                     -MAX_DUCK_DB, 0.0, -10.0)
    attack_ms = _milliseconds(cue.get("attack_ms", 80), maximum=2_000, default=80)
    hold_ms = _milliseconds(cue.get("hold_ms", 180), maximum=2_000, default=180)
    release_ms = _milliseconds(cue.get("release_ms", 420),
                               maximum=5_000, default=420)
    regions = _dialogue_regions(dialogue_intervals, start_ms, span, hold_ms)
    music = _apply_duck_envelope(music, regions, duck_db, attack_ms, release_ms)
    music = music + gain_db

    shorthand = cue.get("fade_ms", config.MUSIC_FADE_MS)
    fade_in_ms = min(span, _milliseconds(
        cue.get("fade_in_ms", shorthand),
        maximum=MAX_FADE_MS, default=config.MUSIC_FADE_MS,
    ))
    fade_out_ms = min(span, _milliseconds(
        cue.get("fade_out_ms", shorthand),
        maximum=MAX_FADE_MS, default=config.MUSIC_FADE_MS,
    ))
    if fade_in_ms:
        music = music.fade_in(fade_in_ms)
    if fade_out_ms:
        music = music.fade_out(fade_out_ms)
    return base.overlay(music, position=start_ms)


def mix_and_master(stems: list[dict[str, Any]],
                   settings: dict[str, Any] | None = None) -> AudioSegment:
    """Safely sum stems, then apply fast RMS/peak normalization.

    Each stem contains either ``audio`` (:class:`AudioSegment`) or ``path``, plus
    optional ``position_ms`` and ``gain_db``. ``settings`` accepts
    ``duration_ms``, ``headroom_db`` (default 6), ``target_dbfs`` (default -18),
    ``peak_ceiling_dbfs`` (default -1), and ``normalize`` (default true).

    This is deliberately a fast pydub master, not an LUFS/true-peak mastering
    replacement. It reserves worst-case summing headroom, targets segment dBFS,
    and caps sample peak. A production delivery pass can replace it later.
    """
    settings = settings or {}
    resolved: list[tuple[AudioSegment, int, float]] = []
    for order, stem in enumerate(stems):
        audio = stem.get("audio")
        if audio is None and stem.get("path") is not None:
            audio = load(stem["path"])
        if not isinstance(audio, AudioSegment):
            raise ValueError(f"stem {order} requires 'audio' or 'path'")
        position_ms = _milliseconds(stem.get("position_ms", 0),
                                    maximum=24 * 60 * 60 * 1_000)
        gain_db = _clamp(stem.get("gain_db", 0.0), -60.0, 24.0, 0.0)
        resolved.append((audio, position_ms, gain_db))

    if not resolved:
        duration = _milliseconds(settings.get("duration_ms", 0),
                                 maximum=24 * 60 * 60 * 1_000)
        return AudioSegment.silent(duration=duration,
                                   frame_rate=config.TTS_SAMPLE_RATE)

    latest_tail = max(position + len(audio) for audio, position, _ in resolved)
    requested_duration = _milliseconds(
        settings.get("duration_ms", latest_tail),
        maximum=24 * 60 * 60 * 1_000, default=latest_tail,
    )
    duration = max(latest_tail, requested_duration)
    reference = resolved[0][0]
    mix = _silent_like(reference, duration)

    requested_headroom = _clamp(settings.get("headroom_db", 6.0),
                                0.0, 24.0, 6.0)
    linear_sum = sum(10 ** (gain_db / 20.0) for _, _, gain_db in resolved)
    worst_case_sum_db = 20.0 * math.log10(max(1.0, linear_sum))
    safety_attenuation = requested_headroom + worst_case_sum_db
    for audio, position, gain_db in resolved:
        mix = mix.overlay(audio + gain_db - safety_attenuation,
                          position=position)

    if not settings.get("normalize", True) or mix.dBFS == float("-inf"):
        return mix

    target_dbfs = _clamp(settings.get("target_dbfs", -18.0),
                         -40.0, -6.0, -18.0)
    peak_ceiling = _clamp(settings.get("peak_ceiling_dbfs", -1.0),
                          -12.0, 0.0, -1.0)
    target_gain = target_dbfs - mix.dBFS
    peak_limited_gain = peak_ceiling - mix.max_dBFS
    return mix + min(target_gain, peak_limited_gain)


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
