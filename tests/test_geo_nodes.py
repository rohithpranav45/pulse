"""Tests for the price-node builder (Sprint 1, Phase 5).

The math is tested hermetically via compute_nodes() with hand-built frames; a
final test exercises the real /Data path but skips cleanly when the lake is
absent (CI / fresh machine), matching the rest of the PULSE test suite.
"""

import numpy as np
import pandas as pd
import pytest

from research.news_impact.geo import nodes


def _frame(idx, **cols):
    return pd.DataFrame(cols, index=pd.to_datetime(idx))


def test_compute_nodes_crack_and_regrade_math():
    idx = ["2024-01-02", "2024-01-03"]
    brent = _frame(idx, c1=[80.0, 81.0], c2=[79.0, 80.0], c3=[78.5, 79.5],
                   c12=[74.0, 75.0])
    wti = _frame(idx, c1=[76.0, 77.0])
    ho = _frame(idx, c1=[2.50, 2.60])          # $/gal
    gasoil = _frame(idx, c1=[745.0, 760.0])    # $/tonne

    p = nodes.compute_nodes(brent, wti, ho, gasoil)

    # conversions
    ho_bbl = 2.50 * nodes.HO_GAL_PER_BBL                # 105.0
    go_bbl = 745.0 / nodes.GASOIL_BBL_PER_TONNE         # ~100.0
    assert p["ho_crack"].iloc[0] == pytest.approx(ho_bbl - 76.0, abs=1e-6)
    assert p["gasoil_crack"].iloc[0] == pytest.approx(go_bbl - 80.0, abs=1e-6)
    assert p["regrade"].iloc[0] == pytest.approx(go_bbl - ho_bbl, abs=1e-6)
    # crude nodes
    assert p["wti_brent"].iloc[0] == pytest.approx(76.0 - 80.0, abs=1e-6)
    assert p["brent_m1_m2"].iloc[0] == pytest.approx(80.0 - 79.0, abs=1e-6)
    assert p["brent_fly_123"].iloc[0] == pytest.approx(80.0 - 2 * 79.0 + 78.5, abs=1e-6)
    assert p["brent_structure"].iloc[0] == pytest.approx(80.0 - 74.0, abs=1e-6)


def test_compute_nodes_autoscales_cents_per_gallon():
    idx = ["2024-01-02"]
    brent = _frame(idx, c1=[80.0])
    wti = _frame(idx, c1=[76.0])
    ho_cents = _frame(idx, c1=[250.0])         # cents/gal → should scale /100
    p = nodes.compute_nodes(brent, wti, ho_cents, None)
    assert p["ho_crack"].iloc[0] == pytest.approx(2.50 * 42.0 - 76.0, abs=1e-6)


def test_compute_nodes_partial_inputs_omit_dependent_nodes():
    idx = ["2024-01-02"]
    brent = _frame(idx, c1=[80.0], c2=[79.0])
    p = nodes.compute_nodes(brent, None, None, None)   # crude only
    assert "brent_flat" in p.columns
    assert "wti_brent" not in p.columns
    assert "ho_crack" not in p.columns
    # nothing at all → empty frame, no crash
    assert nodes.compute_nodes(None, None, None, None).empty


def test_catalog_available_and_gaps_are_disjoint_and_documented():
    avail, gaps = set(nodes.available_nodes()), set(nodes.gap_nodes())
    assert avail and gaps
    assert not (avail & gaps)
    for g in gaps:
        assert nodes.NODES[g].get("gap_reason"), f"{g} gap must state a reason"
    # brent_dubai stays a gap (no sour feed); rbob_crack is now REAL (OHLCV feed)
    assert "brent_dubai" in gaps
    assert "rbob_crack" in avail


def test_real_data_panel_plausible_when_lake_present():
    panel = nodes.build_node_panel()
    if panel.empty:
        pytest.skip("/Data lake not available")
    assert "brent_flat" in panel.columns
    # distillate cracks should sit in a sane band on the real tape
    if "ho_crack" in panel.columns:
        assert 5 < panel["ho_crack"].median() < 60
    if "gasoil_crack" in panel.columns:
        assert 5 < panel["gasoil_crack"].median() < 60
    if "wti_brent" in panel.columns:
        assert -15 < panel["wti_brent"].median() < 10
