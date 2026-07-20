"""
Pulls the earnings-call transcript dataset for the verbosity study (see
earnings_call_study.py and docs/superpowers/specs/2026-07-13-ticker-expansion-design.md).

Alpha Vantage's free tier caps at 25 requests/day PER IP (a second key does
not add quota - proven 2026-07-14/15) on a ROLLING 24-hour window, not a
midnight reset - manual pulls between automated runs collide with the next
day's quota. 29 tickers x 25 quarters = 725 files, so the dataset fills over
~24 days of daily automated runs (~2026-08-06).

TranscriptFetcher caches each successful pull to storage/transcripts/ and skips
anything already cached, so this script is safe to just rerun once a day - each
run picks up wherever the previous one left off, no manual bookkeeping needed.

The quarter window is PINNED (2020Q2..2026Q2), not rolling:
default_recent_quarters() shifts every calendar quarter (on Oct 1 it would start
requesting 2026Q3 and drop 2020Q2), silently changing the study window.

AV quarter labels are the company's FISCAL quarter (probe 2026-07-13, see spec):
for the 11 fiscal-offset tickers the same labels cover their own fiscal
2020Q2..2026Q2 (calendar span up to ~3 quarters earlier), and their 2026Q2
calls have already happened. For the 18 calendar-FY tickers 2026Q2 caches as
[] until those calls happen (~mid-Aug 2026): delete their *_2026Q2.json
empties then and let the daily task refill them.
"""
from src.transcript_fetcher import TranscriptFetcher

# Universe per the 2026-07-13 expansion spec. Order = pull priority: existing
# (fully cached, instant skip) -> event names -> controls, so partial data
# favors the names the study is about.
EXISTING_TICKERS = ["IEP", "PLTR", "AMD", "VRT", "VST"]
EVENT_TICKERS = [  # high-attention names, chosen by Zander 2026-07-13
    "GOOG", "META", "NFLX", "FDX", "NVDA", "MSFT", "INTC", "MU",
    "LMT", "NOC", "AMZN", "ARM", "LRCX", "GEV", "ORCL", "DELL",
]
CONTROL_TICKERS = [  # pre-registered selection criteria in the spec; chosen blind
    "PG", "KO", "CL", "KMB", "TXN", "ADP", "ACN", "GD",
]
TICKERS = EXISTING_TICKERS + EVENT_TICKERS + CONTROL_TICKERS

NUM_QUARTERS = 25
PINNED_QUARTERS = [
    "2020Q2", "2020Q3", "2020Q4",
    "2021Q1", "2021Q2", "2021Q3", "2021Q4",
    "2022Q1", "2022Q2", "2022Q3", "2022Q4",
    "2023Q1", "2023Q2", "2023Q3", "2023Q4",
    "2024Q1", "2024Q2", "2024Q3", "2024Q4",
    "2025Q1", "2025Q2", "2025Q3", "2025Q4",
    "2026Q1", "2026Q2",
]


def pull_all():
    fetcher = TranscriptFetcher()
    progress = {}

    for ticker in TICKERS:
        results = fetcher.fetch_recent_transcripts(ticker, PINNED_QUARTERS)
        progress[ticker] = f"{len(results)}/{NUM_QUARTERS}"
        if fetcher.exhausted:
            print("Daily Alpha Vantage quota exhausted - rerun this script "
                  "tomorrow to keep filling in the dataset.")
            break

    print("--- Transcript dataset progress ---")
    for ticker in TICKERS:
        print(f"{ticker}: {progress.get(ticker, '0/' + str(NUM_QUARTERS) + ' (not attempted yet)')}")
    return progress


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    pull_all()
