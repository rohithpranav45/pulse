"""Quick exploration: spread series coverage + behaviour around key event dates."""
import sys
sys.path.insert(0, "backend")
from dotenv import load_dotenv; load_dotenv()
import pandas as pd

from data_lake import get_brent_settlements

settle = get_brent_settlements()
print(f"settle: {settle.shape}, {settle.index.min().date()} -> {settle.index.max().date()}")
print(f"cols: {list(settle.columns[:8])} ...")

spreads = pd.DataFrame(index=settle.index)
spreads["m1_m2"] = settle["c1"] - settle["c2"]
spreads["m2_m4"] = settle["c2"] - settle["c4"]
spreads["m1_m6"] = settle["c1"] - settle["c6"]
spreads = spreads.dropna()
print(f"\nspreads: {len(spreads)} rows")
print(spreads.describe().round(3))

print("\nCurrent levels (last 5 days):")
print(spreads.tail(5).round(3))

# Key events — check data exists around them
events = {
    "2018-05-08": "US exits JCPOA",
    "2019-05-12": "Fujairah tanker sabotage",
    "2019-06-13": "Gulf of Oman tanker attacks",
    "2019-06-20": "Iran downs US drone",
    "2019-09-14": "Abqaiq-Khurais attack",
    "2020-01-03": "Soleimani strike",
    "2022-02-24": "Russia invades Ukraine",
    "2023-10-07": "Hamas attack on Israel",
    "2024-01-12": "US/UK strikes Houthis",
    "2024-04-13": "Iran direct attack on Israel",
    "2024-10-01": "Iran missile barrage on Israel",
    "2024-10-26": "Israel strikes Iran military",
    "2025-06-13": "Israel-Iran war (12-day)",
}

print("\nEvent windows (D-1 level -> D+5 level, delta):")
for d, label in events.items():
    ts = pd.Timestamp(d)
    # last trading day strictly before event
    pre_idx = spreads.index[spreads.index < ts]
    post_idx = spreads.index[spreads.index >= ts]
    if len(pre_idx) == 0 or len(post_idx) < 6:
        print(f"  {d} {label:35s} -- INSUFFICIENT DATA")
        continue
    t0 = pre_idx[-1]
    t5 = post_idx[5] if len(post_idx) > 5 else post_idx[-1]
    row = []
    for s in ["m1_m2", "m2_m4", "m1_m6"]:
        d0, d5 = spreads.loc[t0, s], spreads.loc[t5, s]
        row.append(f"{s}: {d0:+.2f}->{d5:+.2f} (D{d5-d0:+.2f})")
    print(f"  {d} {label:35s} {' | '.join(row)}")

# What did m1_m2 do in June 2025 day by day (the closest analog)?
print("\nJune 2025 war — daily m1_m2 / m1_m6:")
win = spreads.loc["2025-06-09":"2025-07-03", ["m1_m2", "m1_m6"]]
print(win.round(3))

# Historical extremes for closure-scenario anchoring
print("\nExtremes:")
for s in spreads.columns:
    print(f"  {s}: max={spreads[s].max():+.2f} ({spreads[s].idxmax().date()}), "
          f"p99.5={spreads[s].quantile(0.995):+.2f}, p99={spreads[s].quantile(0.99):+.2f}")

# Unconditional 5-day change distribution (for baseline vol)
chg5 = spreads.diff(5).dropna()
print("\nUnconditional 5d changes:")
print(chg5.describe().round(3))
print("\n5d change std by regime proxy (m1_m12 backwardation > 5):")
m1_m12 = (settle["c1"] - settle["c12"]).reindex(chg5.index)
back = chg5[m1_m12 > 5]
print(f"  BACK regime n={len(back)}: std = {back.std().round(3).to_dict()}")
print(f"  ALL          n={len(chg5)}: std = {chg5.std().round(3).to_dict()}")
