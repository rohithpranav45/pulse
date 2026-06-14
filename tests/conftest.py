"""Pytest bootstrap — put backend/ (and the repo root) on sys.path so tests can
import the engine modules the same way the app does: `research.*`, `paper_trading`."""
import os
import sys

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_BACKEND = os.path.join(_ROOT, "backend")
for _p in (_BACKEND, _ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)
