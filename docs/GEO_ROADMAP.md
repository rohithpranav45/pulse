# GEO news-impact engine — roadmap

Branch `phase4-live-feature-overlay` (not merged to main). The geospatial oil-news impact engine:
**location-news → physical asset → price nodes/spreads → directional impact, regime-gated,
prior-then-learn, with RAG analogs and a dashboard.** Full per-sprint detail lives in CLAUDE.md §1
(the "Geo news-impact engine" entries). This doc is the forward plan.

## ✅ Done (Sprints 1–7, all on free Groq — no paid Claude)

| # | Sprint | Deliverable |
|---|--------|-------------|
| 1 | Registry + nodes | 41 assets (chokepoints/refineries/pipelines/fields/producers + generics); 7 price nodes |
| 2 | LLM extraction + impact map | headline → {assets, event, severity} → signed node vector (Claude/Groq/keyword) |
| 3 | Per-node event study | forward node move + binomial hit-rate + beta, prior-then-learn (machinery; thin corpus) |
| 4 | GDELT corpus + ACLED | desk corpus made it gradeable (30 events); `conflict.py` ACLED regime feed |
| 4b | **LLM re-grade** | `gpt-oss-120b` fixed closure-vs-reopen polarity → 68 events, measured crude-flat/structure edges |
| 5 | **RAG analogs** | `analogs.py` — interpretable nearest-neighbour over the graded event panel; `/api/news/geo/analogs` |
| 6 | **Products OHLCV feed** | `products_feed.py` (RBOB/HO/LGO/LCO/CL); `rbob_crack` real; node tape extended to 2026-06-26 → **June war gradeable (112 events)** |
| 7 | **rbob_crack graded + dashboard** | registry gasoline-crack bias; `/api/news/geo` + `GeoImpactPanel` + `GeoAnalogPanel` on the News tab |
| 8 | **Live scheduler wiring + geo alerts** | `geo/live.py` + `_geo_news_ingest` job; `/api/news/geo/live`; `GeoLiveAlertsPanel` on the News tab |
| 9 | **Geo-map visualization** | SVG world map (`worldOutline.ts`, no dep); `live.map_assets` + `/api/news/geo/map`; `GeoMapPanel` — 37 assets sized/coloured by live activity, click → bias + analog pre-fill |
| 10 | **LLM-narrated RAG desk note** | `analogs.narrate` — free-Groq (or template) note grounded in the retrieved analogs + graded edges; `/api/news/geo/analogs?narrate=1`; "Desk note" card in `GeoAnalogPanel` |

**Measured edges (2026 Hormuz war, single episode — read direction not exact p):** chokepoint disruption →
WTI−Brent tightens (0.59 @5d, p=0.008) + distillate crack firms (`ho_crack` 0.57 @5d) + crude **flat reverses**
(0.40 @5d); refinery outage → gasoline crack up 86–92% @1d (n=14, prior — too thin to certify). 280 tests pass.

## ⬜ Forward plan (one sprint per session, in this order)

### ✅ Sprint 8 — Live scheduler wiring + geo alerts (done 2026-06-30)
The engine is now a *live* analysis engine, not a corpus-only study.
- New **`backend/research/news_impact/geo/live.py`** — `ingest_wire(articles, *, extract_fn=, regime=, …)` pipes
  the wire through the `is_geo_candidate` prefilter (free Groq budget spent only on geo news) → `extract_cached`
  (LLM-cached, fallback-not-cached guard untouched) → `impact_map.headline_impact` → `annotate_impact` (EDGE/prior
  tags merged across +1d/+5d, preferring the 5d geo edge) → an accumulating JSON store (`geo_live_events.json`,
  deduped by title hash, capped 200). `recent_events(limit)` ranks by |conviction| × tradeable.
- **Scheduler job `_geo_news_ingest`** (`app.py`, every `TTL_NEWS`, opt-out `PULSE_GEO_DISABLED=1`; also runs on the
  manual `/api/news/refresh`). Endpoint **`GET /api/news/geo/live`**; `api.newsGeoLive`.
- **Dashboard:** **`GeoLiveAlertsPanel`** at the top of the News tab — newest geo-scored headlines with the strongest
  node arrows + an `edge`/`prior` tag (gold ring on EDGE nodes), reusing the freshness/error chips.
- **Verified:** Hormuz closure → `wti_brent`/`ho_crack` EDGE @5d; Aramco strike → field/attack; dedup re-run adds 0;
  non-geo headlines never reach the extractor. +7 hermetic tests (monkeypatched wire+extractor, no network/Groq/Data)
  → **270 pass**; `tsc`/build clean.

### ✅ Sprint 9 — Geo-map visualization (done 2026-06-30)
The registry's lat/lon for every asset is now a map.
- **No heavy dep** — the bundle had no map lib, so the map is a hand-rolled SVG equirectangular world
  (`frontend/src/lib/worldOutline.ts`: coarse continent rings + `projectLonLat`/`continentPaths`). +9 kB JS, no dep.
