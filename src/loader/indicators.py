"""
Indicator wrappers that enforce as_of via get_bars.
Every function can only see bars strictly before as_of by construction.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import numpy as np
import pandas as pd

from src.loader.loader import get_bars


def _require_period(bars: pd.DataFrame, period: int, tf: str, indicator: str) -> None:
    if len(bars) < period:
        raise ValueError(
            f"{indicator}({tf}, period={period}): need {period} bars, "
            f"only {len(bars)} available before as_of."
        )


def sma(tf: str, as_of: pd.Timestamp, period: int) -> float:
    bars = get_bars(tf, as_of)
    _require_period(bars, period, tf, "sma")
    return float(bars["close"].iloc[-period:].mean())


def ema(tf: str, as_of: pd.Timestamp, period: int) -> float:
    bars = get_bars(tf, as_of)
    _require_period(bars, period, tf, "ema")
    # Use span=period, adjust=False to match standard EMA convention
    series = bars["close"].iloc[-period * 3 :] if len(bars) >= period * 3 else bars["close"]
    result = series.ewm(span=period, adjust=False).mean()
    return float(result.iloc[-1])


def atr(tf: str, as_of: pd.Timestamp, period: int) -> float:
    bars = get_bars(tf, as_of)
    # ATR needs period+1 bars (one extra for prior close)
    if len(bars) < period + 1:
        raise ValueError(
            f"atr({tf}, period={period}): need {period + 1} bars, "
            f"only {len(bars)} available before as_of."
        )
    window = bars.iloc[-(period + 1) :]
    high = window["high"].values
    low = window["low"].values
    prev_close = window["close"].shift(1).values

    tr = np.maximum(
        high[1:] - low[1:],
        np.maximum(
            np.abs(high[1:] - prev_close[1:]),
            np.abs(low[1:] - prev_close[1:]),
        ),
    )
    return float(tr.mean())


def rolling_high(tf: str, as_of: pd.Timestamp, period: int) -> float:
    bars = get_bars(tf, as_of)
    _require_period(bars, period, tf, "rolling_high")
    return float(bars["high"].iloc[-period:].max())


def rolling_low(tf: str, as_of: pd.Timestamp, period: int) -> float:
    bars = get_bars(tf, as_of)
    _require_period(bars, period, tf, "rolling_low")
    return float(bars["low"].iloc[-period:].min())
