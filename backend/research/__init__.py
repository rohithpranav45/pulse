"""
Phase 2 research package.

Class-demo scope (2026-06-05):
  • 4 curve regimes (extreme/mild contango/backwardation) from M1-M12 spread
  • 3 instruments: Brent M1-M2, Brent M3-M6, Brent front fly (M1-2*M2+M3)
  • Per-regime regression suite (Ridge + Quantile p10/p50/p90)
  • Train ≤ 2026-03-31, test 2026-04-01 → 2026-05-31
  • Output: top-ranked opportunity per day, surfaced on Paper Trading tab

Designed to slot directly into Phase 2 Sprint 1 as the "vertical slice" —
no refactor required when we broaden to more instruments / regimes / axes.
"""
