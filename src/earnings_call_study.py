import pandas as pd
from scipy import stats

from src.transcript_fetcher import TranscriptFetcher
from src.sentiment_analyzer import EarningsCallAnalyzer


def default_recent_quarters(n=8, as_of=None):
    """Builds the last n 'YYYYQN' quarter strings ending at (but not including)
    the current quarter, since the most recent quarter's call likely hasn't
    happened yet."""
    as_of = as_of or pd.Timestamp.today()
    current_q = (as_of.month - 1) // 3 + 1
    quarters = []
    year, q = as_of.year, current_q
    for _ in range(n):
        q -= 1
        if q == 0:
            q, year = 4, year - 1
        quarters.append(f"{year}Q{q}")
    return list(reversed(quarters))


def run_earnings_call_study(ticker, quarters=None, num_quarters=8, speakers=None, lm_dict_path=None):
    """
    Pulls a ticker's recent earnings-call transcripts, scores each for
    verbosity (word count, Gunning Fog complexity) and sentiment (LM lexicon
    net sentiment + Alpha Vantage's own precomputed per-turn sentiment), then
    tests the hypothesis that executives get more verbose when the news is
    bad: a negative correlation between sentiment and verbosity across
    quarters.

    speakers: optional list of speaker names to restrict to (e.g. just the
    CEO/CFO's prepared remarks, excluding analyst Q&A) - the verbosity signal
    is about management's own choices, so mixing in analyst questions dilutes it.
    lm_dict_path: optional path to the real Loughran-McDonald Master
    Dictionary CSV; falls back to the built-in starter word list otherwise.

    Returns (per_quarter_df, correlation_results). correlation_results is
    None if fewer than 3 quarters had usable data (correlation is meaningless
    below that).
    """
    quarters = quarters or default_recent_quarters(num_quarters)

    fetcher = TranscriptFetcher()
    analyzer = EarningsCallAnalyzer()
    if lm_dict_path:
        analyzer.load_lm_dictionary(lm_dict_path)

    transcripts = fetcher.fetch_recent_transcripts(ticker, quarters)

    rows = []
    for quarter, entries in transcripts.items():
        metrics = analyzer.analyze_transcript(entries, speakers=speakers)
        if metrics["word_count"] == 0:
            continue
        metrics["quarter"] = quarter
        rows.append(metrics)

    per_quarter_df = pd.DataFrame(rows)
    if per_quarter_df.empty:
        return per_quarter_df, None
    per_quarter_df = per_quarter_df.sort_values("quarter").reset_index(drop=True)

    correlation_results = None
    if len(per_quarter_df) >= 3:
        correlation_results = {}
        for sentiment_col in ("lm_net_sentiment", "av_sentiment"):
            if per_quarter_df[sentiment_col].isna().any():
                continue
            for verbosity_col in ("word_count", "fog_index"):
                pearson_r, pearson_p = stats.pearsonr(
                    per_quarter_df[sentiment_col], per_quarter_df[verbosity_col]
                )
                spearman_r, spearman_p = stats.spearmanr(
                    per_quarter_df[sentiment_col], per_quarter_df[verbosity_col]
                )
                correlation_results[f"{sentiment_col}_vs_{verbosity_col}"] = {
                    "pearson_r": pearson_r, "pearson_p": pearson_p,
                    "spearman_r": spearman_r, "spearman_p": spearman_p,
                }

    return per_quarter_df, correlation_results


def print_study_results(ticker, per_quarter_df, correlation_results):
    print(f"--- Earnings Call Verbosity/Sentiment Study: {ticker} ---")
    if per_quarter_df.empty:
        print("No transcript data available (quota exhausted, invalid ticker, or no calls yet).")
        return
    print(per_quarter_df[[
        "quarter", "word_count", "fog_index", "lm_net_sentiment", "av_sentiment", "num_speaker_turns"
    ]].to_string(index=False))

    if correlation_results is None:
        print(f"Only {len(per_quarter_df)} usable quarter(s) - need at least 3 to test correlation.")
        return
    for label, r in correlation_results.items():
        direction = "more verbose when sentiment is worse" if r["pearson_r"] < 0 else "more verbose when sentiment is better"
        print(f"{label}: Pearson r={r['pearson_r']:.3f} (p={r['pearson_p']:.3f}), "
              f"Spearman rho={r['spearman_r']:.3f} (p={r['spearman_p']:.3f}) -> {direction}")
