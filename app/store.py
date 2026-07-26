"""File-based project store — the source of truth for a series.

Layout (everything the frontend reads/writes lives here):

    output/<series_id>/
    ├── series.json                  # index card: title, genre, stage, counts
    ├── input/
    │   ├── idea.txt                 # the creator's original story text
    │   ├── transcript.txt           # verbatim transcript when input was audio
    │   ├── source.wav               # the raw recording, if any
    │   ├── clarification.json       # the questions that were asked
    │   └── clarification_answers.json
    ├── blueprint/
    │   ├── plot.json                # logline, story_world, main_storyline
    │   ├── theme.json
    │   ├── genre.json               # genre, tone, setting, language
    │   └── characters/
    │       ├── narrator.json        # only when a narrator is used
    │       └── <character-slug>.json
    ├── images/                      # optional artwork (see app/image_service.py)
    │   ├── thumbnail.png
    │   └── characters/<character-slug>.png
    └── episodes/
        └── ep01/
            ├── outline.json         # title, summary, events, emotion, cliffhanger
            ├── script.json          # ordered ScriptLine list
            ├── sound_plan.json      # music + sfx cues
            ├── audio.json           # manifest: offsets, durations, file paths
            ├── lines/               # per-line rendered wavs
            ├── ep01_voices.wav
            └── ep01_final.wav

Design notes:
- Writes are atomic (temp file + replace) so a crash can't leave half a JSON.
- Every reader tolerates a missing file and returns a sensible empty value, so a
  partially-built series still loads in the UI.
- `hydrate()` rebuilds pipeline state from disk, which is what makes the folder —
  not the in-process checkpointer — the real source of truth.
"""
from __future__ import annotations

import json
import re
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import config
from . import databricks_store

_SLUG = re.compile(r"[^a-z0-9]+")

# Fields the loaders derive from the filesystem and attach for the UI. They are
# stripped again on write so they never end up inside a stored record.
_COMPUTED_CHARACTER_FIELDS = {"has_image"}



# --------------------------------------------------------------------------- #
# paths
# --------------------------------------------------------------------------- #
def slug(name: str) -> str:
    """Filesystem-safe key for a character name ('Dr. Ravi Menon' -> 'dr-ravi-menon')."""
    return _SLUG.sub("-", (name or "").strip().lower()).strip("-") or "unnamed"


def series_dir(series_id: str) -> Path:
    return config.OUTPUT_DIR / series_id


def input_dir(series_id: str) -> Path:
    return series_dir(series_id) / "input"


def blueprint_dir(series_id: str) -> Path:
    return series_dir(series_id) / "blueprint"


def characters_dir(series_id: str) -> Path:
    return blueprint_dir(series_id) / "characters"


def episodes_dir(series_id: str) -> Path:
    return series_dir(series_id) / "episodes"


def episode_dir(series_id: str, number: int) -> Path:
    return episodes_dir(series_id) / f"ep{int(number):02d}"


def lines_dir(series_id: str, number: int) -> Path:
    return episode_dir(series_id, number) / "lines"


def images_dir(series_id: str) -> Path:
    return series_dir(series_id) / "images"


def character_images_dir(series_id: str) -> Path:
    return images_dir(series_id) / "characters"


def thumbnail_path(series_id: str) -> Path:
    return images_dir(series_id) / "thumbnail.png"


def character_image_path(series_id: str, key: str) -> Path:
    return character_images_dir(series_id) / f"{key}.png"


def character_key(character: dict) -> str:
    """The file stem a character is stored under ('narrator', or its slug)."""
    return "narrator" if character.get("is_narrator") else slug(character.get("name", ""))


