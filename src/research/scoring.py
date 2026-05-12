"""
Binary decomposition scoring for NQ futures.
Each timeframe is scored independently — no cross-timeframe logic here.

Score = fraction of SMA scales where close > SMA(scale).
Range: 0.0 (below all SMAs) to 1.0 (above all SMAs).
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pandas as pd

from src.loader.loader import get_bars, load_all
from src.utils.timeframes import filter_ny_session
from src.research.params import get as _p


def _scales() -> list[int]:
    """Read scales from params.yaml each call — respects reload_params() between iterations."""
    return _p("scoring", "scales")


def binary_decomp_score(tf: str, as_of: pd.Timestamp) -> float:
    """
    Point-in-time binary decomp score as of as_of.
    as_of must be UTC timezone-aware.
    Raises ValueError if fewer than max(scales) bars available.
    """
    scales = _scales()
    bars = get_bars(tf, as_of)
    if len(bars) < scales[-1]:
        raise ValueError(
            f"Need at least {scales[-1]} bars before {as_of}, got {len(bars)}"
        )
    close = bars["close"]
    last_close = close.iloc[-1]
    hits = sum(1 for s in scales if last_close > close.rolling(s).mean().iloc[-1])
    return hits / len(scales)


def score_breakdown(tf: str, as_of: pd.Timestamp) -> dict:
    """
    Returns per-scale binary values and the overall score.
    Useful for debugging what the scorer is seeing at a specific moment.
    """
    scales = _scales()
    bars = get_bars(tf, as_of)
    if len(bars) < scales[-1]:
        raise ValueError(
            f"Need at least {scales[-1]} bars before {as_of}, got {len(bars)}"
        )
    close = bars["close"]
    last_close = close.iloc[-1]
    breakdown = {f"s{s}": int(last_close > close.rolling(s).mean().iloc[-1]) for s in scales}
    breakdown["score"] = sum(breakdown.values()) / len(scales)
    breakdown["close"] = last_close
    breakdown["as_of"] = as_of
    return breakdown


def score_history(tf: str, last_n_bars: int | None = None, ny_session: bool = False) -> pd.DataFrame:
    """
    Vectorized binary decomp score for every bar in the clean dataset.
    FOR VISUALIZATION AND RESEARCH ONLY — not for backtesting.

    Returns DataFrame indexed by datetime (UTC) with columns:
      s2, s4, ... per active scale  — per-scale binary (0 or 1)
      score                          — mean of all scale columns
      open, high, low, close, volume — bar data

    Bars where any SMA hasn't warmed up are dropped (dropna).
    """
    scales = _scales()
    df = load_all(tf)

    if last_n_bars is not None:
        df = df.iloc[-(last_n_bars + scales[-1]):]

    close = df["close"]
    scale_cols = {}
    for s in scales:
        sma = close.rolling(s).mean()
        scale_cols[f"s{s}"] = (close > sma).astype(float)

    result = pd.DataFrame(scale_cols, index=df.index)
    result["score"] = result[[f"s{s}" for s in scales]].mean(axis=1)
    result["open"]   = df["open"]
    result["high"]   = df["high"]
    result["low"]    = df["low"]
    result["close"]  = df["close"]
    result["volume"] = df["volume"]

    result = result.dropna()
    if ny_session and tf != "1day":
        result = filter_ny_session(result)
    if last_n_bars is not None:
        result = result.iloc[-last_n_bars:]
    return result
