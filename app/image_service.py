"""Series artwork: one thumbnail per series, up to N character portraits.

Runs off the back of the blueprint — the first moment both the story world and
the characters' physical descriptions actually exist. Everything here is
generate-once: an image already on disk is returned untouched, so refining the
story never redraws (or re-bills) art the creator has already seen.

Nothing in this module is allowed to break story generation. Every generation is
isolated, and a failure is logged and skipped rather than raised.
"""
from __future__ import annotations

import logging
from typing import Any

from . import config, images, jobs, prompts, store

_LOG = logging.getLogger(__name__)


def _relative(series_id: str, path) -> str:
    """Path relative to the series folder, so the folder stays portable."""
    return path.relative_to(store.series_dir(series_id)).as_posix()


# --------------------------------------------------------------------------- #
# thumbnail
# --------------------------------------------------------------------------- #
def generate_thumbnail(series_id: str) -> str | None:
    """Render the series cover art. Returns its relative path, or None."""
    path = store.thumbnail_path(series_id)
    if path.exists():
        return _relative(series_id, path)

    index = store.load_index(series_id)
    blueprint = store.load_blueprint(series_id)
    written = images.generate_image(prompts.thumbnail_image(index, blueprint), path)
    return _relative(series_id, written) if written else None


# --------------------------------------------------------------------------- #
# character portraits
# --------------------------------------------------------------------------- #
def select_characters(characters: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The cast that gets drawn: never the narrator, never without a description.

    Keeps `load_characters` order (narrator first, then alphabetical) so the same
    faces are chosen every run, and caps the count so a large roster can't turn
    into an unbounded image bill.
    """
    eligible = [
        ch for ch in characters
        if not ch.get("is_narrator")
        and (ch.get("physical_persona") or ch.get("description"))
    ]
    return eligible[:config.MAX_CHARACTER_IMAGES]


def generate_character_image(series_id: str, character: dict[str, Any]) -> str | None:
    """Render one character portrait. Returns its relative path, or None."""
    path = store.character_image_path(series_id, store.character_key(character))
    if path.exists():
        return _relative(series_id, path)

    blueprint = store.load_blueprint(series_id)
    written = images.generate_image(
        prompts.character_image(character, blueprint), path)
    return _relative(series_id, written) if written else None


# --------------------------------------------------------------------------- #
# orchestration
# --------------------------------------------------------------------------- #
def ensure_series_images(series_id: str,
                         handle: jobs.JobHandle | None = None) -> dict[str, Any]:
    """Generate whatever artwork this series is still missing."""
    result: dict[str, Any] = {"series_id": series_id,
                              "thumbnail": None, "characters": {}}
    if not images.enabled():
        result["skipped"] = "images are disabled"
        return result

    if handle:
        handle.step("thumbnail", "Painting the series cover")
    try:
        result["thumbnail"] = generate_thumbnail(series_id)
    except Exception:  # noqa: BLE001 - artwork must never break the pipeline
        _LOG.exception("thumbnail_failed series=%s", series_id)

    if handle and handle.cancelled():
        return {**result, "cancelled": True, "step": "thumbnail"}

    cast = select_characters(store.load_characters(series_id))
    if handle:
        handle.step("characters", "Drawing the cast")
    for done, character in enumerate(cast, start=1):
        if handle and handle.cancelled():
            return {**result, "cancelled": True, "step": "characters"}
        key = store.character_key(character)
        try:
            result["characters"][key] = generate_character_image(series_id, character)
        except Exception:  # noqa: BLE001 - one bad portrait shouldn't lose the rest
            _LOG.exception("character_image_failed series=%s key=%s", series_id, key)
        if handle:
            handle.progress(done, len(cast), f"Drew {done} of {len(cast)}")

    return result


def start_images_job(series_id: str) -> dict[str, Any] | None:
    """Generate artwork in the background. No-op when images are disabled.

    Deduped per series, so the blueprint being regenerated while a run is still
    in flight rejoins it instead of paying for a second set of images.
    """
    if not images.enabled():
        return None
    try:
        return jobs.start_or_rejoin(
            "images",
            lambda handle: ensure_series_images(series_id, handle),
            dedupe_key=("images", series_id),
            series_id=series_id, steps=["thumbnail", "characters"],
        )
    except Exception:  # noqa: BLE001 - includes a full queue; art is never critical
        _LOG.exception("images_job_not_started series=%s", series_id)
        return None
