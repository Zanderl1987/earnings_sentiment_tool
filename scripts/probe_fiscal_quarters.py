"""Fiscal-quarter semantics probe - the gate before the 600-call expansion spend.

Spec: docs/superpowers/specs/2026-07-13-ticker-expansion-design.md, section
"Fiscal-quarter probe". Exactly 2 API calls (responses cache like any other
transcript, and 2024Q2 is inside the pinned window, so nothing is wasted).

Ground truth for interpreting the output:
  NVDA (FYE late Jan): FQ1 FY2025 call held 2024-05-22 (i.e. calendar Q2 2024);
                       its FQ2 FY2024 call was held 2023-08-23.
  ORCL (FYE May 31):   FQ4 FY2024 call held 2024-06-11 (i.e. calendar Q2 2024);
                       its FQ2 FY2024 call was held 2023-12-11.

Decision rule (read the printed opening turns):
  GO   - both non-empty and the text matches the calendar-Q2-2024 calls
         ("first quarter fiscal 2025" for NVDA, "fourth quarter"/"fiscal year
         2024" results for ORCL) -> labels are calendar; same pinned list for
         all 29 tickers.
  STOP - text matches the fiscal-Q2 calls instead ("second quarter fiscal
         2024" from Aug/Dec 2023) -> labels are fiscal; a per-ticker
         fiscal->calendar map is needed for quarter lists AND the label join.
         Do not proceed to Tasks 2-4; report to Zander.
  HALT - empty for either ticker -> these quarters certainly had calls, so
         the source is unreliable for fiscal-offset names; reassess before
         spending 600 calls. Do not proceed; report to Zander.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv

load_dotenv()

from src.nlp.transcript_fetcher import TranscriptFetcher

PROBES = [("NVDA", "2024Q2"), ("ORCL", "2024Q2")]


def main():
    fetcher = TranscriptFetcher()
    for ticker, quarter in PROBES:
        turns = fetcher.fetch_transcript(ticker, quarter)
        print(f"\n=== {ticker} {quarter}: {len(turns)} speaker turns ===")
        for turn in turns[:3]:
            content = (turn.get("content") or "")[:400]
            print(f"[{turn.get('speaker')} | {turn.get('title')}] {content}")


if __name__ == "__main__":
    main()
