"""
PULSE — Inventory Surprise Impact Model (crude).

A backtested, regime-conditional framework for assessing the market impact of
the EIA Weekly Petroleum Status Report (crude oil). Answers the Futures First
brief: bullish / bearish / neutral on the upcoming release, the products/spreads
most affected, the top-3 driving factors, and the framework behind the call.

Layered design (see module docstrings for detail):
    L0  surprise engine      eia_report.surprise_series()      actual vs expected
    L2  quality-of-draw      eia_report.decomposition()        the whole report, not the headline
    L1  event study          event_study.run()                 conditional intraday betas
        spread attribution   event_study.attribution()         surprise type -> spread
        when-it-mattered      event_study.regime_table()        explanatory power by regime
    L4  scorecard / call     framework.assess_release()        the decision-ready output

Run the full pipeline:  python -m backend.research.inventory_impact
"""
