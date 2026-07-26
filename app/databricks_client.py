"""Low-level Databricks connection helpers — never on the correctness hot path.

Everything here is feature-flagged via `DATABRICKS_ENABLED` (see app/config.py).
When the flag is off (the default), `is_enabled()` short-circuits before any
import of the Databricks SDK/connector, so disabled installs pay zero cost.

Callers (app/databricks_store.py) are responsible for catching exceptions —
this module raises on failure so the caller's try/except can log it. Nothing
in this module should ever be awaited by a request thread; use `submit()` to
run work on a background executor instead.
"""
from __future__ import annotations

import logging
import importlib.util
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable

from . import config

_LOG = logging.getLogger(__name__)

_CERTIFI_PATCHED = False
_CERTIFI_LOCK = threading.Lock()
_WARNED_MISCONFIGURED = False
_WARNED_MISSING_SDK = False

# Small, bounded pool for fire-and-forget dual-write calls. Sized independently
# of JOB_MAX_CONCURRENCY so a slow/cold SQL warehouse can never block episode
# generation, which stays entirely local-disk-backed.
_EXECUTOR = ThreadPoolExecutor(max_workers=4, thread_name_prefix="pocketfm-dbx")


def _patch_certifi() -> None:
    """Point the SSL stack at certifi's CA bundle.

    Some macOS Python installs ship a broken/incomplete default trust store,
    which fails every HTTPS call (including the OAuth M2M handshake) with
    CERTIFICATE_VERIFY_FAILED. This is a one-time, idempotent, best-effort fix.
    """
    global _CERTIFI_PATCHED
    if _CERTIFI_PATCHED:
        return
    with _CERTIFI_LOCK:
        if _CERTIFI_PATCHED:
            return
        try:
            import certifi
            os.environ.setdefault("SSL_CERT_FILE", certifi.where())
            os.environ.setdefault("REQUESTS_CA_BUNDLE", certifi.where())
        except Exception:
            pass
        _CERTIFI_PATCHED = True


@lru_cache(maxsize=1)
def _connector_installed() -> bool:
    """Whether the optional Databricks packages are importable.

    Uses find_spec so a disabled/uninstalled setup never pays the import cost,
    and caches the answer since it can't change while the process is running.
    """
    try:
        return all(importlib.util.find_spec(name) is not None
                   for name in ("databricks.sql", "databricks.sdk"))
    except (ImportError, ValueError):
        return False


def is_enabled() -> bool:
    """True only when the feature flag is on AND required credentials are set.

    Logs a single warning (not per-call) if the flag is on but misconfigured,
    so a typo'd .env doesn't spam logs on every series save.
    """
    global _WARNED_MISCONFIGURED
    if not config.DATABRICKS_ENABLED:
        return False

    required = {
        "DATABRICKS_SERVER_HOSTNAME": config.DATABRICKS_SERVER_HOSTNAME,
        "DATABRICKS_HTTP_PATH": config.DATABRICKS_HTTP_PATH,
        "DATABRICKS_CLIENT_ID": config.DATABRICKS_CLIENT_ID,
        "DATABRICKS_CLIENT_SECRET": config.DATABRICKS_CLIENT_SECRET,
    }
    missing = [k for k, v in required.items() if not v]
    if missing:
        if not _WARNED_MISCONFIGURED:
            _LOG.warning(
                "DATABRICKS_ENABLED=true but missing env vars: %s — "
                "Databricks dual-write is disabled until these are set.",
                ", ".join(missing),
            )
            _WARNED_MISCONFIGURED = True
        return False

    # The connector is an optional dependency. Without it every dual-write
    # would raise ModuleNotFoundError on the executor and log a full traceback
    # per save, so treat "not installed" the same as "not configured".
    if not _connector_installed():
        if not _WARNED_MISSING_SDK:
            _LOG.warning(
                "DATABRICKS_ENABLED=true but the databricks connector is not "
                "installed — Databricks dual-write is disabled. Install it with: "
                "pip install databricks-sql-connector databricks-sdk"
            )
            globals()["_WARNED_MISSING_SDK"] = True
        return False

    _patch_certifi()
    return True


def submit(fn: Callable[[], None]) -> None:
    """Fire-and-forget one dual-write task. `fn` must catch its own exceptions;
    this only guards against the executor itself being unable to accept work."""
    try:
        _EXECUTOR.submit(fn)
    except Exception:
        _LOG.warning("Failed to submit Databricks sync task", exc_info=True)


def _oauth_m2m_credential_provider():
    """Build an OAuth M2M (service-principal) credential provider.

    IMPORTANT: databricks-sql-connector's `sql.connect()` does NOT accept
    plain `client_id`/`client_secret` kwargs for AWS/GCP M2M auth (only
    `oauth_client_id`, and `azure_client_secret` for Azure). Passing them
    directly silently falls through to the connector's interactive
    user-to-machine OAuth flow — it opens a local browser tab on
    localhost:8020 asking a human to log in, which is never what we want
    here. The documented, non-interactive way is this explicit
    `credentials_provider` built from the Databricks SDK. See:
    https://docs.databricks.com/aws/en/dev-tools/python-sql-connector (OAuth M2M).
    """
    from databricks.sdk.core import Config, oauth_service_principal

    cfg = Config(
        host=f"https://{config.DATABRICKS_SERVER_HOSTNAME}",
        client_id=config.DATABRICKS_CLIENT_ID,
        client_secret=config.DATABRICKS_CLIENT_SECRET,
    )
    return oauth_service_principal(cfg)


def get_sql_connection():
    """One short-lived SQL Warehouse connection, authenticated as the
    service principal via OAuth M2M. Raises on failure."""
    from databricks import sql
    return sql.connect(
        server_hostname=config.DATABRICKS_SERVER_HOSTNAME,
        http_path=config.DATABRICKS_HTTP_PATH,
        credentials_provider=_oauth_m2m_credential_provider,
    )


def execute(statement: str, params: dict[str, Any] | None = None) -> None:
    """Run one write statement (DDL/DML) against the SQL warehouse. Raises on
    failure — callers must wrap this in their own try/except."""
    with get_sql_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(statement, params or {})


def get_workspace_client():
    """Lazily build a WorkspaceClient authenticated as the configured
    service principal (OAuth M2M). `auth_type="oauth-m2m"` is set explicitly
    so the SDK never falls back to any other credential resolution (e.g. an
    ambient DATABRICKS_TOKEN or CLI profile) — this must always be the SP."""
    from databricks.sdk import WorkspaceClient
    return WorkspaceClient(
        host=config.DATABRICKS_HOST,
        client_id=config.DATABRICKS_CLIENT_ID,
        client_secret=config.DATABRICKS_CLIENT_SECRET,
        auth_type="oauth-m2m",
    )


def volume_root() -> str:
    return f"/Volumes/{config.DATABRICKS_CATALOG}/{config.DATABRICKS_SCHEMA}/{config.DATABRICKS_VOLUME}"


def upload_file(local_path: Path, volume_relative_path: str) -> str | None:
    """Upload one local file to the configured Unity Catalog Volume.

    Returns the full `/Volumes/...` path on success, or None (and logs a
    warning) on any failure — a failed upload never raises into the caller.
    """
    if not local_path.exists():
        return None
    volume_path = f"{volume_root()}/{volume_relative_path.lstrip('/')}"
    try:
        client = get_workspace_client()
        with open(local_path, "rb") as fh:
            client.files.upload(volume_path, fh, overwrite=True)
        return volume_path
    except Exception:
        _LOG.warning("Databricks volume upload failed for %s", local_path, exc_info=True)
        return None