# --------------------------------------------------------------------------- #
# primitive read / write
# --------------------------------------------------------------------------- #
def write_json(path: Path, data: Any) -> Path:
    """Atomically write JSON (temp file + replace)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str),
                   encoding="utf-8")
    tmp.replace(path)
    return path


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


def write_text(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    tmp.write_text(text or "", encoding="utf-8")
    tmp.replace(path)
    return path


def read_text(path: Path, default: str = "") -> str:
    return path.read_text(encoding="utf-8") if path.exists() else default


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# --------------------------------------------------------------------------- #
# input/
# --------------------------------------------------------------------------- #
def save_idea(series_id: str, idea: str, *, transcript: str | None = None) -> None:
    write_text(input_dir(series_id) / "idea.txt", idea)
    if transcript is not None:
        write_text(input_dir(series_id) / "transcript.txt", transcript)


def save_source_audio(series_id: str, data: bytes, filename: str = "source.wav") -> Path:
    path = input_dir(series_id) / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def save_clarification(series_id: str, clarification: dict) -> None:
    write_json(input_dir(series_id) / "clarification.json", clarification)


def save_clarification_answers(series_id: str, answers: list[dict]) -> None:
    write_json(input_dir(series_id) / "clarification_answers.json", answers)


def save_confirmation_draft(series_id: str, card: dict) -> None:
    write_json(input_dir(series_id) / "confirmation_draft.json", card)


def load_confirmation_draft(series_id: str) -> dict[str, Any]:
    return read_json(input_dir(series_id) / "confirmation_draft.json", {}) or {}


def save_confirmations(series_id: str, values: dict[str, Any]) -> None:
    write_json(input_dir(series_id) / "confirmations.json", values)


def load_input(series_id: str) -> dict[str, Any]:
    d = input_dir(series_id)
    return {
        "idea": read_text(d / "idea.txt"),
        "transcript": read_text(d / "transcript.txt"),
        "clarification": read_json(d / "clarification.json", {}) or {},
        "clarification_answers": read_json(d / "clarification_answers.json", []) or [],
        "confirmation_draft": load_confirmation_draft(series_id),
        "confirmations": read_json(d / "confirmations.json", {}) or {},
    }


# --------------------------------------------------------------------------- #
# blueprint/  (plot, theme, genre, characters/)
# --------------------------------------------------------------------------- #
def save_blueprint(series_id: str, blueprint: dict, *, meta: dict | None = None) -> None:
    """Split the blueprint into plot.json / theme.json / genre.json + characters/."""
    meta = meta or {}
    bp = blueprint or {}

    write_json(blueprint_dir(series_id) / "plot.json", {
        "logline": bp.get("logline", meta.get("logline", "")),
        "story_world": bp.get("story_world", ""),
        "main_storyline": bp.get("main_storyline", ""),
        "story_beats": bp.get("story_beats", []),
    })
    write_json(blueprint_dir(series_id) / "theme.json", {
        "theme": bp.get("theme", meta.get("theme", "")),
        "tone": bp.get("tone", meta.get("tone", "")),
        "tags": bp.get("theme_tags", meta.get("theme_tags", [])),
    })
    write_json(blueprint_dir(series_id) / "genre.json", {
        "genre": bp.get("genre", meta.get("genre", "")),
        "setting": bp.get("setting", meta.get("setting", "")),
        "language": bp.get("language", meta.get("language", config.DEFAULT_LANGUAGE)),
        "tone": bp.get("tone", meta.get("tone", "")),
        "tags": bp.get("genre_tags", meta.get("genre_tags", [])),
    })

    for ch in bp.get("characters", []) or []:
        save_character(series_id, ch)


def save_character(series_id: str, character: dict) -> Path:
    """One JSON per character; the narrator is always narrator.json."""
    key = character_key(character)
    # `has_image` is derived at read time; drop it so a load -> save round trip
    # (e.g. save_voice_cast) can't bake a stale flag into the file.
    record = {k: v for k, v in character.items() if k not in _COMPUTED_CHARACTER_FIELDS}
    path = write_json(characters_dir(series_id) / f"{key}.json", record)
    databricks_store.sync_character(series_id, key, record)
    return path


def load_characters(series_id: str) -> list[dict]:
    d = characters_dir(series_id)
    if not d.exists():
        return []
    # narrator first, then alphabetical — stable order for the UI
    files = sorted(d.glob("*.json"), key=lambda p: (p.stem != "narrator", p.stem))
    characters = [c for c in (read_json(f) for f in files) if c]
    for ch in characters:
        # Computed at read time, never persisted — the file on disk is the truth.
        ch["has_image"] = character_image_path(series_id, character_key(ch)).exists()
    return characters



def load_blueprint(series_id: str) -> dict[str, Any]:
    d = blueprint_dir(series_id)
    plot = read_json(d / "plot.json", {}) or {}
    theme = read_json(d / "theme.json", {}) or {}
    genre = read_json(d / "genre.json", {}) or {}
    return {
        "logline": plot.get("logline", ""),
        "story_world": plot.get("story_world", ""),
        "main_storyline": plot.get("main_storyline", ""),
        "story_beats": plot.get("story_beats", []),
        "theme": theme.get("theme", ""),
        "theme_tags": theme.get("tags", theme.get("confirmed_tags", [])),
        "tone": theme.get("tone", genre.get("tone", "")),
        "genre": genre.get("genre", ""),
        "genre_tags": genre.get("tags", []),
        "setting": genre.get("setting", ""),
        "language": genre.get("language", ""),
        "emotional_curve": load_emotional_curve(series_id),
        "characters": load_characters(series_id),
        "emotional_curve": load_emotional_curve(series_id),
    }


# --------------------------------------------------------------------------- #
# emotional curve (top-3 tracked emotions across the episode plan)
# --------------------------------------------------------------------------- #
def _emotion_key(label: str, taken: set[str]) -> str:
    """Chart-friendly dataKey for an emotion label ('Cold Betrayal' -> 'cold_betrayal')."""
    key = slug(label).replace("-", "_") or "emotion"
    base = key
    n = 2
    while key in taken:
        key = f"{base}_{n}"
        n += 1
    taken.add(key)
    return key


def emotional_curve_path(series_id: str) -> Path:
    return blueprint_dir(series_id) / "emotional_curve.json"


def save_emotional_curve(series_id: str, analysis: dict[str, Any],
                         episodes: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Persist the top-3 emotion arc, one intensity score per emotion per episode."""
    revision = int(load_index(series_id).get("revision", 1) or 1)
    episodes = episodes if episodes is not None else load_outlines(series_id)
    titles = {int(ep.get("number", 0)): ep.get("title", "") for ep in episodes}

    labels = [
        (analysis.get("emotion_1_label") or "Tension").strip() or "Tension",
        (analysis.get("emotion_2_label") or "Hope").strip() or "Hope",
        (analysis.get("emotion_3_label") or "Grief").strip() or "Grief",
    ]
    taken: set[str] = set()
    keys = [_emotion_key(label, taken) for label in labels]

    points = []
    for row in analysis.get("points", []):
        number = int(row.get("episode", 0) or 0)
        if number <= 0:
            continue
        point = {"episode": number, "beat": f"E{number}", "title": titles.get(number, "")}
        for key, field in zip(keys, ("emotion_1", "emotion_2", "emotion_3")):
            point[key] = max(0, min(100, int(row.get(field, 0) or 0)))
        points.append(point)
    points.sort(key=lambda p: p["episode"])

    dominant_raw = (analysis.get("dominant_emotion") or labels[0]).strip().lower()
    dominant_key = keys[0]
    for label, key in zip(labels, keys):
        if label.strip().lower() == dominant_raw:
            dominant_key = key
            break

    curve = {
        "emotions": [{"key": key, "label": label} for key, label in zip(keys, labels)],
        "points": points,
        "dominant_emotion": dominant_key,
        "summary": analysis.get("summary", ""),
        "source_revision": revision,
        "generated_at": _now(),
        "stale": False,
    }
    write_json(emotional_curve_path(series_id), curve)
    return curve


