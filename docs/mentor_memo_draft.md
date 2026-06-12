# Mentor memo draft — review before sending

---

Hi [mentor],

The PULSE dashboard is live for you to try at:

**https://jacket-army-appointed-racing.trycloudflare.com**

(Best in Chrome. URL is currently a quick-tunnel — fine for today; I'll send a stable URL once IT clears my admin request.)

Two things worth your time:

1. **Regime tab** — today's regime is `BACK/LOW/STRESSED` and the engine's top pick is **BUY Brent front fly (M1-2×M2+M3)** with XGBoost as winner (confidence 0.96, 19/19 features active). The competition grid below shows all 7 candidates' CV R² so you can see why XGBoost won that cell. Drill-down "Evidence" button shows the historical scatter + 3 nearest analogs for sanity.

2. **A/B harness panel** (below the regime card) — Phase 2.8.6 walk-forward surfaced that the un-gated pooled engine beats baseline NET by +0.05 Sharpe, while the current production gated blend ties baseline. Rather than flip the production default on a walk-forward result, I've launched parallel paper books for both arms with stop criteria (n≥30/arm AND Welch p<0.05, hard timeout 14 days). The verdict should land around 2026-06-25. The panel updates live; first tick fired 8 trades (4 per arm) on 2026-06-11.

Methodology PDF is at `backend/data/research/PULSE_methodology.pdf` if you want the full backtest receipts before the demo.

Happy to walk through it whenever works for you.

— [owner]

---

## Notes before sending

- Replace `[mentor]` and `[owner]` with actual names
- Update URL if cloudflared has restarted since this draft (`Get-Content cloudflared output | grep trycloudflare`)
- Consider mentioning that the desk needs to stay on for the URL to work, in case she tries late at night
- If admin access lands before sending, swap to the named-tunnel URL
