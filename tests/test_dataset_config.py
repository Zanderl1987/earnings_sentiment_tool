import pathlib
import re

from src.build_transcript_dataset import (CONTROL_TICKERS, EVENT_TICKERS,
                                              EXISTING_TICKERS, NUM_QUARTERS,
                                              PINNED_QUARTERS, TICKERS)

REPO = pathlib.Path(__file__).resolve().parents[1]


def _quarter_index(q):
    year, n = q.split("Q")
    return int(year) * 4 + int(n)


def test_pinned_quarters_window():
    assert len(PINNED_QUARTERS) == 25
    assert PINNED_QUARTERS[0] == "2020Q2"
    assert PINNED_QUARTERS[-1] == "2026Q2"
    assert all(re.fullmatch(r"20\d\dQ[1-4]", q) for q in PINNED_QUARTERS)


def test_pinned_quarters_consecutive_no_gaps():
    idxs = [_quarter_index(q) for q in PINNED_QUARTERS]
    assert idxs == list(range(idxs[0], idxs[0] + 25))


def test_universe_composition():
    assert len(EXISTING_TICKERS) == 5
    assert len(EVENT_TICKERS) == 16
    assert len(CONTROL_TICKERS) == 8
    assert TICKERS == EXISTING_TICKERS + EVENT_TICKERS + CONTROL_TICKERS
    assert len(set(TICKERS)) == 29          # no duplicates
    assert NUM_QUARTERS == len(PINNED_QUARTERS) == 25


def test_ps1_target_matches_universe():
    ps1 = (REPO / "scripts" / "daily_transcript_pull.ps1").read_text(encoding="utf-8")
    m = re.search(r"^\$target = (\d+)", ps1, re.MULTILINE)
    assert m, "no '$target = N' line found in daily_transcript_pull.ps1"
    assert int(m.group(1)) == len(TICKERS) * NUM_QUARTERS
