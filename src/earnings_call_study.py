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

    Returns (per_quarter_df, correlation_results). per_quarter_df always has
    exactly one row per requested quarter - a quarter with no cached
    transcript gets NaN metrics rather than being omitted, so "no data" stays
    distinguishable from "never checked." correlation_results is None if
    fewer than 3 quarters were requested; otherwise a dict of whichever
    (sentiment, verbosity) pairs had at least 3 quarters with non-NaN values
    on BOTH sides (dropna is pairwise, so one ticker's single missing quarter
    doesn't disqualify every other quarter's real data).
    """
    quarters = quarters or default_recent_quarters(num_quarters)

    fetcher = TranscriptFetcher()
    analyzer = EarningsCallAnalyzer()
    if lm_dict_path:
        analyzer.load_lm_dictionary(lm_dict_path)

    transcripts = fetcher.fetch_recent_transcripts(ticker, quarters)

    rows = []
    for quarter in quarters:
        # A quarter with no cached transcript (pre-IPO, not yet called, quota
        # exhausted) must still appear as a row - silently omitting it would
        # make "no data" indistinguishable from "we never checked" or a bug
        # that lost real data. But analyze_transcript([]) returns word_count=0
        # and num_speaker_turns=0 (real zeros, not NaN) alongside fog_index/
        # lm_net_sentiment=None - a mix that would let "no transcript exists"
        # masquerade as "management said zero words" in any word_count-based
        # correlation (dropna() doesn't remove real zeros). So every metric is
        # forced to NaN for a quarter with no transcript at all, not just the
        # two analyze_text already treats that way.
        entries = transcripts.get(quarter, [])
        metrics = analyzer.analyze_transcript(entries, speakers=speakers)
        if not entries:
            metrics = {k: float("nan") for k in metrics}
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
            for verbosity_col in ("word_count", "fog_index"):
                # Pairwise dropna, not a whole-column skip: one NaN quarter
                # (no transcript) must not disqualify every other quarter's
                # real data from being correlated.
                pair = per_quarter_df[[sentiment_col, verbosity_col]].dropna()
                if len(pair) < 3:
                    continue
                pearson_r, pearson_p = stats.pearsonr(pair[sentiment_col], pair[verbosity_col])
                spearman_r, spearman_p = stats.spearmanr(pair[sentiment_col], pair[verbosity_col])
                correlation_results[f"{sentiment_col}_vs_{verbosity_col}"] = {
                    "pearson_r": pearson_r, "pearson_p": pearson_p,
                    "spearman_r": spearman_r, "spearman_p": spearman_p,
                }

    return per_quarter_df, correlation_results


def print_study_results(ticker, per_quarter_df, correlation_results):
    print(f"--- Earnings Call Verbosity/Sentiment Study: {ticker} ---")
    if per_quarter_df.empty:
        print("No quarters requested.")
        return
    if per_quarter_df["word_count"].isna().all():
        print("No transcript data available for any requested quarter "
              "(quota exhausted, invalid ticker, or no calls yet).")
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
