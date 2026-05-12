"""
Tests for src/research/detector.py
Uses actual clean parquet data via score_history("1day"). No mocking.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd
import numpy as np
import pytest

from src.research.score.scoring       import score_history
from src.research.detection.detector  import FractalDetector, PatternRecord


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def history_1day():
    return score_history("1day")


@pytest.fixture(scope="module")
def patterns_1day(history_1day):
    detector = FractalDetector("1day")
    return detector.run(history_1day)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_no_patterns_on_flat_data():
    """If score never exceeds TREND_THRESH, no patterns are detected."""
    # Build a minimal DataFrame where score is always 0.5 (consolidating)
    n = 600
    idx = pd.date_range("2010-01-01", periods=n, freq="D", tz="UTC")
    flat_data = pd.DataFrame(
        {
            "close": np.full(n, 100.0),
            "high":  np.full(n, 101.0),
            "low":   np.full(n, 99.0),
            "score": np.full(n, 0.5),   # always consolidating — never above TREND_THRESH
        },
        index=idx,
    )
    detector = FractalDetector("test")
    result = detector.run(flat_data)
    assert result == [], f"Expected no patterns on flat data, got {len(result)}"


def test_pattern_fields_complete(patterns_1day):
    """Every PatternRecord must have no None fields."""
    if not patterns_1day:
        pytest.skip("No patterns detected on 1day data — cannot test field completeness")

    for i, p in enumerate(patterns_1day):
        for field_name in PatternRecord.__dataclass_fields__:
            val = getattr(p, field_name)
            assert val is not None, (
                f"Pattern {i} has None field: {field_name}"
            )


def test_fib_depth_in_range(patterns_1day):
    """
    fib_retracement_depth for detected patterns should be >= 0.
    Values > 1.0 are valid (price went below move_low during consolidation)
    but we flag if any are negative, which would indicate a computation error.
    """
    if not patterns_1day:
        pytest.skip("No patterns detected on 1day data")

    for i, p in enumerate(patterns_1day):
        assert p.fib_retracement_depth >= 0.0, (
            f"Pattern {i} has negative fib_retracement_depth: {p.fib_retracement_depth}"
        )


def test_min_move_bars_respected(patterns_1day):
    """No pattern has move_duration_bars < MIN_MOVE_BARS."""
    if not patterns_1day:
        pytest.skip("No patterns detected on 1day data")

    min_bars = FractalDetector.MIN_MOVE_BARS
    for i, p in enumerate(patterns_1day):
        assert p.move_duration_bars >= min_bars, (
            f"Pattern {i} has move_duration_bars={p.move_duration_bars} "
            f"< MIN_MOVE_BARS={min_bars}"
        )


def test_min_consol_bars_respected(patterns_1day):
    """No pattern has consol_duration_bars < MIN_CONSOL_BARS."""
    if not patterns_1day:
        pytest.skip("No patterns detected on 1day data")

    min_bars = FractalDetector.MIN_CONSOL_BARS
    for i, p in enumerate(patterns_1day):
        assert p.consol_duration_bars >= min_bars, (
            f"Pattern {i} has consol_duration_bars={p.consol_duration_bars} "
            f"< MIN_CONSOL_BARS={min_bars}"
        )


def test_entry_score_above_threshold(patterns_1day):
    """entry_score for every pattern must be >= TREND_THRESH."""
    if not patterns_1day:
        pytest.skip("No patterns detected on 1day data")

    threshold = FractalDetector.TREND_THRESH
    for i, p in enumerate(patterns_1day):
        assert p.entry_score >= threshold, (
            f"Pattern {i} has entry_score={p.entry_score:.4f} "
            f"< TREND_THRESH={threshold}"
        )
