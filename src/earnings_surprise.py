"""
External earnings-surprise labels via Alpha Vantage function=EARNINGS.
Spec: docs/superpowers/specs/2026-07-13-label-join-design.md.

AV's YYYYQN labels are FISCAL - fiscal year named by its ending calendar
year, quarter numbered within it (probe 2026-07-13,
scripts/probe_fiscal_quarters.py). The EARNINGS response has no YYYYQN
field, so derive_fiscal_quarters() reconstructs the label from
fiscalDateEnding + the annualEarnings fiscal-year boundaries; any join
against the transcript cache MUST use these derived labels, and only
after they pass verification against DERIVATION_GROUND_TRUTH.

AV also sometimes appends a stub row to annualEarnings for the current,
still-in-progress fiscal year (observed live, NVDA 2026-07-16) - dated to
the latest quarter's own fiscalDateEnding rather than a real FYE.
_drop_stub_annual_rows() filters these out by majority FYE month before
any boundary is computed.
"""
import os
import time
import json
from collections import Counter

import pandas as pd
import requests

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Probe ground truth (corrected 2026-07-15): (ticker, reportedDate, label).
# The first and third rows are the probe's direct observations; the others
# follow from NVDA FYE late-Jan / ORCL FYE May-31.
DERIVATION_GROUND_TRUTH = [
    ("NVDA", "2023-08-23", "2024Q2"),
    ("NVDA", "2024-05-22", "2025Q1"),
    ("ORCL", "2023-12-11", "2024Q2"),
    ("ORCL", "2024-06-11", "2024Q4"),
]


class FiscalDerivationError(Exception):
    """Quarterly earnings could not be mapped cleanly onto fiscal years."""


def _drop_stub_annual_rows(annual):
    """AV sometimes appends a placeholder row to annualEarnings for the
    in-progress fiscal year, dated to the latest quarter's own
    fiscalDateEnding rather than a real fiscal-year end (observed live,
    NVDA 2026-07-16: a 2026-04-30 stub alongside the real 2026-01-31 FYE).
    A real FYE recurs on the same month every year; the stub doesn't. Drop
    any row whose month disagrees with the majority month."""
    months = [pd.Timestamp(r["fiscalDateEnding"]).month for r in annual]
    if not months:
        return annual
    majority_month = Counter(months).most_common(1)[0][0]
    return [r for r in annual
            if pd.Timestamp(r["fiscalDateEnding"]).month == majority_month]


def derive_fiscal_quarters(quarterly, annual):
    """
    quarterly/annual: AV EARNINGS 'quarterlyEarnings'/'annualEarnings' lists
    (dicts with at least 'fiscalDateEnding' as YYYY-MM-DD). Returns
    {fiscalDateEnding: 'YYYYQN'}.

    Fiscal year = calendar year of the annual fiscalDateEnding the quarter
    falls under (extrapolated forward one year at a time past the last
    reported annual, for the in-progress fiscal year). Quarter number from
    month distance to that fiscal year end - round() absorbs the +/- 1 month
    drift of 52/53-week calendars. Anything that doesn't land cleanly on
    Q1..Q4, or two quarters landing on the same label, raises
    FiscalDerivationError (hard stop: never join on a suspect key).
    """
    q_ends = sorted({pd.Timestamp(r["fiscalDateEnding"]) for r in quarterly})
    fy_ends = sorted({pd.Timestamp(r["fiscalDateEnding"])
                      for r in _drop_stub_annual_rows(annual)})
    if not q_ends or not fy_ends:
        return {}
    while fy_ends[-1] < q_ends[-1]:
        fy_ends.append(fy_ends[-1] + pd.DateOffset(years=1))

    labels, claimed = {}, {}
    for q in q_ends:
        candidates = [a for a in fy_ends if a >= q - pd.Timedelta(days=10)]
        if not candidates:
            raise FiscalDerivationError(
                f"no fiscal year end on or after quarter end {q.date()}")
        fy_end = candidates[0]
        months = (fy_end.year - q.year) * 12 + (fy_end.month - q.month)
        n = 4 - round(months / 3)
        if not 1 <= n <= 4:
            raise FiscalDerivationError(
                f"quarter end {q.date()} sits {months} months before fiscal "
                f"year end {fy_end.date()} - annualEarnings gap or bad data")
        label = f"{fy_end.year}Q{n}"
        if label in claimed:
            raise FiscalDerivationError(
                f"{claimed[label].date()} and {q.date()} both derived {label}")
        claimed[label] = q
        labels[q.strftime("%Y-%m-%d")] = label
    return labels


