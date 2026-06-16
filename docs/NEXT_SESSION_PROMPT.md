# Next-session prompt — paste this into a fresh Claude session

---

Read `CLAUDE.md` end-to-end, then `docs/DASHBOARD_REBUILD.md` end-to-end. This
is PULSE; we're starting **Phase 4.A** of the dashboard rebuild.

## Context (do NOT re-derive)
- Project state, gotchas, env keys, run commands: all in `CLAUDE.md`.
- The full 7-phase rebuild plan with acceptance criteria per phase: `docs/DASHBOARD_REBUILD.md`.
- I am NOT touching strategy or architecture this phase (deferred pending mentor verdict).
- The HF deploy is frozen as a presentation backup; root cause of its broken regime endpoints
  is already documented (missing `joblib` — fix already in local `requirements.txt`, not pushed).
  Do NOT push to GitHub or trigger an HF rebuild this session.

## This session: Phase 4.A only — build the new DESK landing view

Scope (verbatim from `docs/DASHBOARD_REBUILD.md` §2):

1. New file `frontend/src/views/DeskView.tsx`.
2. Add as the **first** sidebar entry (key `desk`, hotkey `1`, icon: pick something
   from lucide-react that fits "trading desk" — `LayoutGrid` or `Briefcase`).
3. Shift the other tabs' hotkeys down (Charts=2, Fundamentals=3, etc. — temporary,
   they get cut in later phases).
4. DESK contains, top to bottom:
   - **Hero card:** today's regime pick from `/api/regime/recommendation` (live,
     gated). Single sentence headline: "Trade X, LONG/SHORT, z=Y, conf=Z%."
     Below it: a one-row mini-table of all 6 spreads ranked.
   - **Open positions strip:** compact 1-row-per-trade view from `/api/paper/positions`
     with live MTM. Reuse the existing position rendering from `PaperView.tsx` —
     pull out the row component into a shared `PositionRow.tsx` if it isn't
     already. Show at most 5 rows; "+N more" link to PAPER tab below that.
   - **Risk panel (NEW)** — create `frontend/src/components/panels/RiskPanel.tsx`:
     - Sum-of-stops-if-all-hit (gross drawdown if every open position hits its SL)
     - Gross exposure by leg (Brent c1, c2, c3, c6; same for WTI)
     - 30d rolling correlation between open positions (use the existing
       `/api/correlations` endpoint; filter to instruments we actually hold)
   - **Morning brief card:** Groq brief from `/api/intelligence/brief` (it lives
     in the old Intelligence tab — relocate, don't duplicate the fetch logic).
   - **Price decomposition strip:** existing `PriceDecomposition` panel,
     unchanged, just rendered inside DESK.

5. **Do NOT delete any old tabs yet.** This phase is purely additive. Old tabs
   keep working until 4.B and later.

## Acceptance criteria (must all be true before ending session)

- [ ] DESK is the first sidebar entry; clicking it shows the new layout.
- [ ] All 5 panels above render with real data (not skeletons) within 2s.
- [ ] Risk panel renders an empty-state card when zero positions are open (text:
      "No open positions — risk = 0").
- [ ] Frontend rebuilt (`cd frontend && npm run build`); change visible at
      http://127.0.0.1:5000 after a hard refresh.
- [ ] All 9 old tabs still navigable and still work (no regressions).
- [ ] `python -m pytest tests/` still 9 green.
- [ ] No new TypeScript errors (`npm run build` finishes clean).

## Out of scope this session
- Removing any old tab.
- Strategy/model changes.
- Architecture changes.
- HF deploy.
- The Signal Log dedup fix (Phase 4.G, separate session).
- Calibration plot (Phase 4.H, bonus).

## How to verify visually
Use `mcp__Claude_Preview__preview_*` to start a preview against
http://127.0.0.1:5000 and take a `preview_screenshot` of the new DESK landing.
Attach the screenshot output in your summary. If the local Flask isn't running,
start it with `.venv\Scripts\python.exe start.py` first.

## End-of-session deliverable
1. Brief diff summary (files added, files modified, LOC delta).
2. Screenshot of the new DESK tab.
3. The pytest result (`9 passed`).
4. A one-line recommendation: continue here for Phase 4.B (small) or new chat
   to save usage.

Start now. Don't ask clarifying questions — the plan is explicit.
