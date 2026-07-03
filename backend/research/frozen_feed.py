"""
Frozen desk-feed fallback.
==========================

The live analysis surfaces (15-min bars, the 1-min inventory-reaction feed, and
the hourly OHLCV products feed) are recorded to the office share
`I:\\Public\\Summer Interns Energy\\...` and are **only visible from a desk that
mounts that share**. The public deployment (Hugging Face Space) never sees it.

So the repo ships a *frozen snapshot* of each feed under
`backend/data/frozen_feed/` (committed), and every feed-directory resolver routes
through :func:`resolve_dir`:

    explicit env override  →  live desk share (if it exists)  →  frozen snapshot

On the desk the live share exists, so nothing changes — the desk always reads the
live recorder. On the deployment the share is absent, so the resolver falls back
to the frozen snapshot and every desk-backed panel keeps showing data. Point the
matching env var at a real directory to override either.

The snapshot is a point-in-time freeze (see `FROZEN_AS_OF`); the deployed app is
honest that these panels are a frozen desk session, not a live tick.
"""
from __future__ import annotations

import os
from pathlib import Path

# The last real desk session captured into the frozen snapshot. Surfaced so the
# UI / API can label frozen-feed panels honestly.
FROZEN_AS_OF = "2026-07-01"

# backend/research/frozen_feed.py -> backend/data/frozen_feed
FROZEN_ROOT = Path(__file__).resolve().parent.parent / "data" / "frozen_feed"


def _has_files(d: Path, patterns: tuple[str, ...]) -> bool:
    """True if the directory exists and holds at least one matching feed file."""
    if not d.exists():
        return False
    if not patterns:
        return d.exists()
    return any(next(d.glob(p), None) is not None for p in patterns)


def resolve_dir(
    env_var: str,
    desk_default: str,
    frozen_subdir: str,
    *,
    require: tuple[str, ...] = (),
) -> Path:
    """
    Resolve a feed directory with graceful desk→frozen fallback.

    Priority:
      1. ``os.environ[env_var]`` if set (explicit override always wins).
      2. ``desk_default`` (the office share) if it exists AND — when ``require``
         glob patterns are given — actually contains a matching feed file.
      3. the committed frozen snapshot at ``FROZEN_ROOT / frozen_subdir``.

    ``require`` guards against a share that is mounted but empty/stale: if the
    live dir has no matching files we still fall through to the frozen snapshot.
    """
    override = os.environ.get(env_var)
    if override:
        return Path(override)
    desk = Path(desk_default)
    if _has_files(desk, require):
        return desk
    return FROZEN_ROOT / frozen_subdir


def is_frozen(path: Path | str) -> bool:
    """True when ``path`` resolves inside the committed frozen snapshot."""
    try:
        Path(path).resolve().relative_to(FROZEN_ROOT.resolve())
        return True
    except (ValueError, OSError):
        return False
