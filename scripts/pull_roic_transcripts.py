"""
Supplementary transcript pull via Roic AI - offloads the newest fiscal
quarters from Alpha Vantage's 25-req/day bottleneck. See
src/roic_transcript_fetcher.py's module docstring for the full rationale
and caveats (turn-shape normalization, av_sentiment gap, unverified
fiscal-quarter alignment for tickers with no earnings-surprise ground truth).

Requires ROIC_API_KEY in .env (free signup, no credit card:
https://www.roic.ai/pricing). Free tier: 5 req/min, most recent 8 fiscal
quarters per company only - NOT a full replacement for the AV pull, just a
faster source for the newest slice of the pinned 2020Q2-2026Q2 window.

Step 1 - verify before trusting: fetches ONE AMD quarter into an isolated
temp cache (never touching the real dataset) and checks its call date
against this project's own AV-derived reported_date
(storage/earnings_surprise/AMD.json, built in Step 1 of the earnings-surprise
pull). Hard-stops without pulling anything else if Roic's fiscal-quarter
labeling doesn't match AV's - never join on an unverified label.

Step 2 - only after verification passes: pulls the most recent 8 pinned
quarters for every ticker in the study universe (build_transcript_dataset.
TICKERS) into the SHARED storage/transcripts/ cache, so already-AV-cached
quarters are skipped for free and any quarter Roic fills here is
transparently skipped by tomorrow's AV pull.

CLI:
  C:\\ProgramData\\anaconda3\\python.exe scripts\\pull_roic_transcripts.py
"""
import os
import sys
import tempfile

from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv

load_dotenv()

from src.build_transcript_dataset import TICKERS, PINNED_QUARTERS
from src.earnings_surprise import build_surprise_table
from src.roic_transcript_fetcher import (RoicQuarterMismatchError,
                                          RoicTranscriptFetcher,
                                          verify_against_earnings_surprise)

VERIFICATION_TICKER = "AMD"
RECENT_QUARTERS = PINNED_QUARTERS[-8:]  # Roic free tier's actual depth


def _load_amd_surprise_rows():
    import json
    path = os.path.join("storage", "earnings_surprise", f"{VERIFICATION_TICKER}.json")
    if not os.path.exists(path):
        print(f"STOP: {path} not found - run scripts/pull_earnings_surprise.py "
              f"first (needed as ground truth to verify Roic's fiscal-quarter labels).")
        return None
    with open(path, encoding="utf-8") as f:
        payload = json.load(f)
    return build_surprise_table(payload).to_dict("records")


def main():
    if not os.getenv("ROIC_API_KEY"):
        print("STOP: ROIC_API_KEY not set. Sign up free at "
              "https://www.roic.ai/pricing (no credit card) and add "
              "ROIC_API_KEY=... to .env.")
        return 1

    surprise_rows = _load_amd_surprise_rows()
    if surprise_rows is None:
        return 1

    verify_quarter = surprise_rows[-1]["quarter"]
    with tempfile.TemporaryDirectory() as tmp_cache:
        probe = RoicTranscriptFetcher(cache_dir=tmp_cache)
        turns = probe.fetch_transcript(VERIFICATION_TICKER, verify_quarter)
        if not turns:
            print(f"STOP: could not fetch {VERIFICATION_TICKER} {verify_quarter} "
                  f"from Roic for verification. Nothing pulled - check ROIC_API_KEY "
                  f"and rerun.")
            return 1
        try:
            verify_against_earnings_surprise(verify_quarter, probe.last_fetch_date, surprise_rows)
        except RoicQuarterMismatchError as exc:
            print(f"HARD STOP - Roic's fiscal-quarter labeling does not match "
                  f"this project's own AV-derived ground truth: {exc}")
            print("Nothing else pulled. Do NOT proceed - report to Zander.")
            return 1

    print(f"Verification PASSED: Roic's {VERIFICATION_TICKER} {verify_quarter} call "
          f"({probe.last_fetch_date}) matches this project's own AV-derived "
          f"reported_date for that quarter.")

    fetcher = RoicTranscriptFetcher()  # real shared cache now
    progress = {}
    for ticker in TICKERS:
        filled = 0
        for quarter in RECENT_QUARTERS:
            if fetcher.fetch_transcript(ticker, quarter):
                filled += 1
        progress[ticker] = f"{filled}/{len(RECENT_QUARTERS)}"

    print("--- Roic supplementary pull progress (most recent 8 quarters only) ---")
    for ticker in TICKERS:
        print(f"{ticker}: {progress[ticker]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
