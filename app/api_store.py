"""Store-backed REST API for the frontend.

Everything here reads from and writes to the series folder on disk (app/store.py)
rather than the in-process graph state, so the UI can load a series after a
restart and edits survive independently of the pipeline.

Mounted under /studio by app/main.py.
"""
from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
from pydantic import BaseModel

from . import character_art, config, episode_service, jobs, prompts, schemas, store, story_service
from .llm import generate_structured, transcribe_audio
from .tts import render_line

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
    details: str | None = None
    physical_persona: str | None = None
    backstory: str | None = None
    vocal_direction: str | None = None
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


class ConfirmationBody(BaseModel):
    title: str
    genre: str
    setting: str
    include_narrator: bool
    ep_count: int
    ep_minutes: int
    genre_tags: list[str]
    theme_tags: list[str]


class RefinementBody(BaseModel):
    instruction: str


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
    swot_path = d / "swot.json"
    swot = store.read_json(swot_path, {}) or {}
    if swot:
        swot["stale"] = True
        store.write_json(swot_path, swot)
    store.mark_emotional_curve_stale(series_id)
    store.mark_all_character_portraits_stale(series_id)
    store.save_index(series_id)
    return store.load_blueprint(series_id)


# --------------------------------------------------------------------------- #
# characters
# --------------------------------------------------------------------------- #
@router.get("/series/{series_id}/characters")
def get_characters(series_id: str) -> dict:
    _require(series_id)
    return {"characters": store.load_characters(series_id)}


_PORTRAIT_FIELDS = {"name", "gender", "description", "personality",
                    "physical_persona", "backstory", "is_narrator"}


@router.patch("/series/{series_id}/characters/{key}")
def patch_character(series_id: str, key: str, body: CharacterPatch) -> dict:
    """`key` is the file stem — a character slug, or 'narrator'."""
    _require(series_id)
    path = store.characters_dir(series_id) / f"{key}.json"
    current = store.read_json(path, None)
    if current is None:
        raise HTTPException(404, f"unknown character '{key}'")
    patch = body.model_dump(exclude_none=True)
    updated = {**current, **patch}
    # A rename must move the file so the slug stays in sync with the name.
    new_key = "narrator" if updated.get("is_narrator") else store.slug(updated["name"])
    if new_key != key:
        path.unlink(missing_ok=True)
        old_portrait = store.character_portrait_path(series_id, key)
        old_portrait.unlink(missing_ok=True)
        updated.pop("portrait_generated_at", None)
        updated["portrait_stale"] = False
    elif _PORTRAIT_FIELDS.intersection(patch) and updated.get("portrait_generated_at"):
        updated["portrait_stale"] = True
    store.save_character(series_id, updated)
    store.save_index(series_id)
    return updated


@router.get("/series/{series_id}/characters/{key}/portrait")
def get_character_portrait(series_id: str, key: str) -> FileResponse:
    """A character's concept-art portrait, rendered lazily on first request.

    Mirrors /voices/{id}/sample: the first load costs one Gemini image call,
    every later load is an instant file read — until the character or the
    story's genre/tone/setting changes, which flips it stale for one more render.
    """
    _require(series_id)
    try:
        path = character_art.ensure_portrait(series_id, key)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    except Exception as exc:  # rate limit / model error
        raise HTTPException(503, f"could not render portrait: {exc}") from exc
    return FileResponse(path, media_type="image/png", filename=f"{key}.png")


@router.post("/series/{series_id}/characters/{key}/portrait/regenerate")
def regenerate_character_portrait(series_id: str, key: str) -> dict:
    _require(series_id)
    try:
        character_art.ensure_portrait(series_id, key, force=True)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(503, f"could not render portrait: {exc}") from exc
    character = store.load_character(series_id, key) or {}
    return {"key": key, "generated_at": character.get("portrait_generated_at"),
            "stale": character.get("portrait_stale", False)}


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
    evaluation = store.load_episode(series_id, number).get("evaluation", {})
    if evaluation:
        evaluation["stale"] = True
        store.save_episode_evaluation(series_id, number, evaluation)
    store.save_index(series_id)
    return {"number": number, "lines": len(body.lines),
            "status": store.episode_status(series_id, number)}


