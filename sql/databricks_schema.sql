-- PocketFM Databricks dual-write schema (Phase 1).
--
-- Run this once in the Databricks SQL Editor after the catalog/schema/volume
-- bootstrap. Local disk (app/store.py) stays the source of truth; these
-- tables only ever receive best-effort mirrored copies from
-- app/databricks_store.py.
--
-- Adjust the catalog/schema names below if your .env uses values other than
-- the defaults (DATABRICKS_CATALOG=pocketfm_dev, DATABRICKS_SCHEMA=studio).

CREATE CATALOG IF NOT EXISTS pocketfm_dev;
CREATE SCHEMA IF NOT EXISTS pocketfm_dev.studio;
CREATE VOLUME IF NOT EXISTS pocketfm_dev.studio.audio;

USE CATALOG pocketfm_dev;
USE SCHEMA studio;

-- One row per series (mirrors series.json).
CREATE TABLE IF NOT EXISTS series (
    series_id        STRING NOT NULL,
    title            STRING,
    genre            STRING,
    stage            STRING,
    ep_count         INT,
    ep_minutes       INT,
    episode_count    INT,
    generated_count  INT,
    created_at       STRING,
    updated_at       STRING,
    payload          STRING COMMENT 'full series.json snapshot, JSON-encoded'
) COMMENT 'Mirror of output/<series_id>/series.json';

-- One row per character (mirrors blueprint/characters/<key>.json).
CREATE TABLE IF NOT EXISTS characters (
    series_id       STRING NOT NULL,
    character_key   STRING NOT NULL COMMENT 'slug, or "narrator"',
    name            STRING,
    is_narrator     BOOLEAN,
    voice_id        STRING,
    payload         STRING COMMENT 'full character JSON, JSON-encoded',
    updated_at      STRING
) COMMENT 'Mirror of output/<series_id>/blueprint/characters/*.json';

-- One row per episode outline (mirrors episodes/epNN/outline.json).
CREATE TABLE IF NOT EXISTS episodes (
    series_id       STRING NOT NULL,
    episode_number  INT NOT NULL,
    outline         STRING COMMENT 'outline.json, JSON-encoded',
    updated_at      STRING
) COMMENT 'Mirror of output/<series_id>/episodes/epNN/outline.json';

-- One row per episode script (mirrors episodes/epNN/script.json).
CREATE TABLE IF NOT EXISTS scripts (
    series_id       STRING NOT NULL,
    episode_number  INT NOT NULL,
    lines           STRING COMMENT 'script.json ScriptLine list, JSON-encoded',
    line_count      INT,
    updated_at      STRING
) COMMENT 'Mirror of output/<series_id>/episodes/epNN/script.json';

-- One row per episode sound plan (mirrors episodes/epNN/sound_plan.json).
CREATE TABLE IF NOT EXISTS sound_plans (
    series_id       STRING NOT NULL,
    episode_number  INT NOT NULL,
    plan            STRING COMMENT 'sound_plan.json, JSON-encoded',
    updated_at      STRING
) COMMENT 'Mirror of output/<series_id>/episodes/epNN/sound_plan.json';

-- One row per episode audio manifest (mirrors episodes/epNN/audio.json),
-- plus the Unity Catalog Volume path once the final mix has been uploaded.
CREATE TABLE IF NOT EXISTS audio_manifest (
    series_id       STRING NOT NULL,
    episode_number  INT NOT NULL,
    voices_path     STRING COMMENT 'local path to epNN_voices.wav',
    final_path      STRING COMMENT 'local path to epNN_final.wav',
    volume_path     STRING COMMENT '/Volumes/<catalog>/<schema>/<volume>/... once uploaded',
    total_ms        BIGINT,
    manifest        STRING COMMENT 'full audio.json, JSON-encoded',
    updated_at      STRING
) COMMENT 'Mirror of output/<series_id>/episodes/epNN/audio.json + volume upload path';
