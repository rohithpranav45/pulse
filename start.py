"""
PULSE — Energy Trading Dashboard
=================================
One-command launcher. Run from the pulse/ project root:

    python start.py

What it does:
  1. Checks Python version (3.11+ required)
  2. Verifies required packages are installed
  3. Starts the Flask API (backend/app.py) on port 5000
  4. Polls until the API is healthy (up to 20 s)
  5. Opens frontend/index.html in the default browserg
  6. Streams API logs to the console

Press Ctrl+C to shut down.
"""

import subprocess
import sys
import os
import time
import webbrowser
import urllib.request
from pathlib import Path

# ── Fix Windows console encoding (cp1252 can't print box-drawing chars) ───────
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

ROOT       = Path(__file__).parent
API_URL    = "http://127.0.0.1:5000"
HEALTH_URL = f"{API_URL}/api/health"
DIST_DIR   = ROOT / "backend" / "static"
DIST_INDEX = DIST_DIR / "index.html"
FRONTEND   = ROOT / "frontend"


# ── Colour helpers (no third-party deps) ──────────────────────────────────────
def _c(code, text): return f"\033[{code}m{text}\033[0m"
OK   = lambda t: _c("32", t)
WARN = lambda t: _c("33", t)
ERR  = lambda t: _c("31", t)
DIM  = lambda t: _c("2",  t)
BOLD = lambda t: _c("1",  t)


# ── Pre-flight checks ─────────────────────────────────────────────────────────
def check_python():
    if sys.version_info < (3, 11):
        print(ERR(f"  Python 3.11+ required — you have {sys.version.split()[0]}"))
        sys.exit(1)
    print(OK(f"  Python {sys.version.split()[0]}"))


def check_packages():
    required = ["flask", "flask_cors", "yfinance", "numpy", "pandas",
                "requests", "dotenv"]
    missing = []
    for pkg in required:
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg.replace("_", "-"))
    if missing:
        print(WARN(f"  Missing: {', '.join(missing)}"))
        print(DIM("  Fix: pip install -r requirements.txt"))
        sys.exit(1)
    print(OK("  All required packages present"))


def wait_for_api(timeout: int = 20) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(HEALTH_URL, timeout=2) as r:
                if r.status == 200:
                    return True
        except Exception:
            pass
        time.sleep(1)
    return False


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    print()
    print(BOLD("  ╔══════════════════════════════════════╗"))
    print(BOLD("  ║   PULSE — Energy Trading Dashboard   ║"))
    print(BOLD("  ╚══════════════════════════════════════╝"))
    print()

    print(DIM("  [1/4] Checking environment..."))
    check_python()
    check_packages()

    print()
    print(DIM("  [2/4] Starting Flask API on port 5000..."))
    api_proc = subprocess.Popen(
        [sys.executable, str(ROOT / "backend" / "app.py")],
        cwd=str(ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )

    print(DIM("  [3/4] Waiting for API health check..."))
    ready = wait_for_api(timeout=20)
    if ready:
        print(OK("  API live at http://127.0.0.1:5000"))
    else:
        print(WARN("  API didn't respond in 20 s — opening dashboard anyway"))

    print()
    print(DIM("  [4/4] Opening dashboard in browser..."))
    if not DIST_INDEX.exists():
        print(WARN("  React build not found — run: cd frontend && npm install && npm run build"))
        print(WARN(f"  Then refresh {API_URL}"))
    webbrowser.open(API_URL)
    print(OK(f"  Dashboard: {API_URL}"))

    print()
    print(BOLD("  ─────────────────────────────────────────────"))
    print(f"  {OK('API')}       {API_URL}/api/health")
    print(f"  {OK('Dashboard')} {API_URL}")
    print(DIM(f"  Dev mode: cd {FRONTEND.name} && npm run dev   (Vite hot-reload)"))
    print(BOLD("  ─────────────────────────────────────────────"))
    print(DIM("  Warm-up runs in background (~60 s for full data load)"))
    print(DIM("  Press Ctrl+C to stop.\n"))

    # Stream API logs to console
    try:
        for line in api_proc.stdout:
            print(DIM("  [api] ") + line, end="")
    except KeyboardInterrupt:
        pass
    finally:
        print(f"\n{DIM('  Shutting down...')}")
        api_proc.terminate()
        try:
            api_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            api_proc.kill()
        print(OK("  Stopped.\n"))


if __name__ == "__main__":
    main()
