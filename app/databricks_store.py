"""Best-effort Databricks mirror of app/store.py.

Local disk (app/store.py) remains the single source of truth for every read
in the product — the studio UI and the generation pipeline never read from
here. Each `sync_*` function below is a dual-write side effect called right
after the matching local write succeeds.

Safety rules (do not relax these):
- If `DATABRICKS_ENABLED` is off (default), every function returns instantly
  without importing the Databricks SDK/connector.
- All work runs on a background executor (see databricks_client.submit), so a
  slow or unreachable warehouse can never add latency to a request or job.
- Any exception is caught and logged here; nothing ever propagates back to
  the caller. A Databricks outage must never break series generation.
- Writes carry the source `updated_at` and only apply if it is newer than or
  equal to what's already in the table, so out-of-order async writes can't
  clobber a more recent one with stale data.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import config
from . import databricks_client as dbx

_LOG = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _table(name: str) -> str:
    return f"{config.DATABRICKS_CATALOG}.{config.DATABRICKS_SCHEMA}.{name}"


def _dispatch(op_name: str, series_id: str, fn) -> None:
    """Submit `fn` to the background executor if Databricks is enabled."""
    if not dbx.is_enabled():
        return

    def _guarded() -> None:
        try:
            fn()
        except Exception:
            _LOG.warning(
                "Databricks sync '%s' failed for series %s", op_name, series_id,
                exc_info=True,
            )

    dbx.submit(_guarded)


# --------------------------------------------------------------------------- #
# series.json -> series table
# --------------------------------------------------------------------------- #
def sync_series(card: dict[str, Any]) -> None:
    series_id = card.get("series_id", "")
    updated_at = card.get("updated_at") or _now()

    def _run() -> None:
        dbx.execute(
            f"""
            MERGE INTO {_table('series')} AS t
            USING (SELECT :series_id AS series_id) AS s
            ON t.series_id = s.series_id
            WHEN MATCHED AND :updated_at >= t.updated_at THEN UPDATE SET
                title = :title, genre = :genre, stage = :stage,
                ep_count = :ep_count, ep_minutes = :ep_minutes,
                episode_count = :episode_count, generated_count = :generated_count,
                updated_at = :updated_at, payload = :payload
            WHEN NOT MATCHED THEN INSERT
                (series_id, title, genre, stage, ep_count, ep_minutes,
                 episode_count, generated_count, created_at, updated_at, payload)
            VALUES
                (:series_id, :title, :genre, :stage, :ep_count, :ep_minutes,
                 :episode_count, :generated_count, :created_at, :updated_at, :payload)
            """,
            {
                "series_id": series_id,
                "title": card.get("title", ""),
                "genre": card.get("genre", ""),
                "stage": card.get("stage", ""),
                "ep_count": card.get("ep_count"),
                "ep_minutes": card.get("ep_minutes"),
                "episode_count": card.get("episode_count"),
                "generated_count": card.get("generated_count"),
                "created_at": card.get("created_at", updated_at),
                "updated_at": updated_at,
                "payload": json.dumps(card, ensure_ascii=False, default=str),
            },
        )

    _dispatch("series", series_id, _run)


# --------------------------------------------------------------------------- #
# blueprint/characters/*.json -> characters table
# --------------------------------------------------------------------------- #
def sync_character(series_id: str, key: str, character: dict[str, Any]) -> None:
    updated_at = _now()

    def _run() -> None:
        dbx.execute(
            f"""
            MERGE INTO {_table('characters')} AS t
            USING (SELECT :series_id AS series_id, :character_key AS character_key) AS s
            ON t.series_id = s.series_id AND t.character_key = s.character_key
            WHEN MATCHED AND :updated_at >= t.updated_at THEN UPDATE SET
                name = :name, is_narrator = :is_narrator, voice_id = :voice_id,
                payload = :payload, updated_at = :updated_at
            WHEN NOT MATCHED THEN INSERT
                (series_id, character_key, name, is_narrator, voice_id, payload, updated_at)
            VALUES
                (:series_id, :character_key, :name, :is_narrator, :voice_id, :payload, :updated_at)
            """,
            {
                "series_id": series_id,
                "character_key": key,
                "name": character.get("name", ""),
                "is_narrator": bool(character.get("is_narrator")),
                "voice_id": character.get("voice_id", ""),
                "payload": json.dumps(character, ensure_ascii=False, default=str),
                "updated_at": updated_at,
            },
        )

    _dispatch("character", series_id, _run)


# --------------------------------------------------------------------------- #
# episodes/epNN/outline.json -> episodes table
# --------------------------------------------------------------------------- #
def sync_episode_outline(series_id: str, number: int, outline: dict[str, Any]) -> None:
    updated_at = _now()

    def _run() -> None:
        dbx.execute(
            f"""
            MERGE INTO {_table('episodes')} AS t
            USING (SELECT :series_id AS series_id, :episode_number AS episode_number) AS s
            ON t.series_id = s.series_id AND t.episode_number = s.episode_number
            WHEN MATCHED AND :updated_at >= t.updated_at THEN UPDATE SET
                outline = :outline, updated_at = :updated_at
            WHEN NOT MATCHED THEN INSERT
                (series_id, episode_number, outline, updated_at)
            VALUES
                (:series_id, :episode_number, :outline, :updated_at)
            """,
            {
                "series_id": series_id,
                "episode_number": int(number),
                "outline": json.dumps(outline, ensure_ascii=False, default=str),
                "updated_at": updated_at,
            },
        )

    _dispatch("episode_outline", series_id, _run)


# --------------------------------------------------------------------------- #
# episodes/epNN/script.json -> scripts table
# --------------------------------------------------------------------------- #
def sync_episode_script(series_id: str, number: int, lines: list[dict[str, Any]]) -> None:
    updated_at = _now()

    def _run() -> None:
        dbx.execute(
            f"""
            MERGE INTO {_table('scripts')} AS t
            USING (SELECT :series_id AS series_id, :episode_number AS episode_number) AS s
            ON t.series_id = s.series_id AND t.episode_number = s.episode_number
            WHEN MATCHED AND :updated_at >= t.updated_at THEN UPDATE SET
                lines = :lines, line_count = :line_count, updated_at = :updated_at
            WHEN NOT MATCHED THEN INSERT
                (series_id, episode_number, lines, line_count, updated_at)
            VALUES
                (:series_id, :episode_number, :lines, :line_count, :updated_at)
            """,
            {
                "series_id": series_id,
                "episode_number": int(number),
                "lines": json.dumps(lines, ensure_ascii=False, default=str),
                "line_count": len(lines or []),
                "updated_at": updated_at,
            },
        )

    _dispatch("episode_script", series_id, _run)


# --------------------------------------------------------------------------- #
# episodes/epNN/sound_plan.json -> sound_plans table
# --------------------------------------------------------------------------- #
def sync_episode_sound_plan(series_id: str, number: int, plan: dict[str, Any]) -> None:
    updated_at = _now()

    def _run() -> None:
        dbx.execute(
            f"""
            MERGE INTO {_table('sound_plans')} AS t
            USING (SELECT :series_id AS series_id, :episode_number AS episode_number) AS s
            ON t.series_id = s.series_id AND t.episode_number = s.episode_number
            WHEN MATCHED AND :updated_at >= t.updated_at THEN UPDATE SET
                plan = :plan, updated_at = :updated_at
            WHEN NOT MATCHED THEN INSERT
                (series_id, episode_number, plan, updated_at)
            VALUES
                (:series_id, :episode_number, :plan, :updated_at)
            """,
            {
                "series_id": series_id,
                "episode_number": int(number),
                "plan": json.dumps(plan, ensure_ascii=False, default=str),
                "updated_at": updated_at,
            },
        )

    _dispatch("episode_sound_plan", series_id, _run)


# --------------------------------------------------------------------------- #
# episodes/epNN/audio.json -> audio_manifest table (+ final wav -> UC Volume)
# --------------------------------------------------------------------------- #
def sync_episode_audio(series_id: str, number: int, manifest: dict[str, Any]) -> None:
    updated_at = _now()
    final_local = manifest.get("final")

    def _run() -> None:
        volume_path = None
        if final_local:
            relative = f"{series_id}/ep{int(number):02d}_final.wav"
            volume_path = dbx.upload_file(Path(final_local), relative)

        dbx.execute(
            f"""
            MERGE INTO {_table('audio_manifest')} AS t
            USING (SELECT :series_id AS series_id, :episode_number AS episode_number) AS s
            ON t.series_id = s.series_id AND t.episode_number = s.episode_number
            WHEN MATCHED AND :updated_at >= t.updated_at THEN UPDATE SET
                voices_path = :voices_path, final_path = :final_path,
                volume_path = COALESCE(:volume_path, t.volume_path),
                total_ms = :total_ms, manifest = :manifest, updated_at = :updated_at
            WHEN NOT MATCHED THEN INSERT
                (series_id, episode_number, voices_path, final_path, volume_path,
                 total_ms, manifest, updated_at)
            VALUES
                (:series_id, :episode_number, :voices_path, :final_path, :volume_path,
                 :total_ms, :manifest, :updated_at)
            """,
            {
                "series_id": series_id,
                "episode_number": int(number),
                "voices_path": manifest.get("voices", ""),
                "final_path": manifest.get("final", ""),
                "volume_path": volume_path,
                "total_ms": manifest.get("total_ms"),
                "manifest": json.dumps(manifest, ensure_ascii=False, default=str),
                "updated_at": updated_at,
            },
        )

    _dispatch("episode_audio", series_id, _run)
