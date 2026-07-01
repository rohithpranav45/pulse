"""
Geospatial oil-news impact engine.
==================================

The location-aware extension of the news-impact model: map a headline to the
physical ASSET it concerns (chokepoint / refinery / pipeline / field), then to
the PRICE NODES that asset biases (crude flats, distillate cracks, the regrade,
WTI-Brent) and the sign of that bias, gated by curve regime.

Sprint 1 (this module set):
  * registry.py — the curated asset reference layer + alias resolution.
  * nodes.py    — the price-node series builder over the /Data tape
                  (crude + HO/Gasoil cracks + regrade), with provenance.

Later sprints layer geo-extraction (LLM), the asset→node impact map, the
empirical per-node event study, and the RAG analog engine on top of these two.
"""
