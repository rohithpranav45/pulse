"""
Observability — Sentry + Better Stack
=====================================
Sprint 0b. Safety net for everything Phase 2 will write.

Two thin layers, both no-ops if env vars are absent so the dashboard runs
unchanged on a machine without tokens:

  * **Sentry** captures unhandled exceptions in every Flask route, every
    APScheduler job (via the logging integration), and every call we wrap
    in `capture_exception()`.
  * **Better Stack** aggregates structured logs. A `LogtailHandler` is
    attached to the root logger so every `log.info(...)` / `log.warning(...)`
    streams up automatically.

Public API
----------
    init_sentry()                      → ()   call once at boot
    init_better_stack_logging()        → ()   call once at boot
    capture_exception(exc, **tags)     → ()   safe to call without init
    observability_status()             → dict for health-detail probe

This module never raises on init failure — observability outages must not
take the app down.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Optional

log = logging.getLogger("pulse.observability")

# Module-level flags so other code (and the health probe) can see what
# actually came up.
_state: dict[str, Any] = {
    "sentry_enabled":       False,
    "sentry_dsn_set":       False,
    "sentry_environment":   None,
    "better_stack_enabled": False,
    "better_stack_token_set": False,
    "init_errors":          [],
}


def state() -> dict:
    """Snapshot of what the observability stack thinks it has wired up."""
    return dict(_state)


# ─────────────────────────────────────────────────────────────────────────────
# Sentry
# ─────────────────────────────────────────────────────────────────────────────
def init_sentry() -> None:
    """
    Initialise Sentry. Idempotent — safe to call more than once. No-op when
    SENTRY_DSN is missing or sentry-sdk is not installed.
    """
    dsn = os.environ.get("SENTRY_DSN", "").strip()
    _state["sentry_dsn_set"] = bool(dsn)
    if not dsn:
        log.info("Sentry: SENTRY_DSN not set — error capture disabled")
        return
    try:
        import sentry_sdk
        from sentry_sdk.integrations.flask import FlaskIntegration
        from sentry_sdk.integrations.logging import LoggingIntegration
    except ImportError as exc:
        _state["init_errors"].append(f"sentry import: {exc}")
        log.warning("Sentry: sentry-sdk not installed (%s)", exc)
        return

    environment = os.environ.get("SENTRY_ENV", "local")
    try:
        rate = float(os.environ.get("SENTRY_TRACES_SAMPLE_RATE", "0.05"))
    except ValueError:
        rate = 0.05

    try:
        sentry_sdk.init(
            dsn=dsn,
            environment=environment,
            release=os.environ.get("PULSE_RELEASE") or "pulse@dev",
            traces_sample_rate=rate,
            send_default_pii=False,
            integrations=[
                FlaskIntegration(),
                # Forward log.error / log.warning above WARNING as breadcrumbs;
                # only ERROR-and-above promote to events.
                LoggingIntegration(level=logging.INFO, event_level=logging.ERROR),
            ],
        )
        # Add a tag we can search on
        sentry_sdk.set_tag("component", "pulse-backend")
    except Exception as exc:
        _state["init_errors"].append(f"sentry init: {exc}")
        log.warning("Sentry init failed: %s", exc)
        return

    _state["sentry_enabled"]      = True
    _state["sentry_environment"]  = environment
    log.info("Sentry: enabled (env=%s, traces=%.2f)", environment, rate)


def capture_exception(exc: BaseException, **tags: Any) -> None:
    """
    Send an exception to Sentry with optional tags. Safe to call even when
    Sentry isn't initialised — falls back to a local warning log.

    Use this inside `safe_fetch` and other places that intentionally swallow
    exceptions, so silent failures still leave a paper trail.
    """
    if _state["sentry_enabled"]:
        try:
            import sentry_sdk
            with sentry_sdk.push_scope() as scope:
                for k, v in tags.items():
                    scope.set_tag(k, str(v)[:200])
                sentry_sdk.capture_exception(exc)
            return
        except Exception:
            # never let observability take the app down
            pass
    log.warning("captured (Sentry off): %s — tags=%s", exc, tags)


# ─────────────────────────────────────────────────────────────────────────────
# Better Stack (logtail)
# ─────────────────────────────────────────────────────────────────────────────
def init_better_stack_logging(root_logger: Optional[logging.Logger] = None) -> None:
    """
    Attach a Logtail (Better Stack) handler to the root logger. No-op when
    BETTER_STACK_TOKEN is missing or `logtail` is not installed.

    The handler ships asynchronously in a background thread, so this call
    won't block on network errors.
    """
    token = os.environ.get("BETTER_STACK_TOKEN", "").strip()
    _state["better_stack_token_set"] = bool(token)
    if not token:
        log.info("Better Stack: BETTER_STACK_TOKEN not set — log shipping disabled")
        return
    try:
        from logtail import LogtailHandler  # type: ignore
    except ImportError as exc:
        _state["init_errors"].append(f"logtail import: {exc}")
        log.warning("Better Stack: logtail-python not installed (%s)", exc)
        return

    host = os.environ.get("BETTER_STACK_HOST", "in.logs.betterstack.com")
    try:
        handler = LogtailHandler(source_token=token, host=f"https://{host}")
        handler.setLevel(logging.INFO)
        handler.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s | %(message)s"
        ))
        target = root_logger or logging.getLogger()
        target.addHandler(handler)
    except Exception as exc:
        _state["init_errors"].append(f"logtail init: {exc}")
        log.warning("Better Stack init failed: %s", exc)
        return

    _state["better_stack_enabled"] = True
    log.info("Better Stack: enabled (host=%s)", host)


# ─────────────────────────────────────────────────────────────────────────────
# Health probe helpers — used by /api/health-detail
# ─────────────────────────────────────────────────────────────────────────────
def observability_status() -> dict:
    """
    Compact dict the health probe uses to mark Sentry / Better Stack as
    up / stale / down without needing a network round-trip.
    """
    return {
        "sentry": {
            "enabled":     _state["sentry_enabled"],
            "dsn_set":     _state["sentry_dsn_set"],
            "environment": _state["sentry_environment"],
        },
        "better_stack": {
            "enabled":   _state["better_stack_enabled"],
            "token_set": _state["better_stack_token_set"],
        },
        "init_errors": _state["init_errors"],
    }
