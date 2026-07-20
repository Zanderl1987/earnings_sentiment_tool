import json
import math

import pandas as pd
import pytest

from src import earnings_surprise as es_module
from src.earnings_surprise import (FiscalDerivationError,
                                       EarningsSurpriseFetcher,
                                       build_surprise_table,
                                       derive_fiscal_quarters,
                                       verify_derivation)

# Shapes mimic AV function=EARNINGS. Dates are NVDA's / ORCL's real fiscal
# calendar; the live pull (scripts/pull_earnings_surprise.py) re-verifies
# against actual AV data, so these fixtures only need to be self-consistent.
NVDA_PAYLOAD = {
    "symbol": "NVDA",
    "annualEarnings": [
        {"fiscalDateEnding": "2024-01-28", "reportedEPS": "1.19"},
        {"fiscalDateEnding": "2023-01-29", "reportedEPS": "0.33"},
    ],
    "quarterlyEarnings": [
        {"fiscalDateEnding": "2024-04-28", "reportedDate": "2024-05-22",
         "reportedEPS": "0.61", "estimatedEPS": "0.56", "surprisePercentage": "8.9286"},
        {"fiscalDateEnding": "2024-01-28", "reportedDate": "2024-02-21",
         "reportedEPS": "0.52", "estimatedEPS": "0.46", "surprisePercentage": "13.0435"},
        {"fiscalDateEnding": "2023-10-29", "reportedDate": "2023-11-21",
         "reportedEPS": "0.40", "estimatedEPS": "0.34", "surprisePercentage": "17.6471"},
        {"fiscalDateEnding": "2023-07-30", "reportedDate": "2023-08-23",
         "reportedEPS": "0.27", "estimatedEPS": "0.21", "surprisePercentage": "28.5714"},
        {"fiscalDateEnding": "2023-04-30", "reportedDate": "2023-05-24",
         "reportedEPS": "0.11", "estimatedEPS": "0.09", "surprisePercentage": "22.2222"},
        {"fiscalDateEnding": "2023-01-29", "reportedDate": "2023-02-22",
         "reportedEPS": "0.09", "estimatedEPS": "0.08", "surprisePercentage": "12.5"},
        {"fiscalDateEnding": "2022-10-30", "reportedDate": "2022-11-16",
         "reportedEPS": "0.06", "estimatedEPS": "0.07", "surprisePercentage": "None"},
    ],
}

ORCL_PAYLOAD = {
    "symbol": "ORCL",
    "annualEarnings": [
        {"fiscalDateEnding": "2024-05-31", "reportedEPS": "5.56"},
        {"fiscalDateEnding": "2023-05-31", "reportedEPS": "5.12"},
    ],
    "quarterlyEarnings": [
        {"fiscalDateEnding": "2024-05-31", "reportedDate": "2024-06-11",
         "reportedEPS": "1.63", "estimatedEPS": "1.65", "surprisePercentage": "-1.2121"},
        {"fiscalDateEnding": "2024-02-29", "reportedDate": "2024-03-11",
         "reportedEPS": "1.41", "estimatedEPS": "1.38", "surprisePercentage": "2.1739"},
        {"fiscalDateEnding": "2023-11-30", "reportedDate": "2023-12-11",
         "reportedEPS": "1.34", "estimatedEPS": "1.32", "surprisePercentage": "1.5152"},
        {"fiscalDateEnding": "2023-08-31", "reportedDate": "2023-09-11",
         "reportedEPS": "1.19", "estimatedEPS": "1.15", "surprisePercentage": "3.4783"},
    ],
}


def test_nvda_derivation_matches_probe_ground_truth():
    labels = derive_fiscal_quarters(NVDA_PAYLOAD["quarterlyEarnings"],
                                    NVDA_PAYLOAD["annualEarnings"])
    assert labels["2023-07-30"] == "2024Q2"   # probe's direct observation
    assert labels["2024-04-28"] == "2025Q1"   # FQ1 FY2025 (extrapolated FY end)
    assert labels["2024-01-28"] == "2024Q4"
    assert labels["2022-10-30"] == "2023Q3"   # partial first FY still numbers right


def test_orcl_derivation_matches_probe_ground_truth():
    labels = derive_fiscal_quarters(ORCL_PAYLOAD["quarterlyEarnings"],
                                    ORCL_PAYLOAD["annualEarnings"])
    assert labels["2023-11-30"] == "2024Q2"   # probe's direct observation
    assert labels["2024-05-31"] == "2024Q4"   # FQ4 FY2024
    assert labels["2023-08-31"] == "2024Q1"


def test_53_week_calendar_drift_tolerated():
    # A Jan-FYE company whose Q1 slips into early May (53-week year) must
    # still label as Q1 of the fiscal year ending the FOLLOWING January.
    annual = [{"fiscalDateEnding": "2020-01-26"}, {"fiscalDateEnding": "2021-01-31"}]
    quarterly = [{"fiscalDateEnding": "2020-05-03", "reportedDate": "2020-05-21"}]
    labels = derive_fiscal_quarters(quarterly, annual)
    assert labels["2020-05-03"] == "2021Q1"


def test_missing_annual_year_raises():
    # A gap in annualEarnings would silently mislabel a whole year - hard stop.
    annual = [{"fiscalDateEnding": "2020-12-31"}, {"fiscalDateEnding": "2022-12-31"}]
    quarterly = [{"fiscalDateEnding": "2021-03-31", "reportedDate": "2021-04-20"}]
    with pytest.raises(FiscalDerivationError):
        derive_fiscal_quarters(quarterly, annual)


def test_duplicate_label_raises():
    annual = [{"fiscalDateEnding": "2023-12-31"}]
    quarterly = [{"fiscalDateEnding": "2023-03-31"}, {"fiscalDateEnding": "2023-04-15"}]
    with pytest.raises(FiscalDerivationError):
        derive_fiscal_quarters(quarterly, annual)


