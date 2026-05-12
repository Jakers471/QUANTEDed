"""
Leakage tests for the data loader.
Verifies that no future data leaks through edge cases in as_of filtering.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
import pandas as pd

from src.loader.loader import get_bars, get_last_closed_bar, get_multi_tf
from src.utils.timeframes import CLEAN_DATA_DIR, TIMEFRAMES


def _first_available_tf() -> str:
    for tf in TIMEFRAMES:
        path = CLEAN_DATA_DIR / f"NQ_{tf}_clean.parquet"
        if path.exists():
            return tf
    pytest.skip("No clean data available — run src/pipeline/clean.py first")


def _load_index(tf: str) -> pd.DatetimeIndex:
    path = CLEAN_DATA_DIR / f"NQ_{tf}_clean.parquet"
    if not path.exists():
        pytest.skip(f"Clean data not found for {tf}")
    df = pd.read_parquet(path, engine="pyarrow", columns=["bar_close_utc"])
    return pd.DatetimeIndex(df["bar_close_utc"])


@pytest.fixture(scope="module")
def known_tf_and_timestamps():
    tf = _first_available_tf()
    index = _load_index(tf)
    # Use a bar from the middle of the dataset to avoid edge cases
    mid = len(index) // 2
    return tf, index[mid]


def test_exact_timestamp_bar_excluded(known_tf_and_timestamps):
    tf, ts = known_tf_and_timestamps
    bars = get_bars(tf, ts)
    assert ts not in bars.index, (
        f"Bar at {ts} was returned when as_of == bar close time (should be excluded)"
    )


def test_one_microsecond_after_bar_excluded(known_tf_and_timestamps):
    tf, ts = known_tf_and_timestamps
    as_of = ts + pd.Timedelta(microseconds=1)
    bars = get_bars(tf, as_of)
    # The bar at ts should now be included (close < as_of)
    assert ts in bars.index, (
        f"Bar at {ts} not returned when as_of is 1µs after bar close"
    )
    # But no bar at as_of itself exists or is returned forming
    future = bars[bars.index > ts]
    assert future.empty, "Bars after ts were returned"


def test_one_microsecond_before_bar_excluded(known_tf_and_timestamps):
    tf, ts = known_tf_and_timestamps
    as_of = ts - pd.Timedelta(microseconds=1)
    bars = get_bars(tf, as_of)
    assert ts not in bars.index, (
        f"Bar at {ts} returned when as_of is 1µs before bar close"
    )


def test_multi_tf_no_straddling_bar(known_tf_and_timestamps):
    tf_1min = "1min"
    path = CLEAN_DATA_DIR / f"NQ_{tf_1min}_clean.parquet"
    if not path.exists():
        pytest.skip("1min clean data not available")

    tf_60min = "60min"
    path_60 = CLEAN_DATA_DIR / f"NQ_{tf_60min}_clean.parquet"
    if not path_60.exists():
        pytest.skip("60min clean data not available")

    index_1min = _load_index(tf_1min)
    mid_1min = index_1min[len(index_1min) // 2]

    result = get_multi_tf([tf_1min, tf_60min], mid_1min)

    last_1min = result[tf_1min]
    last_60min = result[tf_60min]

    # The 60min bar returned must have closed strictly before mid_1min
    assert last_60min["bar_close_utc"] < mid_1min, (
        f"60min bar close {last_60min['bar_close_utc']} >= as_of {mid_1min}"
    )


def test_naive_datetime_raises(known_tf_and_timestamps):
    tf, _ = known_tf_and_timestamps
    naive = pd.Timestamp("2020-01-01 12:00:00")  # no tz
    with pytest.raises(ValueError, match="timezone-aware"):
        get_bars(tf, naive)


def test_naive_datetime_get_last_closed_bar_raises(known_tf_and_timestamps):
    tf, _ = known_tf_and_timestamps
    naive = pd.Timestamp("2020-01-01 12:00:00")
    with pytest.raises(ValueError, match="timezone-aware"):
        get_last_closed_bar(tf, naive)


def test_unknown_timeframe_raises():
    as_of = pd.Timestamp("2020-01-01 12:00:00", tz="UTC")
    with pytest.raises((ValueError, FileNotFoundError)):
        get_bars("99min", as_of)


def test_no_bars_before_as_of_raises():
    tf = _first_available_tf()
    # Use a timestamp far before any data
    ancient = pd.Timestamp("1900-01-01 00:00:00", tz="UTC")
    with pytest.raises(LookupError):
        get_last_closed_bar(tf, ancient)
