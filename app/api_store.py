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
from pydantic import BaseModel, Field, field_validator
from starlette.concurrency import run_in_threadpool

from . import config, episode_service, jobs, prompts, schemas, store, story_service
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
    lines: list[dict[str, Any]] = Field(max_length=config.MAX_SCRIPT_LINES)

    @field_validator("lines")
    @classmethod
    def validate_lines(cls, lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
        for line in lines:
            text = line.get("text")
            if isinstance(text, str) and len(text) > config.MAX_SCRIPT_LINE_CHARS:
                raise ValueError("script line exceeds the configured size limit")
        return lines


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


class RemixBody(BaseModel):
    instruction: str


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def capacity_error(exc: jobs.QueueFullError) -> HTTPException:
    """429 carrying a code the UI matches on to raise its at-capacity toast."""
    return HTTPException(429, jobs.capacity_detail(exc), headers={"Retry-After": "30"})


def _require(series_id: str) -> None:
    if not store.series_dir(series_id).exists():
        raise HTTPException(404, f"unknown series {series_id}")


async def _read_upload(file: UploadFile) -> bytes:
    """Read uploads in bounded chunks so oversized recordings fail predictably."""
    chunks: list[bytes] = []
    total = 0
    while chunk := await file.read(config.UPLOAD_CHUNK_BYTES):
        total += len(chunk)
        if total > config.MAX_UPLOAD_BYTES:
            raise HTTPException(413, "audio upload exceeds the configured size limit")
        chunks.append(chunk)
    return b"".join(chunks)


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
    new_key = store.character_key(updated)
    if new_key != key:
        path.unlink(missing_ok=True)
        # Carry the portrait across too, or it would orphan and vanish from the UI.
        old_image = store.character_image_path(series_id, key)
        if old_image.exists():
            new_image = store.character_image_path(series_id, new_key)
            new_image.parent.mkdir(parents=True, exist_ok=True)
            old_image.replace(new_image)
    store.save_character(series_id, updated)
    store.save_index(series_id)
    return {**updated,
            "has_image": store.character_image_path(series_id, new_key).exists()}


# --------------------------------------------------------------------------- #
# artwork (generated by app/image_service.py; absent until then)
# --------------------------------------------------------------------------- #
@router.get("/series/{series_id}/thumbnail")
def get_thumbnail(series_id: str) -> FileResponse:
    _require(series_id)
    path = store.thumbnail_path(series_id)
    if not path.exists():
        raise HTTPException(404, "thumbnail not generated yet")
    return FileResponse(path, media_type="image/png",
                        filename=f"{series_id}_thumbnail.png")


@router.get("/series/{series_id}/characters/{key}/image")
def get_character_image(series_id: str, key: str) -> FileResponse:
    _require(series_id)
    path = store.character_image_path(series_id, key)
    if not path.exists():
        raise HTTPException(404, f"no image for character '{key}'")
    return FileResponse(path, media_type="image/png", filename=f"{key}.png")



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
    # The curve is scored off the outlines, so an edit invalidates it.
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
    except jobs.QueueFullError as exc:
        raise capacity_error(exc) from exc
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post("/series/{series_id}/episodes/{number}/remix", status_code=202)
def remix_episode(series_id: str, number: int, body: RemixBody) -> dict:
    """Redesign music/effects and remix existing dialogue without new TTS."""
    _require(series_id)
    if number not in store.episode_numbers(series_id):
        raise HTTPException(404, f"episode {number} is not in the plan")
    instruction = body.instruction.strip()
    if not instruction:
        raise HTTPException(422, "audio direction cannot be empty")
    try:
        return episode_service.start_episode_remix_job(
            series_id, number, instruction)
    except jobs.QueueFullError as exc:
        raise capacity_error(exc) from exc
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

    The initial graph node creates this in parallel with the questions. This
    endpoint normally returns the persisted draft without another model call;
    the fallback supports series created before draft caching was added.
    """
    _require(series_id)
    inp = store.load_input(series_id)
    card = store.load_confirmation_draft(series_id)
    if not card:
        # Only the uncached fallback reaches the model, so only it needs a slot.
        try:
            with jobs.story_slot():
                card = generate_structured(
                    prompts.confirm_card(inp["idea"]),
                    schemas.ConfirmCard, task="confirm_card", system=prompts.SYSTEM,
                ).model_dump()
        except jobs.QueueFullError as exc:
            raise capacity_error(exc) from exc
        store.save_confirmation_draft(series_id, card)

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
    try:
        return story_service.start_analysis_job(series_id)
    except jobs.QueueFullError as exc:
        raise capacity_error(exc) from exc


# --------------------------------------------------------------------------- #
# emotional curve (top-3 tracked emotions across the episode plan)
# --------------------------------------------------------------------------- #
@router.get("/series/{series_id}/emotional-curve")
def get_emotional_curve(series_id: str) -> dict:
    _require(series_id)
    return store.load_emotional_curve(series_id)


@router.post("/series/{series_id}/emotional-curve/regenerate", status_code=202)
def regenerate_emotional_curve(series_id: str) -> dict:
    """Kick off a background job that recharts the emotional arc.

    Requires the episode plan to exist — the curve is scored per planned episode,
    so there is nothing to chart before then.
    """
    _require(series_id)
    if not store.episode_numbers(series_id):
        raise HTTPException(409, "generate the episode plan before building an emotional curve")
    try:
        return story_service.start_emotional_curve_job(series_id)
    except jobs.QueueFullError as exc:
        raise capacity_error(exc) from exc


@router.post("/series/{series_id}/refine", status_code=202)
def refine_series(series_id: str, body: RefinementBody) -> dict:
    _require(series_id)
    instruction = body.instruction.strip()
    if not instruction:
        raise HTTPException(422, "refinement instruction cannot be empty")
    try:
        return story_service.start_refinement_job(series_id, instruction)
    except jobs.QueueFullError as exc:
        raise capacity_error(exc) from exc


@router.post("/series/{series_id}/episodes/{number}/evaluate")
def evaluate_episode(series_id: str, number: int) -> dict:
    _require(series_id)
    if number not in store.episode_numbers(series_id):
        raise HTTPException(404, f"unknown episode {number}")
    try:
        with jobs.story_slot():
            return story_service.evaluate_episode(series_id, number)
    except jobs.QueueFullError as exc:
        raise capacity_error(exc) from exc
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
        try:
            with jobs.story_slot():
                render_line(_SAMPLE_LINE, voice_id, path, cache_dir=config.TTS_CACHE_DIR)
        except jobs.QueueFullError as exc:
            raise capacity_error(exc) from exc
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
    data = await _read_upload(file)
    name = Path(file.filename or "source.wav").name
    path = store.save_source_audio(series_id, data, name)
    return {"saved": str(path), "bytes": len(data)}


@router.post("/transcribe")
async def transcribe(file: UploadFile = File(...)) -> dict:
    """Speech -> text for the mic flow.

    Flash-Lite accepts audio input directly, so no separate STT model is needed.
    Returns the transcript only; the caller then POSTs it to /series as the idea.
    """
    data = await _read_upload(file)
    if not data:
        raise HTTPException(400, "empty audio upload")
    mime = file.content_type or "audio/webm"
    try:
        with jobs.story_slot():
            text = await run_in_threadpool(transcribe_audio, data, mime)
    except jobs.QueueFullError as exc:
        raise capacity_error(exc) from exc
    except Exception as exc:
        raise HTTPException(502, f"transcription failed: {exc}") from exc
    if not text.strip():
        raise HTTPException(422, "could not hear any speech in that recording")
    return {"transcript": text, "bytes": len(data), "mime": mime}