@router.put("/series/{series_id}/episodes/{number}/outline")
def put_outline(series_id: str, number: int, body: OutlinePatch) -> dict:
    _require(series_id)
    outline = {**body.outline, "number": number}
    store.save_episode_outline(series_id, outline)
    store.mark_emotional_curve_stale(series_id)
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
# episode generation (long-running -> job)
# --------------------------------------------------------------------------- #
@router.post("/series/{series_id}/episodes/{number}/generate", status_code=202)
def generate_episode(series_id: str, number: int,
                     force_script: bool = False) -> dict:
    """Kick off script -> voices -> sound -> mix for ONE episode.

    Returns 202 with a job id; poll /studio/jobs/{id} for progress. Clicking twice
    rejoins the in-flight job rather than starting a duplicate TTS run.
    Pass force_script=true to rewrite the script instead of reusing it.
    """
    _require(series_id)
    if number not in store.episode_numbers(series_id):
        raise HTTPException(404, f"episode {number} is not in the plan")
    try:
        return episode_service.start_episode_job(
            series_id, number, force_script=force_script)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.get("/jobs/{job_id}")
def get_job(job_id: str) -> dict:
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(404, f"unknown job {job_id}")
    return job


@router.post("/jobs/{job_id}/cancel")
def cancel_job(job_id: str) -> dict:
    """Cooperative cancel — takes effect at the next step boundary."""
    if not jobs.cancel(job_id):
        raise HTTPException(409, "job is not cancellable")
    return {"cancelled": job_id}


# --------------------------------------------------------------------------- #
# confirm card (pre-blueprint summary for the wizard)
# --------------------------------------------------------------------------- #
@router.post("/series/{series_id}/confirm-card")
def confirm_card(series_id: str) -> dict:
    """Title + narrator suggestion + recommended episode config.

    The graph only recommends an episode count *after* the blueprint, but the
    wizard's confirm step comes first — so this is one cheap Flash-Lite call over
    the idea and the creator's answers. The title is persisted immediately.
    """
    _require(series_id)
    inp = store.load_input(series_id)
    bp = store.load_blueprint(series_id)
    extracted = {k: bp.get(k) for k in
                 ("genre", "theme", "tone", "setting", "language", "logline")}

    card = generate_structured(
        prompts.confirm_card(inp["idea"], extracted, inp["clarification_answers"]),
        schemas.ConfirmCard, thinking=config.THINK_LOW, system=prompts.SYSTEM,
    ).model_dump()

    store.save_index(series_id, title=card["title"], genre=card["genre"])
    return card


@router.post("/series/{series_id}/confirmations")
def save_confirmations(series_id: str, body: ConfirmationBody) -> dict:
    _require(series_id)
    values = body.model_dump()
    if len({tag.strip().lower() for tag in values["genre_tags"] if tag.strip()}) != 4:
        raise HTTPException(422, "exactly four unique genre tags are required")
    if len({tag.strip().lower() for tag in values["theme_tags"] if tag.strip()}) != 4:
        raise HTTPException(422, "exactly four unique theme tags are required")
    store.save_confirmations(series_id, values)
    store.save_index(series_id, title=body.title, genre=body.genre,
                     include_narrator=body.include_narrator,
                     ep_count=body.ep_count, ep_minutes=body.ep_minutes)
    d = store.blueprint_dir(series_id)
    genre = store.read_json(d / "genre.json", {}) or {}
    genre.update({"genre": body.genre, "setting": body.setting, "tags": body.genre_tags})
    store.write_json(d / "genre.json", genre)
    theme = store.read_json(d / "theme.json", {}) or {}
    theme["confirmed_tags"] = body.theme_tags
    store.write_json(d / "theme.json", theme)
    return values


