"""
Integrity tests that run against clean parquet data.
Verifies OHLC correctness, no NaNs, no duplicate index, monotonic order, UTC-aware timestamps.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
import pandas as pd

from src.utils.timeframes import CLEAN_DATA_DIR, TIMEFRAMES


def load_clean(tf: str) -> pd.DataFrame:
    path = CLEAN_DATA_DIR / f"NQ_{tf}_clean.parquet"
    if not path.exists():
        pytest.skip(f"Clean data not found for {tf}: {path}")
    return pd.read_parquet(path, engine="pyarrow")


@pytest.fixture(params=list(TIMEFRAMES.keys()))
def clean_df(request) -> tuple[str, pd.DataFrame]:
    tf = request.param
    return tf, load_clean(tf)


def test_ohlc_high_gte_low(clean_df):
    tf, df = clean_df
    violations = (df["high"] < df["low"]).sum()
    assert violations == 0, f"[{tf}] {violations} rows where high < low"


def test_close_within_high_low(clean_df):
    tf, df = clean_df
    above = (df["close"] > df["high"]).sum()
    below = (df["close"] < df["low"]).sum()
    assert above == 0, f"[{tf}] {above} rows where close > high"
    assert below == 0, f"[{tf}] {below} rows where close < low"


def test_open_within_high_low(clean_df):
    tf, df = clean_df
    above = (df["open"] > df["high"]).sum()
    below = (df["open"] < df["low"]).sum()
    assert above == 0, f"[{tf}] {above} rows where open > high"
    assert below == 0, f"[{tf}] {below} rows where open < low"


def test_no_nans_in_ohlcv(clean_df):
    tf, df = clean_df
    for col in ["open", "high", "low", "close", "volume"]:
        n = df[col].isna().sum()
        assert n == 0, f"[{tf}] column '{col}' has {n} NaN values"


def test_no_duplicate_index(clean_df):
    tf, df = clean_df
    dupes = df.index.duplicated().sum()
    assert dupes == 0, f"[{tf}] {dupes} duplicate index values"


def test_monotonically_increasing_index(clean_df):
    tf, df = clean_df
    assert df.index.is_monotonic_increasing, f"[{tf}] datetime index is not monotonically increasing"


def test_utc_timezone_aware_index(clean_df):
    tf, df = clean_df
    assert df.index.tzinfo is not None, f"[{tf}] index is timezone-naive"
    tz_name = str(df.index.tzinfo)
    assert "UTC" in tz_name, f"[{tf}] index timezone is not UTC: {tz_name}"


def test_bar_close_utc_matches_index(clean_df):
    tf, df = clean_df
    assert "bar_close_utc" in df.columns, f"[{tf}] missing 'bar_close_utc' column"
    mismatched = (df.index != df["bar_close_utc"]).sum()
    assert mismatched == 0, f"[{tf}] {mismatched} rows where bar_close_utc != index"
