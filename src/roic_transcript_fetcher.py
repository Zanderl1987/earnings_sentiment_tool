"""
Supplementary earnings-call transcript source via Roic AI's API. Free tier
covers only the most recent 8 fiscal quarters per company (roic.ai/pricing,
confirmed live 2026-07-29) - well short of this project's full 2020Q2-2026Q2
pinned window - but its 5-req/min limit clears that window in minutes,
offloading the newest quarters from Alpha Vantage's 25-req/day bottleneck for
whichever tickers haven't been pulled yet.

Roic's endpoint takes fiscal_year/fiscal_quarter (same fiscal-quarter concept
as Alpha Vantage's quarter=YYYYQN, per Roic's own docs: "retrieve any
historical transcript by fiscal year and quarter") but this has NOT been
verified to agree with AV's fiscal-quarter numbering for fiscal-offset
tickers - the exact same trap that made AV's own quarter labels unreliable
until probed (see earnings_surprise.py). verify_against_earnings_surprise()
cross-checks a pull's call date against this project's own AV-derived
reported_date (storage/earnings_surprise/{ticker}.json via
build_surprise_table()) before the label is trusted, mirroring
earnings_surprise.verify_derivation()'s pattern. That ground truth only
exists for the 5 study tickers (IEP/PLTR/AMD/VRT/VST) pulled in Step 1 - for
any other ticker, Roic's fiscal-quarter labeling is UNVERIFIED and relies on
the (reasonable but unconfirmed) assumption that it follows the same SEC
fiscal calendar Alpha Vantage does.

Cached transcripts are normalized to Alpha Vantage's turn shape
({speaker, content}, tagged source="roic") and written to the SAME cache
path TranscriptFetcher reads from (storage/transcripts/{ticker}_{quarter}.json),
so a Roic-filled quarter is transparently skipped by future AV pulls and is
immediately usable by earnings_call_study.py with no changes there. Roic
transcripts have no per-turn sentiment score (unlike AV's own precomputed
'sentiment' field) - av_sentiment will be NaN for these quarters.
run_earnings_call_study() correlates av_sentiment pairwise (dropna per pair,
not a whole-column skip), so mixing sources only drops the Roic-sourced
quarters from THAT specific correlation, not the whole ticker.
lm_net_sentiment/fog_index are unaffected either way, since those are
computed locally from transcript text regardless of source.
"""
import os
import time
import json

import pandas as pd
import requests

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class RoicQuarterMismatchError(Exception):
    """Roic's fiscal-quarter labeling for a call didn't match this project's
    own AV-derived reported_date - never trust the label without checking."""


def verify_against_earnings_surprise(quarter, roic_date, surprise_rows, tolerance_days=5):
    """
    surprise_rows: build_surprise_table() output rows (dicts with at least
    'quarter' and 'reported_date'), e.g. df.to_dict('records'). Raises
    RoicQuarterMismatchError if `quarter` isn't in the surprise table, or if
    roic_date is more than tolerance_days from that quarter's reported_date -
    same tolerance verify_derivation() uses for the AV probe.
    """
    matches = [r for r in surprise_rows if r.get("quarter") == quarter]
    if not matches:
        raise RoicQuarterMismatchError(
            f"{quarter} not found in the earnings-surprise table - "
            f"cannot verify Roic's fiscal-quarter label")
    gap = abs(pd.Timestamp(roic_date) - pd.Timestamp(matches[0]["reported_date"]))
    if gap > pd.Timedelta(days=tolerance_days):
        raise RoicQuarterMismatchError(
            f"Roic's {quarter} call is dated {roic_date}, but this project's "
            f"own AV-derived reported_date for {quarter} is "
            f"{matches[0]['reported_date']} ({gap.days} days apart) - "
            f"Roic's fiscal-quarter numbering does not match AV's for this ticker")


class RoicTranscriptFetcher:
    """
    Fetches earnings call transcripts via Roic AI's /earnings-calls/{id}
    endpoint (fiscal_year + fiscal_quarter query params). Free tier: 5
    req/min, most recent 8 fiscal quarters only (confirmed live 2026-07-29).
    Cache-first, same on-disk path as TranscriptFetcher, so this and the AV
    puller never duplicate work - whichever source fills a quarter first
    wins, and the other silently skips it on its next run.
    """

    API_URL = "https://api.roic.ai/v3.0.0/earnings-calls"

    def __init__(self, cache_dir=None, api_key=None, exchange="NASDAQ"):
        if cache_dir is None:
            cache_dir = os.path.join(PROJECT_ROOT, "storage", "transcripts")
        self.cache_dir = cache_dir
        self.api_key = api_key if api_key is not None else os.getenv("ROIC_API_KEY")
        self.exchange = exchange
        self.last_fetch_date = None
        os.makedirs(self.cache_dir, exist_ok=True)

    def fetch_transcript(self, ticker, quarter):
        """
        quarter: 'YYYYQN' fiscal-quarter string, same convention as
        TranscriptFetcher. Returns a list of {speaker, content, source}
        dicts (Alpha-Vantage-compatible shape), or [] if unavailable (no key,
        quarter outside the free-tier window, no call yet, API error).
        Cached to the shared storage/transcripts/ path.
        """
        cache_file = os.path.join(self.cache_dir, f"{ticker}_{quarter}.json")
        if os.path.exists(cache_file):
            with open(cache_file, "r", encoding="utf-8") as f:
                return json.load(f)

        if not self.api_key:
            print(f"No ROIC_API_KEY set. Skipping {ticker} {quarter}.")
            return []

        year, q = quarter.split("Q")
        print(f"Fetching {ticker} {quarter} transcript from Roic AI...")
        time.sleep(12)  # free tier: 5 req/min
        response = requests.get(
            f"{self.API_URL}/{self.exchange}:{ticker}",
            params={"fiscal_year": int(year), "fiscal_quarter": int(q)},
            headers={"Authorization": f"Bearer {self.api_key}"},
        )
        data = response.json()
        self.last_fetch_date = data.get("date")

        turns = data.get("transcript")
        if not turns:
            error_msg = data.get("error") or data.get("message") or "no transcript available"
            print(f"Error fetching {ticker} {quarter} from Roic: {error_msg}")
            return []

        normalized = [
            {"speaker": t.get("speaker"), "content": t.get("text", ""), "source": "roic"}
            for t in turns
        ]
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(normalized, f)
        return normalized
