"""
Regime statistics — empirical persistence of trending/consolidating/reversal regimes.

DESCRIPTIVE ANALYSIS ONLY. These functions measure what NQ regimes actually do.
They are NOT used to set strategy parameters. Using them to optimize thresholds
would create in-sample bias.

See src/pipeline/decisions.md for the full note on the in-sample / out-of-sample
boundary.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from dataclasses import dataclass

import pandas as pd
import numpy as np


@dataclass
class RegimeRun:
    regime: str            # "trending_up", "consolidating", "trending_down"
    start_ts: pd.Timestamp
    end_ts: pd.Timestamp
    duration_bars: int
    timeframe: str


# ---------------------------------------------------------------------------
# Core classification
# ---------------------------------------------------------------------------

def classify_regime(score: float, trend_up: float = 0.65, range_low: float = 0.35) -> str:
    """Returns "trending_up", "consolidating", or "trending_down"."""
    if score > trend_up:
        return "trending_up"
    elif score < range_low:
        return "trending_down"
    else:
        return "consolidating"


# ---------------------------------------------------------------------------
# Run extraction
# ---------------------------------------------------------------------------

def extract_regime_runs(
    data: pd.DataFrame,
    tf: str,
    trend_up: float = 0.65,
    range_low: float = 0.35,
) -> list[RegimeRun]:
    """
    Given score_history() output, returns list of RegimeRun.
    Each run is a contiguous block of bars in the same regime.
    data must have a 'score' column and a DatetimeIndex.
    No minimum duration filter — returns all runs including 1-bar ones.
    """
    if "score" not in data.columns:
        raise ValueError("data must have a 'score' column")
    if data.empty:
        return []

    runs: list[RegimeRun] = []

    regimes = data["score"].map(lambda s: classify_regime(s, trend_up, range_low))

    current_regime = regimes.iloc[0]
    run_start_ts = data.index[0]
    run_start_i = 0

    for i in range(1, len(regimes)):
        r = regimes.iloc[i]
        if r != current_regime:
            # Close the current run
            runs.append(RegimeRun(
                regime=current_regime,
                start_ts=run_start_ts,
                end_ts=data.index[i - 1],
                duration_bars=i - run_start_i,
                timeframe=tf,
            ))
            current_regime = r
            run_start_ts = data.index[i]
            run_start_i = i

    # Close the final run
    runs.append(RegimeRun(
        regime=current_regime,
        start_ts=run_start_ts,
        end_ts=data.index[-1],
        duration_bars=len(regimes) - run_start_i,
        timeframe=tf,
    ))

    return runs


# ---------------------------------------------------------------------------
# Duration statistics
# ---------------------------------------------------------------------------

def regime_duration_stats(runs: list[RegimeRun]) -> pd.DataFrame:
    """
    Returns a DataFrame with columns:
    regime, count, min_bars, p25_bars, median_bars, p75_bars, p90_bars, max_bars, mean_bars
    One row per regime type.
    """
    regime_names = ["trending_up", "consolidating", "trending_down"]
    rows = []

    for regime in regime_names:
        durations = [r.duration_bars for r in runs if r.regime == regime]
        if not durations:
            rows.append({
                "regime": regime,
                "count": 0,
                "min_bars": np.nan,
                "p25_bars": np.nan,
                "median_bars": np.nan,
                "p75_bars": np.nan,
                "p90_bars": np.nan,
                "max_bars": np.nan,
                "mean_bars": np.nan,
            })
            continue
        arr = np.array(durations, dtype=float)
        rows.append({
            "regime": regime,
            "count": len(arr),
            "min_bars": int(arr.min()),
            "p25_bars": float(np.percentile(arr, 25)),
            "median_bars": float(np.median(arr)),
            "p75_bars": float(np.percentile(arr, 75)),
            "p90_bars": float(np.percentile(arr, 90)),
            "max_bars": int(arr.max()),
            "mean_bars": float(arr.mean()),
        })

    return pd.DataFrame(rows).set_index("regime")


# ---------------------------------------------------------------------------
# Survival table
# ---------------------------------------------------------------------------

def survival_table(
    runs: list[RegimeRun],
    regime: str,
    max_bars: int = 200,
) -> pd.DataFrame:
    """
    Survival table for one regime type.
    Returns DataFrame: duration_bars (1..max_bars), n_surviving, pct_surviving.
    pct_surviving[d] = fraction of runs that lasted at least d bars.
    """
    durations = np.array(
        [r.duration_bars for r in runs if r.regime == regime],
        dtype=float,
    )
    if len(durations) == 0:
        return pd.DataFrame(
            {"duration_bars": range(1, max_bars + 1), "n_surviving": 0, "pct_surviving": 0.0}
        )

    total = len(durations)
    dur_range = np.arange(1, max_bars + 1)
    n_surviving = np.array([(durations >= d).sum() for d in dur_range])
    pct_surviving = n_surviving / total

    return pd.DataFrame({
        "duration_bars": dur_range,
        "n_surviving": n_surviving,
        "pct_surviving": pct_surviving,
    })


# ---------------------------------------------------------------------------
# Rolling median duration
# ---------------------------------------------------------------------------

def rolling_median_duration(
    runs: list[RegimeRun],
    regime: str,
    window: int = 500,
) -> pd.Series:
    """
    Rolling median duration of a regime type over time.
    Index = end_ts of each run. Values = rolling median of duration_bars.
    window = number of regime runs (not bars) per window.
    """
    subset = [r for r in runs if r.regime == regime]
    if not subset:
        return pd.Series(dtype=float)

    timestamps = [r.end_ts for r in subset]
    durations = [r.duration_bars for r in subset]

    s = pd.Series(durations, index=timestamps, dtype=float)
    return s.rolling(window=window, min_periods=1).median()
