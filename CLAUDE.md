# CLAUDE.md — earnings_sentiment_tool

NLP research tool for studying executive verbosity and sentiment in earnings call transcripts.
Owner: Zander. Branch: `master`.

## Environment

- Python: `C:\ProgramData\anaconda3\python.exe` — ALWAYS the full path; bare `python` on
  this machine is a broken MS Store stub.
- Secrets in `.env` at repo root (gitignored): `ALPHA_VANTAGE_API_KEY` + `_2`.
  Alpha Vantage free tier = 25 requests/day TOTAL - enforced per IP, so the
  second key does NOT double the budget (proven by 07-14/15 pull logs:
  both runs stopped at exactly +25).

## Layout

```
earnings_sentiment_tool/
├── src/                       # All NLP source modules (was src/nlp/ in old combined repo)
│   ├── transcript_fetcher.py      # Alpha Vantage EARNINGS_CALL_TRANSCRIPT, caches to storage/transcripts/
│   ├── build_transcript_dataset.py# Resumable driver; 29 tickers, pinned 2020Q2–2026Q2 window
│   ├── earnings_call_study.py     # run_earnings_call_study() computes verbosity/sentiment correlation
│   ├── sentiment_analyzer.py      # Loughran-McDonald & readability (Gunning-Fog) engine
│   ├── earnings_surprise.py       # Alpha Vantage EARNINGS surprise downloader + fiscal-quarter derivation
│   └── label_join.py              # Joins financial/market labels to NLP stats
│
├── scripts/
│   ├── daily_transcript_pull.ps1  # PowerShell wrapper for Windows Scheduled Task
│   ├── earnings_surprise_pull.ps1 # One-shot PS1 wrapper for surprise data pull
│   ├── probe_fiscal_quarters.py   # Validates fiscal-quarter alignment on AV
│   ├── pull_earnings_surprise.py  # Script to fetch surprise records + verify derivation
│   └── run_labeled_study.py       # Stage-2: combines transcripts with market returns (external labels)
│
├── tests/
│   ├── test_earnings_surprise.py
│   ├── test_label_join.py
│   └── test_dataset_config.py
│
├── docs/
│   └── EARNINGS_STUDY.md
│
├── storage/                   # Local file caching (gitignored except logs/results)
│   ├── transcripts/           # {ticker}_{quarter}.json per AV call
│   ├── earnings_surprise/     # {ticker}.json from AV EARNINGS endpoint
│   ├── labels/                # {ticker}_labels.csv (output of run_labeled_study.py)
│   └── study_labeled/         # {ticker}_panel.csv and correlation_summary.csv
│
├── .env                       # API Credentials (gitignored)
├── AUTOMATION.md              # Windows Scheduled Task documentation
├── CLAUDE.md                  # This file
└── EXPERT_BRIEF.md            # Methodology guidelines and analytical pitfalls
```

## Active project: earnings transcript dataset (2026-07)

Hypothesis: executives get more verbose/complex when delivering bad news. Universe
EXPANDED 2026-07-13: 29 tickers x 25 pinned quarters (2020Q2–2026Q2) = 725 transcripts.
Original 5 (IEP anchor case, PLTR, AMD, VRT, VST) fully cached; 16 event names + 8 pre-registered
controls fill via the daily task at 25 files/day through ~2026-08-06.

**2026-07-26 status:** cache at 302/725. The daily task was silently broken
2026-07-20→2026-07-25 by the split out of `custom_index_tool` (`daily_transcript_pull.ps1`
still called the pre-split `-m src.nlp.build_transcript_dataset`; fixed to
`-m src.build_transcript_dataset`, commit `0d7df54`) — `PULL_STALLED.txt` misleadingly
blamed quota the whole time. Confirmed fixed: the 2026-07-26 10:30 run added +25 cleanly.
Stage 2 (`scripts/pull_earnings_surprise.py`) is still stuck at 1/7 (only NVDA, from the
2026-07-19 run that hard-stopped before the split) — needs a rerun in the ~10:05 morning
gap per the script's own docstring ("never run this mid-day"); attempted mid-session on
2026-07-26 at 17:16 but skipped since that day's 25-call quota was already spent by the
10:30 task. Next actionable morning: run `scripts/pull_earnings_surprise.py` before 10:30.

**AV quarter labels are FISCAL, not calendar** (probed 2026-07-13,
`scripts/probe_fiscal_quarters.py`) — 11 tickers are fiscal-offset; uniform label
list kept by design, but any label join MUST map (ticker, fiscal quarter) → real
report date first. ~Mid-Aug 2026: delete the CALENDAR-FY tickers' empty
`*_2026Q2.json` caches so the task refills them.

**Resume daily** until `storage/transcripts/` holds all 725 files:

```
C:\ProgramData\anaconda3\python.exe -m src.build_transcript_dataset
```

Fully resumable — just rerun; it skips cached files and stops at the daily rate limit.

The daily pull is AUTOMATED (Windows task `ClaudeAuto-TranscriptPull`, 10:30 AM — see
`AUTOMATION.md`). If `PULL_STALLED.txt` exists at repo root, yesterday's run produced no
new files — check `storage\pull_log.txt`. NO manual AV pulls between automated runs
(quota window is rolling-24h, not midnight reset).

**Before analyzing the dataset, read `EXPERT_BRIEF.md`** — methodology decisions (how to
define "bad news" non-circularly, prepared-remarks vs Q&A split, IEP-as-case-study) and
data traps (per-ticker quarter availability, quota discipline).

Stage 2 (external labels): implemented in `scripts/run_labeled_study.py`.
Execution:
1. `scripts/pull_earnings_surprise.py` - 7 AV calls, quota-gated, run on a morning per AUTOMATION.md.
2. `scripts/run_labeled_study.py` - zero quota, cache-only, produces outputs in storage/labels/ and storage/study_labeled/.
   Requires: financial-data-pipeline repo at `C:\Users\zande\PycharmProjects\financial-data-pipeline`
   (set `FDP_REPO_PATH` env var to override).

## Cross-repo dependency

`src/label_join.py` calls `event_backtest.event_study()` from the **financial-data-pipeline**
repo for Cumulative Abnormal Returns (CARs). That repo must be on disk and pointed to via
`FDP_REPO_PATH` env var (default: `C:\Users\zande\PycharmProjects\financial-data-pipeline`).
