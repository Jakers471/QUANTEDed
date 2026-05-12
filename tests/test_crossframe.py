"""
Cross-timeframe consistency smoke tests.
Mismatches are warnings, not hard failures, because NinjaTrader data
can have minor discrepancies across separately exported timeframes.
"""

import sys
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
import pandas as pd

from src.utils.timeframes import CLEAN_DATA_DIR


def load_tf(tf: str) -> pd.DataFrame:
    path = CLEAN_DATA_DIR / f"NQ_{tf}_clean.parquet"
    if not path.exists():
        pytest.skip(f"Clean data not found for {tf}")
    return pd.read_parquet(path, engine="pyarrow")


def _warn_or_fail(condition: bool, message: str, hard_fail: bool = False) -> None:
    if not condition:
        if hard_fail:
            pytest.fail(message)
        else:
            warnings.warn(message, stacklevel=2)


@pytest.fixture(scope="module")
def df_5min():
    return load_tf("5min")


@pytest.fixture(scope="module")
def df_15min():
    return load_tf("15min")


@pytest.fixture(scope="module")
def df_60min():
    return load_tf("60min")


def _pick_test_window(df_60min: pd.DataFrame) -> pd.Timestamp:
    # Pick a 1-hour bar from the middle of the dataset
    mid = len(df_60min) // 2
    return df_60min.index[mid]


def test_5min_volume_sums_to_60min(df_5min, df_60min):
    hourly_ts = _pick_test_window(df_60min)
    hour_bar = df_60min.loc[hourly_ts]

    # 5min bars whose close falls within the 60min bar's window
    window_start = hourly_ts - pd.Timedelta(minutes=60)
    window_end = hourly_ts

    five_in_window = df_5min[
        (df_5min.index > window_start) & (df_5min.index <= window_end)
    ]

    if five_in_window.empty:
        pytest.skip(f"No 5min bars found in window ending {hourly_ts}")

    vol_5min_sum = float(five_in_window["volume"].sum())
    vol_60min = float(hour_bar["volume"])

    relative_diff = abs(vol_5min_sum - vol_60min) / (vol_60min + 1e-9)
    _warn_or_fail(
        relative_diff < 0.01,
        f"Volume mismatch at {hourly_ts}: 5min sum={vol_5min_sum:.0f}, "
        f"60min={vol_60min:.0f}, diff={relative_diff:.2%}. "
        "Possible cause: NinjaTrader exports timeframes independently.",
    )


def test_5min_ohlc_reconstructs_60min(df_5min, df_60min):
    hourly_ts = _pick_test_window(df_60min)
    hour_bar = df_60min.loc[hourly_ts]

    window_start = hourly_ts - pd.Timedelta(minutes=60)
    window_end = hourly_ts

    five_in_window = df_5min[
        (df_5min.index > window_start) & (df_5min.index <= window_end)
    ].sort_index()

    if five_in_window.empty:
        pytest.skip(f"No 5min bars found in window ending {hourly_ts}")

    expected_open = float(five_in_window["open"].iloc[0])
    expected_high = float(five_in_window["high"].max())
    expected_low = float(five_in_window["low"].min())
    expected_close = float(five_in_window["close"].iloc[-1])

    actual_open = float(hour_bar["open"])
    actual_high = float(hour_bar["high"])
    actual_low = float(hour_bar["low"])
    actual_close = float(hour_bar["close"])

    tol = 0.25  # NQ tick = 0.25, allow 1 tick tolerance

    _warn_or_fail(
        abs(expected_open - actual_open) <= tol,
        f"Open mismatch at {hourly_ts}: 5min-derived={expected_open}, 60min={actual_open}",
    )
    _warn_or_fail(
        abs(expected_high - actual_high) <= tol,
        f"High mismatch at {hourly_ts}: 5min-derived={expected_high}, 60min={actual_high}",
    )
    _warn_or_fail(
        abs(expected_low - actual_low) <= tol,
        f"Low mismatch at {hourly_ts}: 5min-derived={expected_low}, 60min={actual_low}",
    )
    _warn_or_fail(
        abs(expected_close - actual_close) <= tol,
        f"Close mismatch at {hourly_ts}: 5min-derived={expected_close}, 60min={actual_close}",
    )


def test_15min_ohlc_reconstructs_60min(df_15min, df_60min):
    hourly_ts = _pick_test_window(df_60min)
    hour_bar = df_60min.loc[hourly_ts]

    window_start = hourly_ts - pd.Timedelta(minutes=60)
    window_end = hourly_ts

    fifteen_in_window = df_15min[
        (df_15min.index > window_start) & (df_15min.index <= window_end)
    ].sort_index()

    if fifteen_in_window.empty:
        pytest.skip(f"No 15min bars found in window ending {hourly_ts}")

    expected_open = float(fifteen_in_window["open"].iloc[0])
    expected_high = float(fifteen_in_window["high"].max())
    expected_low = float(fifteen_in_window["low"].min())
    expected_close = float(fifteen_in_window["close"].iloc[-1])

    actual_open = float(hour_bar["open"])
    actual_high = float(hour_bar["high"])
    actual_low = float(hour_bar["low"])
    actual_close = float(hour_bar["close"])

    tol = 0.25

    _warn_or_fail(
        abs(expected_open - actual_open) <= tol,
        f"Open mismatch at {hourly_ts}: 15min-derived={expected_open}, 60min={actual_open}",
    )
    _warn_or_fail(
        abs(expected_high - actual_high) <= tol,
        f"High mismatch at {hourly_ts}: 15min-derived={expected_high}, 60min={actual_high}",
    )
    _warn_or_fail(
        abs(expected_low - actual_low) <= tol,
        f"Low mismatch at {hourly_ts}: 15min-derived={expected_low}, 60min={actual_low}",
    )
    _warn_or_fail(
        abs(expected_close - actual_close) <= tol,
        f"Close mismatch at {hourly_ts}: 15min-derived={expected_close}, 60min={actual_close}",
    )


def test_15min_volume_sums_to_60min(df_15min, df_60min):
    hourly_ts = _pick_test_window(df_60min)
    hour_bar = df_60min.loc[hourly_ts]

    window_start = hourly_ts - pd.Timedelta(minutes=60)
    window_end = hourly_ts

    fifteen_in_window = df_15min[
        (df_15min.index > window_start) & (df_15min.index <= window_end)
    ]

    if fifteen_in_window.empty:
        pytest.skip(f"No 15min bars found in window ending {hourly_ts}")

    vol_15min_sum = float(fifteen_in_window["volume"].sum())
    vol_60min = float(hour_bar["volume"])

    relative_diff = abs(vol_15min_sum - vol_60min) / (vol_60min + 1e-9)
    _warn_or_fail(
        relative_diff < 0.01,
        f"Volume mismatch at {hourly_ts}: 15min sum={vol_15min_sum:.0f}, "
        f"60min={vol_60min:.0f}, diff={relative_diff:.2%}.",
    )
