"""
Leak-proof data loading API for NQ futures clean parquet files.

All filtering is strictly bar_close_utc < as_of.
No bar whose close time >= as_of is ever returned.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from functools import lru_cache

import pandas as pd

from src.utils.timeframes import CLEAN_DATA_DIR, TIMEFRAMES


def _validate_as_of(as_of: pd.Timestamp) -> None:
    if as_of.tzinfo is None:
        raise ValueError(
            f"as_of must be timezone-aware (UTC). Got naive timestamp: {as_of!r}"
        )


@lru_cache(maxsize=None)
def _load_clean(tf: str) -> pd.DataFrame:
    if tf not in TIMEFRAMES:
        raise ValueError(f"Unknown timeframe: {tf!r}. Valid: {list(TIMEFRAMES)}")

    parquet_path = CLEAN_DATA_DIR / f"NQ_{tf}_clean.parquet"
    if not parquet_path.exists():
        raise FileNotFoundError(
            f"Clean data not found for timeframe {tf!r}. "
            f"Expected: {parquet_path}. Run src/pipeline/clean.py first."
        )

    df = pd.read_parquet(parquet_path, engine="pyarrow")
    return df


def get_bars(tf: str, as_of: pd.Timestamp) -> pd.DataFrame:
    """
    Returns all bars for timeframe tf whose close time is strictly less than as_of.
    as_of must be timezone-aware (UTC).
    Raises ValueError if as_of is naive.
    Raises FileNotFoundError if clean data doesn't exist for tf.
    Never returns a forming bar. Never returns future data.
    """
    _validate_as_of(as_of)
    df = _load_clean(tf)

    as_of_utc = as_of.tz_convert("UTC")
    # Strict less-than: the bar whose close equals as_of is still forming
    mask = df["bar_close_utc"] < as_of_utc
    return df[mask].copy()


def get_last_closed_bar(tf: str, as_of: pd.Timestamp) -> pd.Series:
    """
    Returns the single most recent fully-closed bar as of as_of.
    Raises LookupError if no bar exists before as_of.
    """
    bars = get_bars(tf, as_of)
    if bars.empty:
        raise LookupError(
            f"No closed bars found for timeframe {tf!r} before as_of={as_of!r}."
        )
    return bars.iloc[-1]


def get_multi_tf(timeframes: list[str], as_of: pd.Timestamp) -> dict[str, pd.Series]:
    """
    Returns the last closed bar for each timeframe, all relative to the same as_of.
    Each value is the last bar whose close time < as_of on that timeframe.
    """
    _validate_as_of(as_of)
    result = {}
    for tf in timeframes:
        result[tf] = get_last_closed_bar(tf, as_of)
    return result


def load_all(tf: str) -> pd.DataFrame:
    """
    Returns the complete clean dataset for a timeframe.
    FOR RESEARCH AND VISUALIZATION USE ONLY.
    Never call this inside a backtest or signal loop — use get_bars(tf, as_of) there.
    """
    return _load_clean(tf).copy()