def load_emotional_curve(series_id: str) -> dict[str, Any]:
    return read_json(emotional_curve_path(series_id), {}) or {}


def mark_emotional_curve_stale(series_id: str) -> None:
    path = emotional_curve_path(series_id)
    curve = read_json(path, {}) or {}
    if curve:
        curve["stale"] = True
        write_json(path, curve)


def save_voice_cast(series_id: str, voice_cast: dict[str, str]) -> None:
    """Voice choice lives on each character file, so edits survive independently."""
    for ch in load_characters(series_id):
        name = ch.get("name", "")
        voice = voice_cast.get(name)
        if voice and ch.get("voice_id") != voice:
            ch["voice_id"] = voice
            save_character(series_id, ch)


def load_voice_cast(series_id: str) -> dict[str, str]:
    return {c["name"]: c["voice_id"]
            for c in load_characters(series_id)
            if c.get("name") and c.get("voice_id")}


# --------------------------------------------------------------------------- #
# episodes/
# --------------------------------------------------------------------------- #
def save_episode_outline(series_id: str, outline: dict) -> Path:
    num = int(outline.get("number", 0))
    path = write_json(episode_dir(series_id, num) / "outline.json", outline)
    databricks_store.sync_episode_outline(series_id, num, outline)
    mark_emotional_curve_stale(series_id)
    return path


def save_episode_script(series_id: str, number: int, lines: list[dict]) -> Path:
    path = write_json(episode_dir(series_id, number) / "script.json", lines)
    databricks_store.sync_episode_script(series_id, number, lines)
    return path


def save_episode_sound_plan(series_id: str, number: int, plan: dict) -> Path:
    path = write_json(episode_dir(series_id, number) / "sound_plan.json", plan)
    databricks_store.sync_episode_sound_plan(series_id, number, plan)
    return path


def save_episode_audio(series_id: str, number: int, manifest: dict) -> Path:
    path = write_json(episode_dir(series_id, number) / "audio.json", manifest)
    databricks_store.sync_episode_audio(series_id, number, manifest)
    return path


def save_episode_evaluation(series_id: str, number: int, evaluation: dict) -> Path:
    return write_json(episode_dir(series_id, number) / "evaluation.json", evaluation)


def load_episode(series_id: str, number: int) -> dict[str, Any]:
    d = episode_dir(series_id, number)
    return {
        "number": number,
        "outline": read_json(d / "outline.json", {}) or {},
        "script": read_json(d / "script.json", []) or [],
        "sound_plan": read_json(d / "sound_plan.json", {}) or {},
        "audio": read_json(d / "audio.json", {}) or {},
        "evaluation": read_json(d / "evaluation.json", {}) or {},
    }


