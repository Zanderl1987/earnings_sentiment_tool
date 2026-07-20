# NLP Earnings Call Sentiment Tool

A financial NLP research pipeline studying whether corporate executives become more verbose or use more complex language when delivering bad news on earnings calls.

---

## Repository Architecture & Layout

```
earnings_sentiment_tool/
├── src/                       # NLP source modules
│   ├── transcript_fetcher.py      # Resumable Alpha Vantage EARNINGS_CALL_TRANSCRIPT fetcher/cacher
│   ├── build_transcript_dataset.py# Bulk dataset orchestrator (29 tickers x 25 quarters)
│   ├── sentiment_analyzer.py      # Loughran-McDonald & readability (Gunning-Fog) engine
│   ├── earnings_surprise.py       # Alpha Vantage earnings surprise downloader + fiscal-quarter derivation
│   ├── label_join.py              # Joins financial/market labels to NLP stats
│   └── earnings_call_study.py     # Sentiment vs complexity correlation study
│
├── scripts/                   # Automation wrappers & utility scripts
│   ├── daily_transcript_pull.ps1  # PowerShell wrapper for Windows Scheduled Task
│   ├── earnings_surprise_pull.ps1 # One-shot PS1 wrapper (stage-2 label join)
│   ├── probe_fiscal_quarters.py   # Validates fiscal-quarter alignment on Alpha Vantage
│   ├── pull_earnings_surprise.py  # Script to fetch surprise records + verify fiscal-quarter derivation
│   └── run_labeled_study.py       # Stage-2: joins transcripts with external surprises & CARs
│
├── tests/                     # Pytest suite
│   ├── test_earnings_surprise.py
│   ├── test_label_join.py
│   └── test_dataset_config.py
│
├── docs/
│   └── EARNINGS_STUDY.md
│
├── storage/                   # Local file caching (gitignored except logs/results)
│   ├── transcripts/           # {ticker}_{quarter}.json per Alpha Vantage call
│   ├── earnings_surprise/     # {ticker}.json from AV EARNINGS endpoint
│   ├── labels/                # {ticker}_labels.csv (stage-2 output)
│   └── study_labeled/         # {ticker}_panel.csv + correlation_summary.csv
│
├── .env                       # API Credentials (gitignored)
├── AUTOMATION.md              # Windows Scheduled Task documentation
├── CLAUDE.md                  # Developer runbook, commands, and environment setup
└── EXPERT_BRIEF.md            # Methodology guidelines and analytical pitfalls
```

---

## 🎙️ What This Tool Does

This module researches the linguistic patterns in corporate earnings calls, testing the hypothesis that executives use verbosity or complex language to obfuscate poor quarterly performance ("bad news").

### Key Research Features

*   **Lexicon-Based Sentiment Analysis**: Implements Loughran-McDonald (LM) financial dictionary categories (Positive, Negative, Uncertainty, Litigious) to calculate semantic metrics (e.g., `lm_net_sentiment`).
*   **Obfuscation/Complexity Metric**: Computes the **Gunning Fog Index** (combining average sentence length and the ratio of complex syllables) to measure readability.
*   **Circular-Avoidance Labeling**: Rather than using in-transcript sentiment to define "bad news" (which creates circular reasoning), the pipeline joins transcripts with external labels:
    1.  **Earnings Surprises**: Measured against consensus estimates (reportedEPS - estimatedEPS) via Alpha Vantage.
    2.  **Cumulative Abnormal Returns (CARs)**: Excess stock return over the market benchmark (SPY) in a narrow window around the call (via `financial-data-pipeline` cross-repo dependency).
*   **Fiscal Quarter Mapping**: Resolves the discrepancy where Alpha Vantage quarters are labeled by **fiscal** quarters (quarter=YYYYQN), which may map to different calendar dates depending on the ticker.
*   **Resumable Download pipeline**: Due to Alpha Vantage free tier constraints (25 requests/day total per IP), the fetcher caches successes to disk (`storage/transcripts/`) and handles rate-limits gracefully.

---

## Setup & Configuration

### Prerequisites
*   Windows OS (configured for PowerShell execution if utilizing automatic pulling scripts)
*   Anaconda or Python 3.10+
*   [financial-data-pipeline](https://github.com/Zanderl1987/financial-data-pipeline) repo on disk (for CARs in Stage 2)

### Configuration
1.  Clone this repository: `git clone https://github.com/Zanderl1987/earnings_sentiment_tool`
2.  Create a `.env` file in the root of the project:
    ```env
    ALPHA_VANTAGE_API_KEY=your_primary_key_here
    ALPHA_VANTAGE_API_KEY_2=your_secondary_key_here
    ```
3.  Optionally set `FDP_REPO_PATH` to the path of the financial-data-pipeline repo if not at the default location (`C:\Users\zande\PycharmProjects\financial-data-pipeline`).

---

## Execution & Usage

Always execute python scripts using the full path to your Python interpreter.

### Running the NLP Earnings Call Dataset Pull
To manually resume pulling transcripts (which skips cached files and respects the 25-request daily budget):
```powershell
C:\ProgramData\anaconda3\python.exe -m src.build_transcript_dataset
```

### Running the Earnings Call Sentiment Study (Stage 1)
```powershell
C:\ProgramData\anaconda3\python.exe -c "
from dotenv import load_dotenv; load_dotenv()
from src.earnings_call_study import run_earnings_call_study, print_study_results
df, corr = run_earnings_call_study('PLTR')
print_study_results('PLTR', df, corr)
"
```

### Running Stage 2: Pulling Earnings Surprises
```powershell
C:\ProgramData\anaconda3\python.exe scripts\pull_earnings_surprise.py
```

### Running Stage 2: Labeled Study (Cross-Repo Join)
```powershell
C:\ProgramData\anaconda3\python.exe scripts\run_labeled_study.py
```

---

## Automation & Task Scheduling

The project features a scheduled Windows Task to run the daily Alpha Vantage pull:

*   **Task Name**: `ClaudeAuto-TranscriptPull`
*   **Execution Time**: Daily at **10:30 AM**
*   **Action**: Runs `scripts\daily_transcript_pull.ps1`
*   **Output Monitoring**: Logs history to `storage\pull_log.txt`. If a daily run stalls (yields 0 new files), it generates `PULL_STALLED.txt` at the root directory.

Refer to [AUTOMATION.md](AUTOMATION.md) for full automation rules, troubleshooting, and instructions on how to query or trigger the task.

---

## Testing

Run unit tests via `pytest`:
```powershell
C:\ProgramData\anaconda3\python.exe -m pytest
```

---

## License & Contact
*   **Owner**: Zander
*   **Branch**: `master`
*   **Contact/Support**: Refer to `EXPERT_BRIEF.md` for methodology questions and analytical limitations before interpreting results.
