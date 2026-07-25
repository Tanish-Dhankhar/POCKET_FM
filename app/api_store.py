"""Store-backed REST API for the frontend.

Everything here reads from and writes to the series folder on disk (app/store.py)
rather than the in-process graph state, so the UI can load a series after a
restart and edits survive independently of the pipeline.

Mounted under /studio by app/main.py.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
from pydantic import BaseModel

from . import config, store

router = APIRouter(prefix="/studio", tags=["studio"])


# --------------------------------------------------------------------------- #
# request bodies
# --------------------------------------------------------------------------- #
class IndexPatch(BaseModel):
    title: str | None = None
    include_narrator: bool | None = None
    ep_count: int | None = None
    ep_minutes: int | None = None


class CharacterPatch(BaseModel):
    """Any subset of a character's fields; merged into its JSON file."""
    name: str | None = None
    role: str | None = None
    description: str | None = None
    personality: str | None = None
    gender: str | None = None
    relationships: list[str] | None = None
    vocal_signature: str | None = None
    voice_id: str | None = None
    is_narrator: bool | None = None


class ScriptPatch(BaseModel):
    lines: list[dict[str, Any]]


class OutlinePatch(BaseModel):
    outline: dict[str, Any]


class PlotPatch(BaseModel):
    plot: dict[str, Any] | None = None
    theme: dict[str, Any] | None = None
    genre: dict[str, Any] | None = None


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _require(series_id: str) -> None:
    if not store.series_dir(series_id).exists():
        raise HTTPException(404, f"unknown series {series_id}")


# --------------------------------------------------------------------------- #
# series listing (dashboard)
# --------------------------------------------------------------------------- #
@router.get("/series")
def list_series() -> dict:
    return {"series": store.list_series()}


@router.get("/series/{series_id}")
def get_series(series_id: str) -> dict:
    """Everything the ideaboard needs, straight off the disk."""
    _require(series_id)
    card = store.load_index(series_id)
    return {
        "index": card,
        "input": store.load_input(series_id),
        "blueprint": store.load_blueprint(series_id),
        "characters": store.load_characters(series_id),
        "episodes": [
            {**(store.read_json(store.episode_dir(series_id, n) / "outline.json", {}) or {}),
             "number": n,
             "status": store.episode_status(series_id, n)}
            for n in store.episode_numbers(series_id)
        ],
    }


@router.patch("/series/{series_id}")
def patch_series(series_id: str, body: IndexPatch) -> dict:
    _require(series_id)
    return store.save_index(series_id, **body.model_dump(exclude_none=True))


@router.delete("/series/{series_id}")
def delete_series(series_id: str) -> dict:
    if not store.delete_series(series_id):
        raise HTTPException(404, f"unknown series {series_id}")
    return {"deleted": series_id}


# --------------------------------------------------------------------------- #
# blueprint (plot / theme / genre)
# --------------------------------------------------------------------------- #
@router.get("/series/{series_id}/blueprint")
def get_blueprint(series_id: str) -> dict:
    _require(series_id)
    return store.load_blueprint(series_id)


@router.patch("/series/{series_id}/blueprint")
def patch_blueprint(series_id: str, body: PlotPatch) -> dict:
    """Merge edits into plot.json / theme.json / genre.json individually."""
    _require(series_id)
    d = store.blueprint_dir(series_id)
    for key, patch in (("plot", body.plot), ("theme", body.theme), ("genre", body.genre)):
        if patch:
            path = d / f"{key}.json"
            store.write_json(path, {**(store.read_json(path, {}) or {}), **patch})
    store.save_index(series_id)
    return store.load_blueprint(series_id)


# --------------------------------------------------------------------------- #
# characters
# --------------------------------------------------------------------------- #
@router.get("/series/{series_id}/characters")
def get_characters(series_id: str) -> dict:
    _require(series_id)
    return {"characters": store.load_characters(series_id)}