- New **`live.map_assets(store_path=)` + `GET /api/news/geo/map`** — joins every **placeable** registry asset (drops
  the 4 GLOBAL generics at 0,0 → 37 plotted) with its `disruption_bias` prior + live activity (`_activity_index`:
  event count, peak conviction, any-EDGE, newest ts, ≤4 headlines) from the Sprint-8 store. `api.newsGeoMap`.
- **`GeoMapPanel`** at the top of the News tab: dots **sized by live event count**, **coloured** muted-by-type →
  amber (active) → **gold (EDGE)**; clicking an asset shows its bias node-arrows + recent alerts **and pre-fills the
  `GeoAnalogPanel` lookup** (lifted `analogPrefill` state in `NewsView`; `GeoAnalogPanel` gained a `prefill` prop).
- **Verified:** `/api/news/geo/map` → 200, 37 assets, Hormuz at 26.57/56.25 with `brent_flat:+2`. +4 hermetic tests
  (`tests/test_geo_map.py`) → **274 pass**; `tsc`/build clean.

### ✅ Sprint 10 — LLM-narrated RAG desk note (done 2026-06-30)  *(the generative "RAG" piece)*
The analogs were structured/numeric (retrieval, no generation) — this adds the optional narration.
- **`analogs.narrate(result, *, horizon=, provider=, llm_fn=)`** builds an **exact-number evidence block** from the
  analog forecast (`_evidence`: per-node mean-Δ / `analog_agree` / n, EDGE-first; EDGE flags via
  `event_study_geo.annotate_impact` both horizons), then either has **free Groq** (`gpt-oss-120b`) phrase it under a
  strict no-invent prompt, or falls back to a **deterministic template** built from the same numbers. **No key + no
  `llm_fn` ⇒ template** — degrades gracefully, never fabricates a figure. The note names the read to **trust**
  (EDGE/high agreement) + the one to **fade** (agreement <50% = reversal) + the single-episode caveat.
- Surfaced at **`/api/news/geo/analogs?narrate=1`** (a `narration` block) + a gold **"Desk note"** card in
  `GeoAnalogPanel`; `api.newsGeoAnalogs(title,k,horizon,narrate)`.
- **Verified (real index):** "Iran closes Hormuz" → *"…moved WTI–Brent +1.01 over 5d, agreeing 60% (n=5) (certified
  EDGE) — trust this read. ULSD crack reversed (0% agreement, n=5) — fade it. Single-episode evidence …"*. +6 hermetic
  tests (`tests/test_geo_analogs.py`, injected `llm_fn`) → **280 pass**; `tsc`/build clean.

### Sprint 11 — Analytical depth (data-bound)
- Condition the event study on the **ACLED conflict regime** (`conflict.conflict_regime`) as an extra slice axis
  in `node_hit_table` — does the geo edge strengthen in HIGH-conflict months?
- **Certify `rbob_crack`** + add an **RBOB M1-M2** gasoline-curve node — needs a thicker refinery sample
  (broaden the GDELT corpus beyond the single 2026 episode, or a price-covered backfill) for cross-episode
  validation. This is the honest "more data, not more code" item.

## Key facts the next session needs
- **LLM:** free Groq, `extract.GROQ_MODEL = "openai/gpt-oss-120b"` (70B's 100k-TPD cap recurs; 8B too weak —
  nulls reopen events). `GROQ_API_KEY` in `.env`. **No paid Claude** (a Claude *Max subscription* is chat/Claude
  Code, not an API key, and can't clear the data blockers anyway).
- **Feeds:** GDELT corpus + ACLED at `backend/data/research/news_impact/geo/`; OHLCV products feed at
  `I:\Public\Summer Interns Energy\OHLCV` (override `PULSE_OHLCV_DIR`), gotcha 17.
- **Caches:** `geo_extractions.json` (LLM extractions — only LLM results cached, never fallback),
  `geo_event_study.json` (graded edge map). Re-grade: `python backend/research/news_impact/geo/event_study_geo.py`.
- **Standing caveats:** single episode (2026 Hormuz war), clustered/overlapping events ⇒ optimistic p-values
  (read direction + cross-node coherence); node tape ends 2026-06-26; daily product settles are last-hourly-bar
  ESTIMATEs. The real result-unlock is a broader price-covered corpus, not more LLM.
- **Run:** `python start.py` → http://127.0.0.1:5000. Tests: `python -m pytest tests/` (263 green). Frontend:
  portable Node at `~/nodejs` (gotcha 4b) — `$env:Path="$env:USERPROFILE\nodejs;"+$env:Path; npm run build`.
- **Tests:** `python -m pytest tests/` → 280 green.
