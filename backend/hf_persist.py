"""
Hugging Face Dataset persistence for the paper book — free-tier 24/7 deployment.
================================================================================

Why this exists
---------------
Free Hugging Face Spaces have **ephemeral** storage and sleep after ~48 h idle.
On every restart / rebuild / wake-from-sleep the container disk resets to the
image, which would wipe the SQLite paper book (``backend/db/pulse_cache.db``) —
and accumulating that A/B book 24/7 is the entire point of the deployment.

This module syncs the book to a **private HF Dataset** so it survives restarts:
  * ``pull_db()``  — at startup, BEFORE the app opens the DB (called from wsgi.py)
  * ``push_db()``  — periodically (a scheduler job) + at exit; WAL-checkpoints
                     first so the uploaded file is self-contained.

It is a **no-op** unless BOTH env vars are set, so local dev, ``docker compose``
and the Oracle VM are completely unaffected:
    HF_TOKEN         — a HF *write* token (set as a Space secret)
    HF_DATASET_REPO  — e.g. ``your-username/pulse-data`` (set as a Space variable)

Dataset layout (mirrors deploy/hf_space/upload_data.py):
    parquet/*.parquet   — the data lake, baked into the image at BUILD time
    db/pulse_cache.db   — the paper book, synced at RUNTIME by this module
"""
from __future__ import annotations

import logging
import os
import sqlite3

log = logging.getLogger("pulse.hf_persist")

# Same file cache.py + paper_trading.py share (backend/db/pulse_cache.db).
_DB_PATH = os.path.join(os.path.abspath(os.path.dirname(__file__)), "db", "pulse_cache.db")
_PATH_IN_REPO = "db/pulse_cache.db"

_REPO = os.environ.get("HF_DATASET_REPO", "").strip()
_TOKEN = os.environ.get("HF_TOKEN", "").strip()
_PUSH_EVERY_HOURS = float(os.environ.get("HF_PUSH_EVERY_HOURS", "2"))


def is_enabled() -> bool:
    """True only when both the dataset repo and a token are configured."""
    return bool(_REPO and _TOKEN)


def pull_db() -> None:
    """Restore the paper book from the dataset. Safe to call before the app boots.

    On the very first ever deploy the file won't exist yet — that's expected and
    we simply start with a fresh book (the first push_db seeds it)."""
    if not is_enabled():
        return
    try:
        import shutil

        from huggingface_hub import hf_hub_download

        os.makedirs(os.path.dirname(_DB_PATH), exist_ok=True)
        cached = hf_hub_download(
            repo_id=_REPO, repo_type="dataset", filename=_PATH_IN_REPO, token=_TOKEN
        )
        # hf_hub_download returns a (possibly symlinked) cache path — copy to the
        # real DB path so SQLite opens a normal, writable file.
        shutil.copyfile(cached, _DB_PATH)
        log.info("hf_persist: restored paper book from %s", _REPO)
    except Exception as exc:  # EntryNotFoundError on first boot, network blips, …
        log.warning(
            "hf_persist: no remote book to restore (%s) — starting fresh",
            exc.__class__.__name__,
        )


def _checkpoint() -> None:
    """Fold the WAL into the main .db so the uploaded file is complete."""
    try:
        c = sqlite3.connect(_DB_PATH)
        c.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        c.close()
    except Exception as exc:  # pragma: no cover — best effort
        log.warning("hf_persist: WAL checkpoint failed: %s", exc)


def push_db() -> None:
    """Upload the current paper book to the dataset (checkpoint first)."""
    if not is_enabled() or not os.path.exists(_DB_PATH):
        return
    try:
        _checkpoint()
        from huggingface_hub import HfApi

        HfApi(token=_TOKEN).upload_file(
            path_or_fileobj=_DB_PATH,
            path_in_repo=_PATH_IN_REPO,
            repo_id=_REPO,
            repo_type="dataset",
            commit_message="sync paper book",
        )
        log.info("hf_persist: pushed paper book to %s", _REPO)
    except Exception as exc:  # pragma: no cover — best effort, retried next tick
        log.warning("hf_persist: push failed: %s", exc)


def register(scheduler) -> None:
    """Wire a periodic push job + an atexit push. No-op unless enabled."""
    if not is_enabled():
        return
    import atexit

    scheduler.add_job(
        push_db,
        "interval",
        hours=_PUSH_EVERY_HOURS,
        id="hf_persist_push",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    atexit.register(push_db)
    log.info(
        "hf_persist: enabled — book syncs to %s every %sh + on exit",
        _REPO,
        _PUSH_EVERY_HOURS,
    )
