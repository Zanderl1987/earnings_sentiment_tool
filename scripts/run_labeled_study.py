"""Stage-2 labeled rerun: external labels (surprise + CARs) replace the
in-transcript sentiment labels. Zero AV quota - reads only caches; skips
any ticker whose EARNINGS cache is missing rather than fetching.

Prerequisites: scripts/pull_earnings_surprise.py has run (and VERIFIED),
and IEP/VRT/VST are backfilled in financial-data-pipeline's tiingo_prices.

Outputs: storage/labels/{ticker}_labels.csv (labels only),
storage/study_labeled/{ticker}_panel.csv (verbosity panel + labels),
storage/study_labeled/correlation_summary.csv.

Interpretation: hypothesis says verbosity RISES on bad news, and both
labels are higher-is-better-news, so the predicted correlation sign is
NEGATIVE (same convention as the first pass). IEP is a narrative case
study - report its row, never pool it (spec / EXPERT_BRIEF).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv

load_dotenv()

import pandas as pd
from scipy import stats

from src.build_transcript_dataset import EXISTING_TICKERS, PINNED_QUARTERS
from src.earnings_call_study import run_earnings_call_study
from src.earnings_surprise import (EarningsSurpriseFetcher,
                                       FiscalDerivationError,
                                       build_surprise_table)
from src.label_join import CAR_HORIZONS, build_labels, compute_cars

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LABELS_DIR = PROJECT_ROOT / "storage" / "labels"
STUDY_DIR = PROJECT_ROOT / "storage" / "study_labeled"
TRANSCRIPTS_DIR = PROJECT_ROOT / "storage" / "transcripts"

LABEL_COLS = ("surprise_pct", "car_1", "car_3", "car_5", "car_10", "car_21")
VERBOSITY_COLS = ("word_count", "fog_index", "num_speaker_turns")


def main():
    LABELS_DIR.mkdir(parents=True, exist_ok=True)
    STUDY_DIR.mkdir(parents=True, exist_ok=True)
    fetcher = EarningsSurpriseFetcher()

    panels, surprises, event_frames = {}, {}, []
    for ticker in EXISTING_TICKERS:
        cache_file = Path(fetcher.cache_dir) / f"{ticker}.json"
        if not cache_file.exists():
            print(f"{ticker}: no EARNINGS cache - run "
                  "scripts/pull_earnings_surprise.py first. Skipping.")
            continue
        missing_transcripts = [q for q in PINNED_QUARTERS
                                if not (TRANSCRIPTS_DIR / f"{ticker}_{q}.json").exists()]
        if missing_transcripts:
            print(f"{ticker}: {len(missing_transcripts)} of {len(PINNED_QUARTERS)} "
                  "pinned-quarter transcript caches missing - running the study "
                  "would spend live Alpha Vantage quota. Skipping.")
            continue
        payload = fetcher.fetch_earnings(ticker)   # guaranteed cache hit
        try:
            table = build_surprise_table(payload)
        except FiscalDerivationError as exc:
            print(f"{ticker}: fiscal-quarter derivation failed: {exc}. "
                  "Skipping - a ticker whose labels cannot be derived must "
                  "not reach the join.")
            continue
        panel, _ = run_earnings_call_study(ticker, quarters=PINNED_QUARTERS)   # guaranteed cache hit, all quarters cached above
        # panel always has one row per pinned quarter now (empty quarters get
        # NaN metrics, not omitted) - "no usable data" means every row is NaN,
        # not that the frame itself is empty.
        if panel["word_count"].isna().all():
            print(f"{ticker}: no usable transcripts in cache. Skipping.")
            continue
        panels[ticker] = panel
        surprises[ticker] = table
        ev = table[table["quarter"].isin(panel["quarter"])].dropna(subset=["reported_date"])
        if not ev.empty:
            event_frames.append(pd.DataFrame({
                "symbol": ticker, "date": ev["reported_date"],
                "quarter": ev["quarter"],
            }))

    if not event_frames:
        print("No events to study - nothing to do.")
        return 1

    events = pd.concat(event_frames, ignore_index=True)
    print(f"Event study: {len(events)} events, "
          f"{events['symbol'].nunique()} tickers, window (-1, 21), "
          "benchmark SPY, entry_lag 0...")
    cars = compute_cars(events)
    print(f"CARs computed for {len(cars)}/{len(events)} events "
          "(the rest lacked price coverage -> NaN labels).")

    label_out_cols = (["quarter", "reported_date", "surprise_pct"]
                      + [f"car_{h}" for h in CAR_HORIZONS])
    summary_rows = []
    for ticker, panel in panels.items():
        t_cars = cars[cars["symbol"] == ticker]
        labeled = build_labels(panel, surprises[ticker], t_cars)
        labeled[label_out_cols].to_csv(LABELS_DIR / f"{ticker}_labels.csv", index=False)
        labeled.to_csv(STUDY_DIR / f"{ticker}_panel.csv", index=False)
        for label_col in LABEL_COLS:
            for verb_col in VERBOSITY_COLS:
                pair = labeled[[label_col, verb_col]].dropna()
                row = {"ticker": ticker, "label": label_col,
                       "metric": verb_col, "n": len(pair)}
                if len(pair) >= 3:
                    pr, pp = stats.pearsonr(pair[label_col], pair[verb_col])
                    sr, sp = stats.spearmanr(pair[label_col], pair[verb_col])
                    row.update(pearson_r=round(pr, 4), pearson_p=round(pp, 4),
                               spearman_rho=round(sr, 4), spearman_p=round(sp, 4))
                summary_rows.append(row)

    summary = pd.DataFrame(summary_rows, columns=[
        "ticker", "label", "metric", "n",
        "pearson_r", "pearson_p", "spearman_rho", "spearman_p",
    ])
    summary.to_csv(STUDY_DIR / "correlation_summary.csv", index=False)
    print(summary.to_string(index=False))

    n_tested = int((summary["n"] >= 3).sum())
    bonferroni = 0.05 / n_tested if n_tested > 0 else float("nan")
    print("=" * 70)
    print("MULTIPLE-COMPARISON CAVEAT")
    print("=" * 70)
    print(f"{n_tested} (ticker, label, metric) groups were actually tested "
          "(n >= 3; rows with n < 3 have no correlation computed).")
    print(f"Bonferroni threshold: 0.05 / {n_tested} = {bonferroni:.6f}")
    print("Pearson and Spearman are two tests OF THE SAME PAIR and are not "
          "independent, so this threshold is a conservative floor, not an "
          "exact correction.")
    print("NO primary (label, metric) pair was pre-registered for this "
          "run - individual p<0.05 hits are expected by chance alone and "
          "should be treated as hypothesis-generating, not confirmatory.")
    print("=" * 70)
    print("Reminder: predicted sign is NEGATIVE; IEP is a case study - "
          "never pool it.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