def episode_numbers(series_id: str) -> list[int]:
    d = episodes_dir(series_id)
    if not d.exists():
        return []
    nums = []
    for p in d.iterdir():
        if p.is_dir() and p.name.startswith("ep") and p.name[2:].isdigit():
            nums.append(int(p.name[2:]))
    return sorted(nums)


def load_outlines(series_id: str) -> list[dict]:
    return [o for o in (read_json(episode_dir(series_id, n) / "outline.json")
                        for n in episode_numbers(series_id)) if o]


def load_scripts(series_id: str) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for n in episode_numbers(series_id):
        lines = read_json(episode_dir(series_id, n) / "script.json", []) or []
        if lines:
            out[str(n)] = lines
    return out


def load_sound_plans(series_id: str) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for n in episode_numbers(series_id):
        plan = read_json(episode_dir(series_id, n) / "sound_plan.json")
        if plan:
            out[str(n)] = plan
    return out


def load_audio_manifest(series_id: str) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for n in episode_numbers(series_id):
        info = read_json(episode_dir(series_id, n) / "audio.json")
        if info:
            out[str(n)] = info
    return out


def episode_status(series_id: str, number: int) -> str:
    """planned -> scripted -> voiced -> ready (what the UI shows on each row)."""
    d = episode_dir(series_id, number)
    audio = read_json(d / "audio.json", {}) or {}
    if audio.get("final") and Path(audio["final"]).exists():
        return "ready"
    if audio.get("voices"):
        return "voiced"
    if (d / "script.json").exists():
        return "scripted"
    return "planned"


# --------------------------------------------------------------------------- #
# series.json index card + listing
# --------------------------------------------------------------------------- #
def save_index(series_id: str, **fields: Any) -> dict:
    path = series_dir(series_id) / "series.json"
    card = read_json(path, {}) or {}
    card.update({k: v for k, v in fields.items() if v is not None})
    card["series_id"] = series_id
    card["updated_at"] = _now()
    card.setdefault("created_at", card["updated_at"])
    write_json(path, card)
    databricks_store.sync_series(card)
    return card


def load_index(series_id: str) -> dict:
    card = read_json(series_dir(series_id) / "series.json", {}) or {}
    nums = episode_numbers(series_id)
    card["episode_count"] = len(nums)
    card["generated_count"] = sum(
        1 for n in nums if episode_status(series_id, n) == "ready"
    )
    # Computed at read time. save_index re-reads the raw file, so this never
    # round-trips back into series.json.
    card["has_thumbnail"] = thumbnail_path(series_id).exists()
    return card



def list_series() -> list[dict]:
    if not config.OUTPUT_DIR.exists():
        return []
    cards = []
    for d in config.OUTPUT_DIR.iterdir():
        if d.is_dir() and (d / "series.json").exists():
            cards.append(load_index(d.name))
    return sorted(cards, key=lambda c: c.get("updated_at", ""), reverse=True)


def delete_series(series_id: str) -> bool:
    d = series_dir(series_id)
    if not d.exists():
        return False
    shutil.rmtree(d)
    return True


# --------------------------------------------------------------------------- #
# hydrate: disk -> pipeline state
# --------------------------------------------------------------------------- #
def hydrate(series_id: str) -> dict[str, Any]:
    """Rebuild pipeline state from the folder, so the disk is the source of truth."""
    card = load_index(series_id)
    inp = load_input(series_id)
    bp = load_blueprint(series_id)

    return {
        "series_id": series_id,
        "idea": inp["idea"],
        "title": card.get("title", ""),
        "include_narrator": card.get("include_narrator"),
        "genre": bp["genre"], "theme": bp["theme"], "tone": bp["tone"],
        "language": bp["language"], "setting": bp["setting"],
        "logline": bp["logline"],
        "characters": bp["characters"],
        "clarification": inp["clarification"],
        "clarification_answers": inp["clarification_answers"],
        "confirmation_draft": inp["confirmation_draft"],
        "blueprint": {
            "logline": bp["logline"], "story_world": bp["story_world"],
            "main_storyline": bp["main_storyline"], "story_beats": bp["story_beats"],
            "genre": bp["genre"], "genre_tags": bp["genre_tags"],
            "tone": bp["tone"], "theme": bp["theme"],
            "theme_tags": bp["theme_tags"], "setting": bp["setting"],
            "language": bp["language"], "characters": bp["characters"],
        },
        "episodes": load_outlines(series_id),
        "scripts": load_scripts(series_id),
        "voice_cast": load_voice_cast(series_id),
        "sound_plans": load_sound_plans(series_id),
        "audio_manifest": load_audio_manifest(series_id),
        "arcs": card.get("arcs", []),
        "ep_count": card.get("ep_count", 0),
        "ep_minutes": card.get("ep_minutes", 0),
        "stage": card.get("stage", ""),
    }
