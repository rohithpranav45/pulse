"""
WSGI entry point for the production (gunicorn) deployment — Phase 3.D.
=====================================================================

Why this module exists
----------------------
`python start.py` / `python backend/app.py` runs app.py as ``__main__``, and the
APScheduler background jobs (data refresh + 60 s paper MTM + the daily A/B tick)
plus the cache warm-up are started inside app.py's ``if __name__ == "__main__"``
block. Under gunicorn the module is *imported*, not run as ``__main__``, so that
block never fires — the API would serve requests but nothing would refresh and
the A/B paper book would never accumulate. This module is what gunicorn loads;
it imports the Flask ``app`` and explicitly starts the scheduler + warm-up
exactly once, in the worker process that serves requests.

CRITICAL — run gunicorn with --workers 1
----------------------------------------
The APScheduler must live in exactly ONE process. With more than one worker,
every worker would import this module and start its own scheduler, firing the
daily A/B tick, the 60 s MTM sweep, and every data-refresh job once *per
worker* — N× the intended cadence and N processes writing the SQLite book. This
is an I/O-bound, single-tenant dashboard, so one worker with several threads
(--threads 8) is the correct model: threads give request concurrency, the
single process keeps the scheduler singular and serialises writes cleanly under
WAL. The Dockerfile CMD hard-codes ``--workers 1``; do not raise it without
moving the scheduler to a dedicated sidecar process.

Note on --preload: this module starts the scheduler at *import* time, so it must
NOT be combined with gunicorn ``--preload``. Preload imports the app in the
master before forking; APScheduler's background threads do not survive fork(),
so the scheduler would appear started but never run in the worker. The Dockerfile
deliberately omits --preload.
"""

from __future__ import annotations

import atexit
import logging
import threading

# Importing app builds the Flask app, loads .env, inits Sentry/Better Stack, and
# constructs (but does not start) the BackgroundScheduler + defines warm_cache.
from app import app, _scheduler, warm_cache  # noqa: F401  (app is the WSGI callable)

log = logging.getLogger("pulse.wsgi")

_boot_lock = threading.Lock()
_booted = False


def _boot_once() -> None:
    """Start the cache warm-up + scheduler exactly once for this process."""
    global _booted
    with _boot_lock:
        if _booted:
            return
        _booted = True

        # Warm the cache in the background so the first requests don't block on a
        # cold data-lake load (mirrors app.py's __main__ behaviour).
        threading.Thread(target=warm_cache, name="cache-warmup", daemon=True).start()

        # Guard against an accidental double-start within a single process. This
        # does NOT protect against multiple worker processes — see the module
        # docstring; --workers 1 is the real guarantee.
        if not _scheduler.running:
            _scheduler.start()
            log.info(
                "APScheduler started under gunicorn — data refresh + 60s paper MTM "
                "+ daily A/B tick active (tuned-rule paper book will accumulate)"
            )
            atexit.register(_shutdown)


def _shutdown() -> None:
    """Stop the scheduler cleanly on worker exit (best-effort)."""
    try:
        if _scheduler.running:
            _scheduler.shutdown(wait=False)
            log.info("APScheduler stopped on worker shutdown")
    except Exception as exc:  # pragma: no cover — shutdown is best-effort
        log.warning("scheduler shutdown failed: %s", exc)


_boot_once()
