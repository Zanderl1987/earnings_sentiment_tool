"""One-time AV EARNINGS pull + LIVE fiscal-derivation verification.
Spec: docs/superpowers/specs/2026-07-13-label-join-design.md, data flow
step 1. Verification tickers (NVDA, ORCL) are pulled FIRST: if the
derived labels don't reproduce the probe's ground truth, this script
hard-stops before spending the other 5 calls.

QUOTA - 7 calls; the shared AV budget is 25/day per IP and the
ClaudeAuto-TranscriptPull task consumes whatever is left of it
(rolling-24h window - never run this mid-day). Run it in the ~10:05 gap:
after the previous day's calls roll off the window, and before the
transcript task fires at 10:30. Nothing else is needed - that task then
takes the remaining ~18 calls on its own.

  C:\\ProgramData\\anaconda3\\python.exe scripts\\pull_earnings_surprise.py

Do NOT disable the transcript task to make room (the earlier approach,
superseded 2026-07-15): a disabled task that never gets re-enabled
silently costs a day of fill, and re-timing it mid-morning makes Windows
skip that day's run entirely. See AUTOMATION.md.

`scripts\\earnings_surprise_pull.ps1` is the unattended wrapper around
this script (logging, key scrubbing, failure flag file).

Safe to rerun: cached tickers are skipped at zero quota cost. If AV
prints quota errors, scrub any copied log text - AV error messages can
echo the API key.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv

load_dotenv()

from src.earnings_surprise import (DERIVATION_GROUND_TRUTH,
                                       EarningsSurpriseFetcher,
                                       FiscalDerivationError,
                                       build_surprise_table,
                                       verify_derivation)

VERIFICATION_TICKERS = ["NVDA", "ORCL"]
STUDY_TICKERS = ["IEP", "PLTR", "AMD", "VRT", "VST"]


def main():
    fetcher = EarningsSurpriseFetcher()

    tables = {}
    try:
        for ticker in VERIFICATION_TICKERS:
            payload = fetcher.fetch_earnings(ticker)
            if payload is None:
                print(f"STOP: could not fetch {ticker} EARNINGS (quota/key). "
                      "Nothing verified - rerun when quota allows.")
                return 1
            table = build_surprise_table(payload)
            tables[ticker] = table
            print(f"{ticker}: {len(table)} quarters, "
                  f"{table['fiscal_date_ending'].iloc[0]} .. {table['fiscal_date_ending'].iloc[-1]}")

        for ticker in VERIFICATION_TICKERS:
            truth = [(d, q) for t, d, q in DERIVATION_GROUND_TRUTH if t == ticker]
            verify_derivation(tables[ticker], truth)
    except FiscalDerivationError as exc:
        print(f"HARD STOP - derivation failed live verification: {exc}")
        print("Do NOT proceed to the label join. Report to Zander "
              "(spec: error handling).")
        return 1
    print("Derivation VERIFIED against probe ground truth (4/4 checks).")

    for ticker in STUDY_TICKERS:
        payload = fetcher.fetch_earnings(ticker)
        if payload is None:
            print(f"{ticker}: not fetched (quota) - rerun this script "
                  "another morning; cached tickers are skipped.")
            continue
        try:
            table = build_surprise_table(payload)
        except FiscalDerivationError as exc:
            print(f"{ticker}: fiscal-quarter derivation failed: {exc}. "
                  "Payload is still cached (no quota spent) - investigate "
                  "offline; skipping table build for this ticker.")
            continue
        with_est = int(table["surprise_pct"].notna().sum())
        print(f"{ticker}: {len(table)} quarters cached, "
              f"{with_est} with surprise estimates.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
