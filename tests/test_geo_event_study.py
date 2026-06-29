"""Tests for the per-node geo event study (Sprint 3).

The real corpus is too thin to grade (see the standalone), so these tests prove
the measurement + grading machinery on synthetic data: forward-move math, panel
assembly, hit-rate significance, magnitude betas, and the prior-then-learn
annotate_impact consumer.
"""

import numpy as np
import pandas as pd

from research.news_impact.geo import event_study_geo as es


def _daily(idx, **cols):
    return pd.DataFrame(cols, index=pd.to_datetime(idx))


def test_fwd_change_direction_and_staleness():
    idx = pd.bdate_range("2022-01-03", periods=10)
    s = pd.Series(np.arange(10, dtype=float) + 80.0, index=idx)   # strictly rising
    # event mid-series → +1 step is up
    out = es.fwd_change(s, pd.Timestamp("2022-01-07T10:00:00Z"), 1)
    assert out is not None and out[0] > 0
    # event after the series end → no post → None
    assert es.fwd_change(s, pd.Timestamp("2022-02-01"), 1) is None
    # huge pre-gap → None
    s2 = pd.Series([80.0, 81.0], index=pd.to_datetime(["2022-01-03", "2022-01-04"]))
    assert es.fwd_change(s2, pd.Timestamp("2022-03-01"), 1) is None


def test_build_event_panel_computes_hit_and_regime():
    idx = pd.bdate_range("2022-01-03", periods=15)
    panel = _daily(idx,
                   brent_flat=np.arange(15, dtype=float) + 80,        # rising
                   brent_structure=np.full(15, 1.5))                  # >0 → BACK
    events = [{"published_at": "2022-01-06T09:00:00Z", "asset_type": "chokepoint",
               "event_type": "closure", "conviction": {"brent_flat": 2.0}}]
    ep = es.build_event_panel(events=events, node_panel=panel)
    assert len(ep) == 1
    row = ep.iloc[0]
    assert row["node"] == "brent_flat" and row["pred_sign"] == 1
    assert row["regime"] == "BACK"
    assert row["hit1"] == 1.0          # predicted up, price rose


def test_node_hit_table_flags_real_edge():
    # 25 claims on one node, 20 correct → hit 0.8, should be significant
    n = 25
    df = pd.DataFrame({
        "node": ["gasoil_crack"] * n,
        "asset_type": ["chokepoint"] * n,
        "regime": ["BACK"] * n,
        "conviction": [2.0] * n,
        "pred_sign": [1] * n,
        "hit1": [1.0] * 20 + [0.0] * 5,
        "hit5": [1.0] * 13 + [0.0] * 12,    # ~coin flip
        "vn1": [1.0] * n, "vn5": [0.1] * n,
    })
    t1 = es.node_hit_table(df, 1)
    node_row = next(r for r in t1 if r["slice"] == "node")
    assert node_row["hit"] == 0.8 and node_row["significant"] is True
    # the ~coin-flip horizon is not significant
    t5 = es.node_hit_table(df, 5)
    assert all(not r["significant"] for r in t5)


def test_node_betas_measured_when_move_tracks_conviction():
    rng = np.random.default_rng(0)
    n = 40
    conv = rng.choice([-2.0, -1.0, 1.0, 2.0], n)
    vn_raw = 0.5 * conv + rng.normal(0, 0.05, n)     # move tracks conviction tightly
    pred = np.sign(conv).astype(int)
    df = pd.DataFrame({
        "node": ["ho_crack"] * n, "asset_type": ["refinery"] * n, "regime": ["BACK"] * n,
        "conviction": conv, "pred_sign": pred,
        "vn1": vn_raw * pred,        # stored aligned (build_event_panel convention)
        "hit1": (np.sign(vn_raw) == pred).astype(float),
    })
    betas = es.node_betas(df, 1)
    assert betas and betas[0]["node"] == "ho_crack"
    assert betas[0]["measured"] is True and betas[0]["beta"] > 0


def test_annotate_impact_prior_then_learn_and_specificity():
    cached = {"hit_tables": {"1": [
        {"slice": "node", "node": "gasoil_crack", "asset_type": "*", "regime": "*",
         "hit": 0.7, "n": 30, "p": 0.01, "significant": True},
        {"slice": "node×type", "node": "gasoil_crack", "asset_type": "chokepoint",
         "regime": "*", "hit": 0.82, "n": 22, "p": 0.004, "significant": True},
        {"slice": "node", "node": "brent_flat", "asset_type": "*", "regime": "*",
         "hit": 0.52, "n": 40, "p": 0.7, "significant": False},
    ]}}
    impact = {"nodes": {"gasoil_crack": 2.0, "brent_flat": 1.0}}
    ann = es.annotate_impact(impact, "chokepoint", "BACK", horizon=1, cached=cached)
    # measured edge → tradeable, and the MOST SPECIFIC significant slice wins
    assert ann["edges"]["gasoil_crack"]["tradeable"] is True
    assert ann["edges"]["gasoil_crack"]["slice"] == "node×type"
    # no significant slice → stays on prior
    assert ann["edges"]["brent_flat"]["tradeable"] is False
    assert ann["tradeable_nodes"] == ["gasoil_crack"]


def test_empty_inputs_dont_crash():
    assert es.build_event_panel(events=[], node_panel=None).empty
    assert es.node_hit_table(pd.DataFrame(), 1) == []
    assert es.node_betas(pd.DataFrame(), 1) == []
    out = es.annotate_impact({"nodes": {"brent_flat": 1.0}}, None, None, cached={})
    assert out["edges"]["brent_flat"]["tradeable"] is False