@router.post("/series/{series_id}/analysis/regenerate", status_code=202)
def regenerate_analysis(series_id: str) -> dict:
    _require(series_id)
    return story_service.start_analysis_job(series_id)


# --------------------------------------------------------------------------- #
# emotional curve (top-3 tracked emotions across the episode plan)
# --------------------------------------------------------------------------- #
@router.get("/series/{series_id}/emotional-curve")
def get_emotional_curve(series_id: str) -> dict:
    _require(series_id)
    return store.load_emotional_curve(series_id)


@router.post("/series/{series_id}/emotional-curve/regenerate", status_code=202)
def regenerate_emotional_curve(series_id: str) -> dict:
    """Kick off (or rejoin) the job that charts the top-3 emotions per episode.

    Requires the episode plan to exist — the curve is scored per planned episode,
    so there is nothing to chart until /series has advanced past episode_plan.
    """
    _require(series_id)
    if not store.episode_numbers(series_id):
        raise HTTPException(409, "generate the episode plan before building an emotional curve")
    return story_service.start_emotional_curve_job(series_id)


@router.post("/series/{series_id}/refine", status_code=202)
def refine_series(series_id: str, body: RefinementBody) -> dict:
    _require(series_id)
    instruction = body.instruction.strip()
    if not instruction:
        raise HTTPException(422, "refinement instruction cannot be empty")
    return story_service.start_refinement_job(series_id, instruction)


@router.post("/series/{series_id}/episodes/{number}/evaluate")
def evaluate_episode(series_id: str, number: int) -> dict:
    _require(series_id)
    if number not in store.episode_numbers(series_id):
        raise HTTPException(404, f"unknown episode {number}")
    try:
        return story_service.evaluate_episode(series_id, number)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


# --------------------------------------------------------------------------- #
# voices
# --------------------------------------------------------------------------- #
@router.get("/voices")
def list_voices() -> dict:
    return {"voices": [{"id": name, "style": style}
                       for name, style in config.VOICES.items()]}


_SAMPLE_LINE = (
    "Every story deserves a voice. [pause] Let me tell you how this one begins."
)
_sample_lock = threading.Lock()


@router.get("/voices/{voice_id}/sample")
def voice_sample(voice_id: str) -> FileResponse:
    """A short clip of a voice, rendered on first request and cached forever.

    Pre-generating all 30 would take ~10 min at the free-tier TTS rate, so we
    render lazily: the first preview of a given voice costs one TTS call, every
    later preview is an instant file read.
    """
    if voice_id not in config.VOICES:
        raise HTTPException(404, f"unknown voice {voice_id}")
    path = config.ASSETS_DIR / "voice_samples" / f"{voice_id}.wav"
    if not path.exists():
        # Serialise so parallel hovers over the same voice don't double-render.
        with _sample_lock:
            if not path.exists():
                try:
                    render_line(_SAMPLE_LINE, voice_id, path)
                except Exception as exc:  # rate limit / model error
                    raise HTTPException(503, f"could not render sample: {exc}") from exc
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


@router.post("/transcribe")
async def transcribe(file: UploadFile = File(...)) -> dict:
    """Speech -> text for the mic flow.

    Flash-Lite accepts audio input directly, so no separate STT model is needed.
    Returns the transcript only; the caller then POSTs it to /series as the idea.
    """
    data = await file.read()
    if not data:
        raise HTTPException(400, "empty audio upload")
    mime = file.content_type or "audio/webm"
    try:
        text = transcribe_audio(data, mime)
    except Exception as exc:
        raise HTTPException(502, f"transcription failed: {exc}") from exc
    if not text.strip():
        raise HTTPException(422, "could not hear any speech in that recording")
    return {"transcript": text, "bytes": len(data), "mime": mime}
