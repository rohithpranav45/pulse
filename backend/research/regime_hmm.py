"""
regime_hmm.py — data-driven curve regimes (Phase 6 / 2.8.9).

The Phase 2 regime grid splits the curve axis on **hard trader thresholds**:
CONTANGO ≤ −$2 < NEUTRAL ≤ +$5 < BACK (see regimes.classify_curve). Those
numbers are trader-chosen, not fit to data — the open question (mentor directive
2.8.9) is whether a *fitted* regime detector that discovers the curve regimes
from the data beats both the regime-unaware baseline and the hard-threshold
pooled / global variants on NET Sharpe.

This module answers that with a **Gaussian-mixture + causal sticky-HMM** detector
over the curve level (`m1_m12`) and its 5-day change (a change-point/momentum
feature). It mirrors shock_engine.StressDetector's machinery exactly — GMM
emission posterior + a sticky forward filter for persistence — so it needs no
new dependency (sklearn.mixture only) and deploys to HF cleanly.

Design choices that keep it honest and comparable to the hard grid:
  • **Ordinal relabelling.** GMM component indices are arbitrary; we sort the
    fitted components by their mean curve level and relabel R0 (deepest
    contango) … R{K−1} (deepest backwardation). The labels are then stable
    across refits, so a cell trained for (spread, R1) at refit t is looked up
    correctly in refit t's forward window.
  • **Causal labelling.** The forward filter at day d uses only observations
    ≤ d (look-ahead-free), so the walk-forward's out-of-sample window labels
    are honest. The GMM *parameters* are fit on the training slice (≤ cutoff)
    only — the regime *definition* is learned in-sample, then applied forward,
    exactly as the hard thresholds are fixed on history then applied forward.
  • **Persistence.** A sticky K-state transition matrix (self-prob `stay`,
    uniform leakage) stops the regime from flickering day-to-day — that
    persistence is what makes these *regimes* rather than per-day clusters,
    and gives the detector a change-point flavour (it switches state only when
    the evidence is sustained).

Public API
----------
  CURVE_HMM_FEATURES                       feature columns used by the detector
  CurveRegimeHMM(n_states=3).fit(df)       fit GMM on a training frame (≤ cutoff)
  detector.label_series(df) -> pd.Series   causal ordinal regime labels ("R0"…)
  detector.state_labels                    ["R0", …, "R{K-1}"]
  detector.state_summary() -> dict         per-state curve-level means + implied
                                           boundaries (the data-driven analog of
                                           the −$2/+$5 trader thresholds)
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

# Curve level + its 5-day change. Level captures contango/backwardation;
# the change captures the *speed* of a curve move — the change-point signal a
# static threshold on the level alone is blind to.
CURVE_HMM_FEATURES = ["m1_m12", "curve_chg_5d"]

N_HMM_STATES_DEFAULT = 3       # matched to the 3 hard curve buckets for a fair test
HMM_STAY_DEFAULT     = 0.95    # sticky self-transition prob (persistence)
_CHG_WINDOW          = 5       # days for the curve-change feature


def _curve_feature_frame(curve: pd.Series) -> pd.DataFrame:
    """Build the [m1_m12, curve_chg_5d] frame from a curve-level series."""
    curve = curve.astype(float)
    df = pd.DataFrame(index=curve.index)
    df["m1_m12"]       = curve
    df["curve_chg_5d"] = curve.diff(_CHG_WINDOW)
    return df


class CurveRegimeHMM:
    """Data-driven curve regime detector — GMM + causal sticky-HMM smoothing."""

    def __init__(self, n_states: int = N_HMM_STATES_DEFAULT,
                 stay: float = HMM_STAY_DEFAULT, random_state: int = 42):
        if n_states < 2:
            raise ValueError("n_states must be ≥ 2")
        self.n_states = int(n_states)
        self.stay = float(stay)
        self.random_state = int(random_state)
        self.gmm = None
        self.mu_ = None
        self.sd_ = None
        # order_[k] = GMM component index of the k-th ordinal state (k=0 lowest
        # curve level). inv_order_[component] = ordinal rank.
        self.order_: np.ndarray | None = None
        self.inv_order_: np.ndarray | None = None
        self.state_means_: np.ndarray | None = None  # mean m1_m12 per ordinal state

    @property
    def state_labels(self) -> list[str]:
        return [f"R{k}" for k in range(self.n_states)]

    def _standardize(self, feats: pd.DataFrame) -> np.ndarray:
        return ((feats[CURVE_HMM_FEATURES] - self.mu_) / self.sd_).values

    def fit(self, df: pd.DataFrame, *, curve_col: str = "m1_m12") -> "CurveRegimeHMM":
        """Fit the GMM on a training frame (rows ≤ cutoff). `df` must carry the
        curve level in `curve_col`; the 5-day change is derived here."""
        from sklearn.mixture import GaussianMixture

        feats = _curve_feature_frame(df[curve_col]).dropna()
        if len(feats) < self.n_states * 5:
            raise RuntimeError(
                f"CurveRegimeHMM.fit: only {len(feats)} usable rows for "
                f"{self.n_states} states"
            )
        self.mu_ = feats[CURVE_HMM_FEATURES].mean()
        self.sd_ = feats[CURVE_HMM_FEATURES].std().replace(0, 1.0)
        Xz = ((feats[CURVE_HMM_FEATURES] - self.mu_) / self.sd_).values
        self.gmm = GaussianMixture(
            n_components=self.n_states, covariance_type="full",
            random_state=self.random_state, max_iter=300, n_init=3,
        ).fit(Xz)

        # Ordinal relabel by ascending mean curve level (feature index 0 =
        # m1_m12). De-standardise the component means so state_means_ are in
        # real $/bbl for the mentor-facing threshold comparison.
        lvl_idx = CURVE_HMM_FEATURES.index("m1_m12")
        means_z = self.gmm.means_[:, lvl_idx]
        self.order_ = np.argsort(means_z)
        self.inv_order_ = np.argsort(self.order_)
        self.state_means_ = (
            means_z[self.order_] * float(self.sd_.iloc[lvl_idx]) + float(self.mu_.iloc[lvl_idx])
        )
        return self

    def _transition(self) -> np.ndarray:
        """Sticky K-state transition matrix: `stay` on the diagonal, the
        remaining mass spread uniformly across the other states."""
        K = self.n_states
        leak = (1.0 - self.stay) / (K - 1)
        A = np.full((K, K), leak)
        np.fill_diagonal(A, self.stay)
        return A

    def filtered_states(self, df: pd.DataFrame, *, curve_col: str = "m1_m12") -> pd.Series:
        """Causal forward-filter most-likely component (in GMM component order)
        per row, indexed over the rows with complete features. Internal helper —
        callers use `label_series` for ordinal string labels."""
        if self.gmm is None:
            raise RuntimeError("CurveRegimeHMM not fit")
        feats = _curve_feature_frame(df[curve_col]).dropna()
        if feats.empty:
            return pd.Series([], dtype=object)
        emis = self.gmm.predict_proba(self._standardize(feats))  # (T, K) posteriors
        A = self._transition()
        K = self.n_states
        f = np.full(K, 1.0 / K)
        out = np.empty(len(emis), dtype=int)
        for t in range(len(emis)):
            pred = A.T @ f
            f = pred * emis[t]                 # emission likelihood ≈ GMM posterior
            s = f.sum()
            f = f / s if s > 0 else np.full(K, 1.0 / K)
            out[t] = int(np.argmax(f))
        return pd.Series(out, index=feats.index, name="hmm_component")

    def label_series(self, df: pd.DataFrame, *, curve_col: str = "m1_m12") -> pd.Series:
        """Causal ordinal regime labels ("R0"…"R{K-1}") aligned to `df.index`.
        Rows whose curve features are incomplete (the 5-day burn-in at the very
        start) get "UNKNOWN" — they drop out of training/eval downstream."""
        comp = self.filtered_states(df, curve_col=curve_col)
        ordinal = comp.map(lambda c: f"R{int(self.inv_order_[c])}")
        return ordinal.reindex(df.index).fillna("UNKNOWN").rename("regime_hmm")

    def state_summary(self) -> dict:
        """Per-state mean curve level + the implied boundaries between adjacent
        states (midpoints of sorted state means) — the data-driven analog of the
        hard −$2 / +$5 trader thresholds, for the mentor-facing comparison."""
        if self.state_means_ is None:
            raise RuntimeError("CurveRegimeHMM not fit")
        means = [round(float(m), 3) for m in self.state_means_]
        bounds = [round(float((means[k] + means[k + 1]) / 2.0), 3)
                  for k in range(len(means) - 1)]
        return {
            "n_states":          self.n_states,
            "stay":              self.stay,
            "state_curve_means": dict(zip(self.state_labels, means)),
            "implied_boundaries": bounds,
            "hard_thresholds":   [-2.0, 5.0],   # regimes.classify_curve cuts
        }


if __name__ == "__main__":
    import warnings; warnings.filterwarnings("ignore")
    from research.features import build_features

    df = build_features()
    print(f"feature frame: {df.shape}  {df.index.min().date()} → {df.index.max().date()}")
    for K in (2, 3, 4):
        det = CurveRegimeHMM(n_states=K).fit(df.loc[:"2024-01-01"])
        labels = det.label_series(df)
        summ = det.state_summary()
        occ = labels.value_counts(normalize=True).round(3).to_dict()
        print(f"\nK={K}  state curve means $: {summ['state_curve_means']}")
        print(f"      implied boundaries:  {summ['implied_boundaries']}  (hard: -2 / +5)")
        print(f"      occupancy:           {occ}")