@router.patch("/series/{series_id}/characters/{key}")
def patch_character(series_id: str, key: str, body: CharacterPatch) -> dict:
    """`key` is the file stem — a character slug, or 'narrator'."""
    _require(series_id)
    path = store.characters_dir(series_id) / f"{key}.json"
    current = store.read_json(path, None)
    if current is None:
        raise HTTPException(404, f"unknown character '{key}'")
    updated = {**current, **body.model_dump(exclude_none=True)}
    # A rename must move the file so the slug stays in sync with the name.
    new_key = "narrator" if updated.get("is_narrator") else store.slug(updated["name"])
    if new_key != key:
        path.unlink(missing_ok=True)
    store.save_character(series_id, updated)
    store.save_index(series_id)
    return updated


# --------------------------------------------------------------------------- #
# episodes
# --------------------------------------------------------------------------- #
@router.get("/series/{series_id}/episodes")
def list_episodes(series_id: str) -> dict:
    _require(series_id)
    return {"episodes": [
        {"number": n, "status": store.episode_status(series_id, n),
         **(store.read_json(store.episode_dir(series_id, n) / "outline.json", {}) or {})}
        for n in store.episode_numbers(series_id)
    ]}


@router.get("/series/{series_id}/episodes/{number}")
def get_episode(series_id: str, number: int) -> dict:
    _require(series_id)
    if number not in store.episode_numbers(series_id):
        raise HTTPException(404, f"unknown episode {number}")
    ep = store.load_episode(series_id, number)
    ep["status"] = store.episode_status(series_id, number)
    return ep


@router.put("/series/{series_id}/episodes/{number}/script")
def put_script(series_id: str, number: int, body: ScriptPatch) -> dict:
    """Creator edits to the script. Marks the rendered audio stale."""
    _require(series_id)
    store.save_episode_script(series_id, number, body.lines)
    # Audio no longer matches the script — drop `final` so the UI offers a re-render.
    info = store.load_episode(series_id, number)["audio"]
    if info.pop("final", None):
        info["stale"] = True
        store.save_episode_audio(series_id, number, info)
    store.save_index(series_id)
    return {"number": number, "lines": len(body.lines),
            "status": store.episode_status(series_id, number)}


@router.put("/series/{series_id}/episodes/{number}/outline")
def put_outline(series_id: str, number: int, body: OutlinePatch) -> dict:
    _require(series_id)
    outline = {**body.outline, "number": number}
    store.save_episode_outline(series_id, outline)
    store.save_index(series_id)
    return outline


@router.get("/series/{series_id}/episodes/{number}/audio")
def get_episode_audio(series_id: str, number: int) -> FileResponse:
    _require(series_id)
    info = store.load_episode(series_id, number)["audio"]
    path = info.get("final") or info.get("voices")
    if not path or not Path(path).exists():
        raise HTTPException(404, "audio not generated yet")
    return FileResponse(path, media_type="audio/wav",
                        filename=f"{series_id}_ep{number:02d}.wav")


# --------------------------------------------------------------------------- #
# voices
# --------------------------------------------------------------------------- #
@router.get("/voices")
def list_voices() -> dict:
    return {"voices": [{"id": name, "style": style}
                       for name, style in config.VOICES.items()]}


@router.get("/voices/{voice_id}/sample")
def voice_sample(voice_id: str) -> FileResponse:
    """Pre-generated sample clip (see tools/build_voice_samples.py)."""
    if voice_id not in config.VOICES:
        raise HTTPException(404, f"unknown voice {voice_id}")
    path = config.ASSETS_DIR / "voice_samples" / f"{voice_id}.wav"
    if not path.exists():
        raise HTTPException(
            503, "voice samples not generated yet — run tools/build_voice_samples.py")
    return FileResponse(path, media_type="audio/wav", filename=f"{voice_id}.wav")


# --------------------------------------------------------------------------- #
# audio input (mic)
# --------------------------------------------------------------------------- #
@router.post("/series/{series_id}/input/audio")
async def upload_source_audio(series_id: str, file: UploadFile = File(...)) -> dict:
    """Store the raw recording alongside its transcript in input/."""
    _require(series_id)
    data = await file.read()
    name = Path(file.filename or "source.wav").name
    path = store.save_source_audio(series_id, data, name)
    return {"saved": str(path), "bytes": len(data)}
