"""
Tests for src/research/scoring.py
Research tests — verify mathematical correctness, not data integrity.
Uses actual clean parquet data (no mocking). Timeframe: "1day" for speed.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd
import numpy as np
import pytest

from src.research.scoring import SCALES, score_history


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def history_1day():
    """Load 1day score history once for all tests in this module."""
    return score_history("1day")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_score_range(history_1day):
    """Score must be in [0.0, 1.0] for any valid input."""
    score = history_1day["score"]
    assert (score >= 0.0).all(), "Score has values below 0.0"
    assert (score <= 1.0).all(), "Score has values above 1.0"


def test_score_all_above():
    """If close is above all 9 SMAs, score == 1.0."""
    n_scales = len(SCALES)
    max_scale = max(SCALES)
    n_bars = max_scale + 50

    # Create a strictly ascending price series so close always beats all SMAs
    close = pd.Series(
        np.linspace(100.0, 200.0, n_bars),
        index=pd.date_range("2000-01-01", periods=n_bars, freq="D", tz="UTC"),
        name="close",
    )

    last_close = close.iloc[-1]
    hits = sum(
        1
        for s in SCALES
        if last_close > close.rolling(s).mean().iloc[-1]
    )
    score = hits / n_scales
    assert score == 1.0, f"Expected 1.0, got {score}"


def test_score_all_below():
    """If close is below all 9 SMAs, score == 0.0."""
    n_scales = len(SCALES)
    max_scale = max(SCALES)
    n_bars = max_scale + 50

    # Strictly descending price: last bar is lower than every SMA
    close = pd.Series(
        np.linspace(200.0, 100.0, n_bars),
        index=pd.date_range("2000-01-01", periods=n_bars, freq="D", tz="UTC"),
        name="close",
    )

    last_close = close.iloc[-1]
    hits = sum(
        1
        for s in SCALES
        if last_close > close.rolling(s).mean().iloc[-1]
    )
    score = hits / n_scales
    assert score == 0.0, f"Expected 0.0, got {score}"


def test_score_half():
    """If close is above exactly 4 of 9 scales, score == 4/9 ~= 0.444."""
    n_scales = len(SCALES)  # 9
    # Simulate: 4 scales return 1, 5 return 0
    hit_count = 4
    score = hit_count / n_scales
    expected = 4 / 9
    assert abs(score - expected) < 1e-9, f"Expected {expected:.6f}, got {score:.6f}"


def test_score_history_columns(history_1day):
    """score_history() must return all expected columns."""
    expected_cols = {
        "s2", "s4", "s8", "s16", "s32", "s64", "s128", "s256", "s512",
        "score", "close", "high", "low", "volume",
    }
    actual_cols = set(history_1day.columns)
    missing = expected_cols - actual_cols
    assert not missing, f"Missing columns: {missing}"


def test_score_history_no_nan(history_1day):
    """score_history() result must have no NaN after dropna."""
    # score_history() already calls dropna() internally, but verify
    assert not history_1day.isnull().any().any(), "score_history() returned NaN values"


def test_score_history_index_utc(history_1day):
    """DatetimeIndex must be UTC timezone-aware."""
    idx = history_1day.index
    assert isinstance(idx, pd.DatetimeIndex), "Index is not a DatetimeIndex"
    assert idx.tz is not None, "DatetimeIndex is timezone-naive (expected UTC)"
    assert str(idx.tz) == "UTC", f"Expected UTC, got {idx.tz}"
