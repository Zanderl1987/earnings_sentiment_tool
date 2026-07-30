import math

from src.earnings_call_study import run_earnings_call_study
from src.transcript_fetcher import TranscriptFetcher

# A few real-shaped word counts so correlations aren't degenerate.
GOOD_QUARTERS = {
    "2023Q1": [{"speaker": "CEO", "content": "Strong quarter, great results, record growth.", "sentiment": "0.8"}],
    "2023Q2": [{"speaker": "CEO", "content": "Weak quarter, decline, difficult conditions, weakness, unable to meet expectations badly.", "sentiment": "-0.6"}],
    "2023Q3": [{"speaker": "CEO", "content": "Solid improvement and progress, strengthened position overall.", "sentiment": "0.5"}],
    "2023Q4": [{"speaker": "CEO", "content": "Concerns about slowdown, weaker demand, risk of further decline ahead ongoing.", "sentiment": "-0.4"}],
}


def test_quarter_with_no_transcript_kept_as_nan_row_not_dropped(monkeypatch):
    # 2022Q4 (e.g. pre-IPO) never appears in fetch_recent_transcripts' result -
    # must still show up in the panel as a NaN row, not vanish.
    monkeypatch.setattr(TranscriptFetcher, "fetch_recent_transcripts",
                        lambda self, ticker, quarters: dict(GOOD_QUARTERS))

    quarters = ["2022Q4"] + list(GOOD_QUARTERS.keys())
    panel, _ = run_earnings_call_study("TEST", quarters=quarters)

    assert len(panel) == 5
    assert "2022Q4" in panel["quarter"].values
    missing_row = panel[panel["quarter"] == "2022Q4"].iloc[0]
    # Every metric NaN, including word_count/num_speaker_turns - "no
    # transcript exists" must not look like "management said zero words"
    # to a correlation's dropna() (real zeros wouldn't be dropped).
    assert math.isnan(missing_row["word_count"])
    assert math.isnan(missing_row["num_speaker_turns"])
    assert math.isnan(missing_row["fog_index"])
    assert math.isnan(missing_row["lm_net_sentiment"])


def test_correlation_computed_pairwise_despite_a_missing_quarter(monkeypatch):
    # Previously: ANY NaN in a sentiment column skipped that column's
    # correlation entirely for the whole ticker. Now: dropna per (sentiment,
    # verbosity) pair, so a single missing quarter shouldn't zero out every
    # av_sentiment/lm_net_sentiment correlation for tickers that have one gap.
    monkeypatch.setattr(TranscriptFetcher, "fetch_recent_transcripts",
                        lambda self, ticker, quarters: dict(GOOD_QUARTERS))

    quarters = ["2022Q4"] + list(GOOD_QUARTERS.keys())  # one missing quarter
    panel, correlation_results = run_earnings_call_study("TEST", quarters=quarters)

    assert correlation_results is not None
    # lm_net_sentiment is computed locally from text - present for the 4 real
    # quarters even though 2022Q4 is NaN - correlation must still be computed.
    assert "lm_net_sentiment_vs_word_count" in correlation_results
    result = correlation_results["lm_net_sentiment_vs_word_count"]
    assert not math.isnan(result["pearson_r"])


def test_all_quarters_missing_gives_all_nan_panel_not_a_crash(monkeypatch):
    monkeypatch.setattr(TranscriptFetcher, "fetch_recent_transcripts",
                        lambda self, ticker, quarters: {})

    panel, correlation_results = run_earnings_call_study("TEST", quarters=["2023Q1", "2023Q2", "2023Q3"])
    assert len(panel) == 3
    assert panel["word_count"].isna().all()
    # len(panel) >= 3 so correlation_results isn't None, but every pair has
    # zero non-NaN rows (all quarters empty) so nothing meets the n>=3 floor.
    assert correlation_results == {}
