# CLAUDE.md — earnings_sentiment_tool

NLP research tool for studying executive verbosity and sentiment in earnings call transcripts.
Owner: Zander. Branch: `master`.

## Environment

- Python: `C:\ProgramData\anaconda3\python.exe` — ALWAYS the full path; bare `python` on
  this machine is a broken MS Store stub.
- Secrets in `.env` at repo root (gitignored): `ALPHA_VANTAGE_API_KEY` + `_2`.
  Alpha Vantage free tier = 25 requests/day TOTAL - enforced per IP, so the
  second key does NOT double the budget (proven by 07-14/15 pull logs:
  both runs stopped at exactly +25). **Both keys rotated 2026-07-29** after
  an AV rate-limit error echoed them in plaintext into this session's
  transcript and `storage/pull_log.txt` (log scrubbed same day) - old keys
  no longer used anywhere.
- `ROIC_API_KEY` (optional, not yet set) - supplementary transcript source,
  see `scripts/pull_roic_transcripts.py`. Free signup, no credit card:
  https://www.roic.ai/pricing.

## Layout

```
earnings_sentiment_tool/
├── src/                       # All NLP source modules (was src/nlp/ in old combined repo)
│   ├── transcript_fetcher.py      # Alpha Vantage EARNINGS_CALL_TRANSCRIPT, caches to storage/transcripts/
│   ├── build_transcript_dataset.py# Resumable driver; 29 tickers, pinned 2020Q2–2026Q2 window
│   ├── earnings_call_study.py     # run_earnings_call_study() computes verbosity/sentiment correlation
│   ├── sentiment_analyzer.py      # Loughran-McDonald & readability (Gunning-Fog) engine
│   ├── earnings_surprise.py       # Alpha Vantage EARNINGS surprise downloader + fiscal-quarter derivation
│   ├── roic_transcript_fetcher.py # Supplementary transcript source (Roic AI) - see Active project below
│   └── label_join.py              # Joins financial/market labels to NLP stats
│
├── scripts/
│   ├── daily_transcript_pull.ps1  # PowerShell wrapper for Windows Scheduled Task
│   ├── earnings_surprise_pull.ps1 # One-shot PS1 wrapper for surprise data pull
│   ├── probe_fiscal_quarters.py   # Validates fiscal-quarter alignment on AV
│   ├── pull_earnings_surprise.py  # Script to fetch surprise records + verify derivation
│   ├── pull_roic_transcripts.py   # Supplementary transcript pull via Roic AI (not yet run - needs ROIC_API_KEY)
│   └── run_labeled_study.py       # Stage-2: combines transcripts with market returns (external labels)
│
├── tests/
│   ├── test_earnings_surprise.py
│   ├── test_roic_transcript_fetcher.py
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

**2026-07-29 status: Stage 2 Step 1 (earnings-surprise pull) is COMPLETE.** All 7
tickers built (NVDA/ORCL verification passed 4/4 against probe ground truth; IEP/PLTR/
AMD/VRT/VST all have surprise tables). Found and fixed a real bug along the way: IEP's
AV `annualEarnings` is missing FY2000 and FY2005 entirely (a genuine gap in AV's own
data), and `derive_fiscal_quarters()` used to hard-stop the ENTIRE 111-quarter ticker
over just the 6 quarters that fell in those two gaps - including the perfectly good
2020-2026 window this project actually needs. Fixed to skip only the individually
unresolvable quarters (with a warning), not the whole ticker; duplicate-label collisions
still hard-stop (that's a different, more dangerous ambiguity). Verified against the
real cached `IEP.json`: 105/111 quarters recovered, full 2020-2026 window intact
including the 2023 post-Hindenburg quarters. 22 tests in `test_earnings_surprise.py`,
all passing. **Next: Step 2 (`scripts/run_labeled_study.py`) can now run - zero quota,
cache-only.**

Transcript cache at 350/725 as of 2026-07-29 (16 of 29 tickers - LMT, NOC, AMZN, ARM,
LRCX, GEV, ORCL, DELL, PG, KO, CL, KMB, TXN, ADP, ACN, GD - not yet started; ETA
unchanged, ~2026-08-06 at 25/day). `PULL_STALLED.txt` is present as of this writing but
already explained, not a new problem: the 2026-07-29 10:30 automated run used the
OLD (pre-rotation) Alpha Vantage keys and hit their exhausted quota; the keys were
rotated later that same afternoon (see Environment section). The new keys already spent
6 calls that afternoon on the earnings-surprise pull above, so the 2026-07-30 10:30 run
will have ~19/25 headroom rather than a fresh 25 (rolling-24h window) - expect a
partial, not a full, day's fill; nothing to fix, just don't be surprised by a lower
`+N` in `pull_log.txt`.

**Built, not yet run: a supplementary Roic AI transcript source**
(`src/roic_transcript_fetcher.py` + `scripts/pull_roic_transcripts.py`, 9 tests passing)
to offload the newest quarters from Alpha Vantage's 25/day bottleneck for the 16
untouched tickers. Roic's free tier (signup at roic.ai/pricing, no credit card) covers
only the most recent 8 fiscal quarters per company at 5 req/min - not a full
replacement, just a faster source for the newest slice of the pinned window. The script
verifies Roic's fiscal-quarter labeling against this project's own AV-derived
`reported_date` (AMD, since it has clean ground truth from Step 1) before pulling
anything else - hard-stops if they disagree, exactly the same "never join on an
unverified label" lesson AV's own fiscal-quarter probe already taught this project.
Roic turns are normalized from `{speaker, text}` to Alpha Vantage's `{speaker, content}`
shape (tagged `source: "roic"`) so `earnings_call_study.py` reads them correctly with no
changes there; Roic transcripts have no per-turn sentiment score, so `av_sentiment`
correlations will skip any ticker that mixes both sources (`lm_net_sentiment`/
`fog_index` are unaffected). **Blocked on the user signing up for a free `ROIC_API_KEY`**
- once set in `.env`, run `scripts/pull_roic_transcripts.py`. One unverified assumption
worth checking on the first live run: the fetcher defaults every ticker to
`NASDAQ:{ticker}`, but several of the 29 tickers are NYSE-listed - not hardcoded from
memory to avoid asserting wrong exchange facts, so some may come back empty on a wrong
exchange prefix rather than genuinely unavailable.

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
1. ~~`scripts/pull_earnings_surprise.py` - 7 AV calls, quota-gated~~ **DONE 2026-07-29**
   (see status above - all 7 tickers built, IEP derivation bug fixed).
2. `scripts/run_labeled_study.py` - zero quota, cache-only, produces outputs in storage/labels/ and storage/study_labeled/.
   Requires: financial-data-pipeline repo at `C:\Users\zande\PycharmProjects\financial-data-pipeline`
   (set `FDP_REPO_PATH` env var to override). **Not yet run.**

## Cross-repo dependency

`src/label_join.py` calls `event_backtest.event_study()` from the **financial-data-pipeline**
repo for Cumulative Abnormal Returns (CARs). That repo must be on disk and pointed to via
`FDP_REPO_PATH` env var (default: `C:\Users\zande\PycharmProjects\financial-data-pipeline`).