def test_stub_annual_row_for_in_progress_fiscal_year_does_not_collide():
    # Live NVDA pull 2026-07-16: AV's annualEarnings included a stub row for
    # the most recent (still in-progress) fiscal year, dated to the latest
    # quarter's own fiscalDateEnding instead of a real FYE. reportedEPS on
    # the stub is quarter-sized (1.87), not annual-sized, and its month
    # (April) breaks with every other annual row's month (January). Treating
    # it as a real FYE candidate made the Q1 FY2027 quarter derive as
    # "2026Q4", colliding with the real Q4 FY2026 quarter.
    annual = [
        {"fiscalDateEnding": "2026-04-30", "reportedEPS": "1.87"},  # stub
        {"fiscalDateEnding": "2026-01-31", "reportedEPS": "4.78"},
        {"fiscalDateEnding": "2025-01-31", "reportedEPS": "2.992"},
    ]
    quarterly = [
        {"fiscalDateEnding": "2026-04-30", "reportedDate": "2026-05-20"},
        {"fiscalDateEnding": "2026-01-31", "reportedDate": "2026-02-25"},
        {"fiscalDateEnding": "2025-10-31", "reportedDate": "2025-11-19"},
    ]
    labels = derive_fiscal_quarters(quarterly, annual)
    assert labels["2026-01-31"] == "2026Q4"
    assert labels["2026-04-30"] == "2027Q1"


def test_empty_inputs_return_empty():
    assert derive_fiscal_quarters([], []) == {}
    assert derive_fiscal_quarters([{"fiscalDateEnding": "2023-03-31"}], []) == {}


def test_build_surprise_table_shape_and_nan():
    table = build_surprise_table(NVDA_PAYLOAD)
    assert list(table.columns) == ["quarter", "fiscal_date_ending",
                                   "reported_date", "surprise_pct"]
    assert len(table) == 7
    assert table["fiscal_date_ending"].is_monotonic_increasing
    row = table[table["quarter"] == "2024Q2"].iloc[0]
    assert row["reported_date"] == "2023-08-23"
    assert row["surprise_pct"] == pytest.approx(28.5714)
    # AV sends the string "None" when it has no estimate -> NaN, not a crash
    q3 = table[table["quarter"] == "2023Q3"].iloc[0]
    assert math.isnan(q3["surprise_pct"])


def test_verify_derivation_passes_on_ground_truth():
    table = build_surprise_table(NVDA_PAYLOAD)
    verify_derivation(table, [("2023-08-23", "2024Q2"), ("2024-05-22", "2025Q1")])


def test_verify_derivation_raises_on_wrong_label():
    table = build_surprise_table(NVDA_PAYLOAD)
    with pytest.raises(FiscalDerivationError):
        verify_derivation(table, [("2023-08-23", "2024Q1")])


def test_verify_derivation_raises_when_no_nearby_row():
    table = build_surprise_table(ORCL_PAYLOAD)
    with pytest.raises(FiscalDerivationError):
        verify_derivation(table, [("2019-06-11", "2019Q4")])


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


def test_fetcher_cache_hit_never_touches_network(tmp_path, monkeypatch):
    cache = tmp_path / "NVDA.json"
    cache.write_text(json.dumps(NVDA_PAYLOAD), encoding="utf-8")

    def _no_network(*args, **kwargs):
        raise AssertionError("cache hit must not call requests.get")

    monkeypatch.setattr(es_module.requests, "get", _no_network)
    fetcher = EarningsSurpriseFetcher(cache_dir=str(tmp_path))
    assert fetcher.fetch_earnings("NVDA") == NVDA_PAYLOAD


def test_fetcher_rotates_key_on_quota_and_caches_success(tmp_path, monkeypatch):
    monkeypatch.setenv("ALPHA_VANTAGE_API_KEY", "key1")
    monkeypatch.setenv("ALPHA_VANTAGE_API_KEY_2", "key2")
    monkeypatch.setattr(es_module.time, "sleep", lambda s: None)
    responses = [
        _FakeResponse({"Information": "25 requests per day limit reached"}),
        _FakeResponse(ORCL_PAYLOAD),
    ]
    monkeypatch.setattr(es_module.requests, "get",
                        lambda *a, **kw: responses.pop(0))

    fetcher = EarningsSurpriseFetcher(cache_dir=str(tmp_path))
    payload = fetcher.fetch_earnings("ORCL")
    assert payload == ORCL_PAYLOAD
    assert fetcher.key_index == 1
    assert json.loads((tmp_path / "ORCL.json").read_text(encoding="utf-8")) == ORCL_PAYLOAD


def test_fetcher_returns_none_and_caches_nothing_when_all_keys_exhausted(tmp_path, monkeypatch):
    monkeypatch.setenv("ALPHA_VANTAGE_API_KEY", "key1")
    monkeypatch.setenv("ALPHA_VANTAGE_API_KEY_2", "key2")
    monkeypatch.setattr(es_module.time, "sleep", lambda s: None)
    monkeypatch.setattr(
        es_module.requests, "get",
        lambda *a, **kw: _FakeResponse({"Information": "25 requests per day limit reached"}))

    fetcher = EarningsSurpriseFetcher(cache_dir=str(tmp_path))
    assert fetcher.fetch_earnings("IEP") is None
    assert fetcher.exhausted is True
    assert not (tmp_path / "IEP.json").exists()
    # exhausted flag short-circuits: no further network attempts this run
    monkeypatch.setattr(es_module.requests, "get",
                        lambda *a, **kw: (_ for _ in ()).throw(AssertionError("no retry")))
    assert fetcher.fetch_earnings("AMD") is None
