import json

import pytest

from src import roic_transcript_fetcher as rtf_module
from src.roic_transcript_fetcher import (RoicQuarterMismatchError,
                                          RoicTranscriptFetcher,
                                          verify_against_earnings_surprise)

ROIC_RESPONSE = {
    "symbol": "NASDAQ:AMD",
    "fiscal_year": 2026,
    "fiscal_quarter": 1,
    "date": "2026-01-27",
    "transcript": [
        {"speaker": "Operator", "text": "Good day, and welcome."},
        {"speaker": "Lisa Su", "text": "Thank you. Strong quarter across the board."},
    ],
}


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


def test_fetcher_cache_hit_never_touches_network(tmp_path, monkeypatch):
    cache = tmp_path / "AMD_2026Q1.json"
    cached_turns = [{"speaker": "Operator", "content": "Good day.", "source": "roic"}]
    cache.write_text(json.dumps(cached_turns), encoding="utf-8")

    def _no_network(*args, **kwargs):
        raise AssertionError("cache hit must not call requests.get")

    monkeypatch.setattr(rtf_module.requests, "get", _no_network)
    fetcher = RoicTranscriptFetcher(cache_dir=str(tmp_path), api_key="k1")
    assert fetcher.fetch_transcript("AMD", "2026Q1") == cached_turns


def test_fetcher_normalizes_turns_and_caches(tmp_path, monkeypatch):
    monkeypatch.setattr(rtf_module.time, "sleep", lambda s: None)
    monkeypatch.setattr(rtf_module.requests, "get",
                        lambda *a, **kw: _FakeResponse(ROIC_RESPONSE))

    fetcher = RoicTranscriptFetcher(cache_dir=str(tmp_path), api_key="k1")
    turns = fetcher.fetch_transcript("AMD", "2026Q1")

    # Normalized to Alpha Vantage's turn shape (speaker/content), not Roic's
    # raw speaker/text - analyze_transcript() reads "content", not "text".
    assert turns == [
        {"speaker": "Operator", "content": "Good day, and welcome.", "source": "roic"},
        {"speaker": "Lisa Su", "content": "Thank you. Strong quarter across the board.", "source": "roic"},
    ]
    cached = json.loads((tmp_path / "AMD_2026Q1.json").read_text(encoding="utf-8"))
    assert cached == turns


def test_fetcher_exposes_last_fetch_date_for_verification(tmp_path, monkeypatch):
    monkeypatch.setattr(rtf_module.time, "sleep", lambda s: None)
    monkeypatch.setattr(rtf_module.requests, "get",
                        lambda *a, **kw: _FakeResponse(ROIC_RESPONSE))

    fetcher = RoicTranscriptFetcher(cache_dir=str(tmp_path), api_key="k1")
    assert fetcher.last_fetch_date is None  # nothing fetched yet
    fetcher.fetch_transcript("AMD", "2026Q1")
    assert fetcher.last_fetch_date == "2026-01-27"


def test_fetcher_sends_fiscal_year_and_quarter_params(tmp_path, monkeypatch):
    monkeypatch.setattr(rtf_module.time, "sleep", lambda s: None)
    captured = {}

    def _capture(url, params=None, headers=None):
        captured["url"] = url
        captured["params"] = params
        captured["headers"] = headers
        return _FakeResponse(ROIC_RESPONSE)

    monkeypatch.setattr(rtf_module.requests, "get", _capture)
    fetcher = RoicTranscriptFetcher(cache_dir=str(tmp_path), api_key="secret-key")
    fetcher.fetch_transcript("AMD", "2026Q1")

    assert captured["url"].endswith("/earnings-calls/NASDAQ:AMD")
    assert captured["params"] == {"fiscal_year": 2026, "fiscal_quarter": 1}
    assert captured["headers"] == {"Authorization": "Bearer secret-key"}


def test_fetcher_returns_empty_list_and_caches_nothing_on_error(tmp_path, monkeypatch):
    monkeypatch.setattr(rtf_module.time, "sleep", lambda s: None)
    monkeypatch.setattr(rtf_module.requests, "get",
                        lambda *a, **kw: _FakeResponse({"error": "no transcript for this period"}))

    fetcher = RoicTranscriptFetcher(cache_dir=str(tmp_path), api_key="k1")
    assert fetcher.fetch_transcript("AMD", "2026Q1") == []
    assert not (tmp_path / "AMD_2026Q1.json").exists()


def test_fetcher_returns_empty_list_without_key_and_makes_no_network_call(tmp_path, monkeypatch):
    def _no_network(*args, **kwargs):
        raise AssertionError("no key means no network call")

    monkeypatch.setattr(rtf_module.requests, "get", _no_network)
    fetcher = RoicTranscriptFetcher(cache_dir=str(tmp_path), api_key=None)
    assert fetcher.fetch_transcript("AMD", "2026Q1") == []


def test_verify_against_earnings_surprise_passes_when_dates_agree():
    # surprise_table rows look like build_surprise_table()'s output.
    surprise_rows = [{"quarter": "2026Q1", "reported_date": "2026-01-27"}]
    verify_against_earnings_surprise("2026Q1", "2026-01-29", surprise_rows)  # within 5 days


def test_verify_against_earnings_surprise_raises_on_mismatch():
    surprise_rows = [{"quarter": "2026Q1", "reported_date": "2026-01-27"}]
    with pytest.raises(RoicQuarterMismatchError):
        verify_against_earnings_surprise("2026Q1", "2026-04-15", surprise_rows)


def test_verify_against_earnings_surprise_raises_when_quarter_not_in_surprise_table():
    surprise_rows = [{"quarter": "2025Q4", "reported_date": "2025-10-28"}]
    with pytest.raises(RoicQuarterMismatchError):
        verify_against_earnings_surprise("2026Q1", "2026-01-27", surprise_rows)