def _to_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return float("nan")


def build_surprise_table(payload):
    """AV EARNINGS payload -> DataFrame[quarter, fiscal_date_ending,
    reported_date, surprise_pct], sorted chronologically."""
    quarterly = payload.get("quarterlyEarnings") or []
    annual = payload.get("annualEarnings") or []
    labels = derive_fiscal_quarters(quarterly, annual)
    rows = [{
        "quarter": labels[r["fiscalDateEnding"]],
        "fiscal_date_ending": r["fiscalDateEnding"],
        "reported_date": r.get("reportedDate"),
        "surprise_pct": _to_float(r.get("surprisePercentage")),
    } for r in quarterly if r.get("fiscalDateEnding") in labels]
    table = pd.DataFrame(rows, columns=["quarter", "fiscal_date_ending",
                                        "reported_date", "surprise_pct"])
    return table.sort_values("fiscal_date_ending").reset_index(drop=True)


def verify_derivation(table, ground_truth):
    """Hard-stop check that derived labels reproduce the fiscal probe's
    ground truth. ground_truth: [(reported_date, expected_label), ...].
    Raises FiscalDerivationError on any mismatch or missing row."""
    dates = pd.to_datetime(table["reported_date"], errors="coerce")
    for reported_date, expected in ground_truth:
        gaps = (dates - pd.Timestamp(reported_date)).abs()
        if gaps.isna().all():
            raise FiscalDerivationError(
                f"no reported_date values to match {reported_date}")
        i = gaps.idxmin()
        if gaps[i] > pd.Timedelta(days=5):
            raise FiscalDerivationError(
                f"no earnings row within 5 days of {reported_date} "
                f"(nearest: {table.loc[i, 'reported_date']})")
        got = table.loc[i, "quarter"]
        if got != expected:
            raise FiscalDerivationError(
                f"row reported {table.loc[i, 'reported_date']} derived "
                f"{got}, probe ground truth says {expected}")


class EarningsSurpriseFetcher:
    """
    One function=EARNINGS call per ticker - the full quarterly history -
    cached permanently to storage/earnings_surprise/{ticker}.json. Same
    key-rotation/cache pattern as TranscriptFetcher (same AV account and
    25-req/day per-IP quota). Failures return None and are NEVER cached.
    """

    AV_URL = "https://www.alphavantage.co/query"

    def __init__(self, cache_dir=None):
        if cache_dir is None:
            cache_dir = os.path.join(PROJECT_ROOT, "storage", "earnings_surprise")
        self.cache_dir = cache_dir
        self.api_keys = [k for k in [os.getenv("ALPHA_VANTAGE_API_KEY"),
                                     os.getenv("ALPHA_VANTAGE_API_KEY_2")] if k]
        self.key_index = 0
        self.exhausted = False
        os.makedirs(self.cache_dir, exist_ok=True)

    @property
    def api_key(self):
        if self.key_index >= len(self.api_keys):
            return None
        return self.api_keys[self.key_index]

    def fetch_earnings(self, ticker):
        """Returns the raw EARNINGS payload dict (cache-first), or None if
        no data could be fetched (quota exhausted, no key, AV error)."""
        cache_file = os.path.join(self.cache_dir, f"{ticker}.json")
        if os.path.exists(cache_file):
            with open(cache_file, "r", encoding="utf-8") as f:
                return json.load(f)

        if not self.api_key:
            print(f"No usable Alpha Vantage key (quota exhausted or unset). Skipping {ticker} EARNINGS.")
            return None
        if self.exhausted:
            print(f"Skipping {ticker} EARNINGS: keys already exhausted this run.")
            return None

        print(f"Fetching {ticker} EARNINGS history from Alpha Vantage...")
        time.sleep(12)  # free-tier rate limit, same as TranscriptFetcher
        response = requests.get(self.AV_URL, params={
            "function": "EARNINGS",
            "symbol": ticker,
            "apikey": self.api_key,
        })
        data = response.json()

        if "quarterlyEarnings" not in data:
            error_msg = data.get("Information") or data.get("Error Message") or data.get("Note") or "Unknown error"
            print(f"Error fetching {ticker} EARNINGS: {error_msg}")
            if "requests per day" in error_msg or "rate limit" in error_msg.lower():
                self.key_index += 1
                if self.api_key:
                    print(f"Daily quota hit on previous key, switching to backup key ({self.key_index + 1}/{len(self.api_keys)}).")
                    return self.fetch_earnings(ticker)
                print("All API keys have hit their daily quota.")
                self.exhausted = True
            return None

        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(data, f)
        return data
