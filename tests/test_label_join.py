import math

import pandas as pd

from src.label_join import CAR_HORIZONS, build_labels

PANEL = pd.DataFrame({
    "quarter": ["2024Q1", "2024Q2", "2024Q3"],
    "word_count": [5000, 6200, 4100],
    "fog_index": [14.2, 15.1, 13.8],
})

SURPRISE = pd.DataFrame({
    "quarter": ["2023Q4", "2024Q1", "2024Q2"],   # 2023Q4 has no panel row
    "fiscal_date_ending": ["2023-12-31", "2024-03-31", "2024-06-30"],
    "reported_date": ["2024-01-25", "2024-04-24", "2024-07-23"],
    "surprise_pct": [3.1, -7.5, float("nan")],
})

CARS = pd.DataFrame({
    "symbol": ["TEST"],
    "quarter": ["2024Q1"],                        # 2024Q2 event lacked prices
    "car_1": [-0.021], "car_3": [-0.034], "car_5": [-0.030],
    "car_10": [-0.045], "car_21": [-0.052],
})


def test_build_labels_joins_without_row_loss():
    out = build_labels(PANEL, SURPRISE, CARS)
    assert len(out) == len(PANEL)                       # no loss, no dupes
    assert list(out["quarter"]) == list(PANEL["quarter"])
    r1 = out[out["quarter"] == "2024Q1"].iloc[0]
    assert r1["surprise_pct"] == -7.5
    assert r1["reported_date"] == "2024-04-24"
    assert r1["car_21"] == -0.052
    r2 = out[out["quarter"] == "2024Q2"].iloc[0]
    assert math.isnan(r2["surprise_pct"])               # AV had no estimate
    assert math.isnan(r2["car_21"])                     # no price coverage
    r3 = out[out["quarter"] == "2024Q3"].iloc[0]
    assert math.isnan(r3["surprise_pct"])               # no earnings row at all
    assert pd.isna(r3["reported_date"])


def test_build_labels_handles_missing_cars_frame():
    out = build_labels(PANEL, SURPRISE, None)
    assert len(out) == len(PANEL)
    for h in CAR_HORIZONS:
        assert out[f"car_{h}"].isna().all()


def test_build_labels_keeps_panel_columns():
    out = build_labels(PANEL, SURPRISE, CARS)
    assert "word_count" in out.columns and "fog_index" in out.columns
