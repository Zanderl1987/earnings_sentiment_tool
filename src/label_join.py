"""
Joins external bad-news labels (earnings surprise + CARs) onto the
verbosity panel. Spec: docs/superpowers/specs/2026-07-13-label-join-design.md.

CARs come from ONE batched cross-repo call into
financial-data-pipeline/event_backtest.py (entry_lag=0, benchmark SPY,
window (-1, 21) - signal-eval defaults). Set FDP_REPO_PATH to override the
sibling-repo location. event_study silently drops events without price
coverage and raises only if ZERO survive - build_labels turns dropped
events into NaN label columns rather than failing the run.

entry_lag=0 (overrides the spec's original entry_lag=1; Zander's call,
2026-07-15): in event_backtest.py, entry_lag=1 makes the baseline the
close ON the reportedDate itself, which means the announcement-day
reaction is EXCLUDED from the CAR for before-open (BMO) reporters (VRT,
VST) but INCLUDED for after-close (AMC) reporters (AMD, PLTR, IEP) -
the label would silently mean different things for different tickers.
entry_lag=0 puts the reaction inside the window for every ticker
regardless of report timing, so the label is comparable across the panel.

TRAP: entry_lag=0 is a LOOK-AHEAD BUG when building a tradable signal (it
is exactly what invalidated the oil_shock factor in financial-data-pipeline,
which was reversed for this reason - see that repo's history). It is
CORRECT here only because these CARs are a NEWS-CONTENT label describing
what happened, not a signal anyone claims to trade on same-day
information. Do not "fix" this back to entry_lag=1.
"""
import os
import sys

import pandas as pd

FDP_ROOT = os.getenv(
    "FDP_REPO_PATH",
    r"C:\Users\zande\PycharmProjects\financial-data-pipeline")

CAR_HORIZONS = (1, 3, 5, 10, 21)


def _load_event_backtest():
    if FDP_ROOT not in sys.path:
        sys.path.insert(0, FDP_ROOT)
    import event_backtest
    return event_backtest


def compute_cars(events):
    """events: DataFrame[symbol, date, quarter] (date = AV reportedDate).
    Returns DataFrame[symbol, quarter, car_1..car_21] for the events that
    had price coverage; events event_study dropped are simply absent."""
    eb = _load_event_backtest()
    result = eb.event_study(events, window=(-1, 21),
                            benchmark="SPY", entry_lag=0)
    out = result.events[["symbol", "quarter"]].reset_index(drop=True)
    for h in CAR_HORIZONS:
        out[f"car_{h}"] = result.car[h].to_numpy()
    return out


def build_labels(panel, surprise_table, cars):
    """Left-join surprise + CAR labels onto the per-quarter verbosity panel.
    Never drops or duplicates panel rows; quarters without labels get NaN."""
    labels = surprise_table[["quarter", "reported_date", "surprise_pct"]]
    merged = panel.merge(labels, on="quarter", how="left", validate="one_to_one")
    if cars is not None and not cars.empty:
        merged = merged.merge(cars.drop(columns=["symbol"]),
                              on="quarter", how="left", validate="one_to_one")
    for h in CAR_HORIZONS:
        if f"car_{h}" not in merged.columns:
            merged[f"car_{h}"] = float("nan")
    if len(merged) != len(panel):
        raise ValueError(
            f"label join changed row count {len(panel)} -> {len(merged)}")
    return merged
