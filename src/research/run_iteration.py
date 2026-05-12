"""
Iteration runner: change params.yaml, then run this script.

Usage:
    python src/research/run_iteration.py

Auto-creates the next numbered iteration folder under outputs/iterations/.
Each run is fully self-contained and reproducible.

Outputs per iteration (outputs/iterations/iteration_NNN/):
    params_snapshot.yaml        exact copy of params.yaml used
    patterns_NQ_{tf}.csv        signal-by-signal (all PatternRecord fields)
    summary.csv                 one aggregate row per timeframe
    patterns_{tf}/pattern_NNNN.png   inspection charts

To compare two runs:
    diff outputs/iterations/iteration_001/params_snapshot.yaml \
         outputs/iterations/iteration_002/params_snapshot.yaml
"""

import sys
import shutil
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import numpy as np
import pandas as pd
import yaml

from src.research.params    import load_params, reload_params, PARAMS_PATH, get as _p
from src.research.scoring   import score_history
from src.research.detector  import FractalDetector
from src.research.export    import patterns_to_dataframe, save_patterns
from src.research.visualize import plot_all_patterns

ITERATIONS_DIR = Path(__file__).resolve().parents[2] / "outputs" / "iterations"


# ---------------------------------------------------------------------------
# Auto-naming
# ---------------------------------------------------------------------------

def _next_name(iterations_dir: Path) -> str:
    """Return next auto-incremented name: iteration_001, iteration_002, ..."""
    existing = []
    if iterations_dir.exists():
        for d in iterations_dir.iterdir():
            if d.is_dir() and d.name.startswith("iteration_"):
                try:
                    existing.append(int(d.name.split("_")[1]))
                except (IndexError, ValueError):
                    pass
    return f"iteration_{(max(existing, default=0) + 1):03d}"


# ---------------------------------------------------------------------------
# Per-timeframe run
# ---------------------------------------------------------------------------

def _run_tf(tf: str, run_dir: Path, max_png: int, context_bars: int, ny: bool) -> dict:
    """
    Detect patterns for one timeframe, save CSV + PNGs, return stats dict.
    """
    print(f"\n  [{tf}] loading score history...")
    data = score_history(tf, ny_session=ny)
    print(f"  [{tf}] {len(data):,} bars  ({data.index[0].date()} to {data.index[-1].date()})")

    detector  = FractalDetector(tf)
    patterns  = detector.run(data)
    print(f"  [{tf}] {len(patterns):,} patterns detected")

    # Signal-by-signal CSV
    save_patterns(patterns, tf, run_dir)

    # Inspection PNGs
    subset = patterns[:max_png]
    if subset:
        plot_all_patterns(subset, data, run_dir, tf)

    # Aggregate stats for summary row
    if not patterns:
        return _empty_stats(tf, ny)

    df = patterns_to_dataframe(patterns)
    return {
        "timeframe":          tf,
        "ny_session":         ny,
        "pattern_count":      len(patterns),
        "fib_depth_mean":     round(df["fib_retracement_depth"].mean(),  3),
        "fib_depth_median":   round(df["fib_retracement_depth"].median(), 3),
        "fib_depth_std":      round(df["fib_retracement_depth"].std(),   3),
        "move_bars_mean":     round(df["move_duration_bars"].mean(),     1),
        "move_bars_median":   round(df["move_duration_bars"].median(),   1),
        "consol_bars_mean":   round(df["consol_duration_bars"].mean(),   1),
        "consol_bars_median": round(df["consol_duration_bars"].median(), 1),
        "entry_score_mean":   round(df["entry_score"].mean(),            3),
    }


def _empty_stats(tf: str, ny: bool) -> dict:
    return {
        "timeframe": tf, "ny_session": ny, "pattern_count": 0,
        "fib_depth_mean": None,  "fib_depth_median": None, "fib_depth_std": None,
        "move_bars_mean": None,  "move_bars_median": None,
        "consol_bars_mean": None,"consol_bars_median": None,
        "entry_score_mean": None,
    }


# ---------------------------------------------------------------------------
# Summary enrichment — append key params so CSV is self-documenting
# ---------------------------------------------------------------------------

def _enrich_summary(rows: list[dict], params: dict, name: str, ts: str) -> pd.DataFrame:
    """Add iteration metadata and key param values to every row."""
    key_params = {
        "trend_up_threshold":              params["regimes"]["trend_up_threshold"]["value"],
        "range_low_threshold":             params["regimes"]["range_low_threshold"]["value"],
        "hysteresis":                      params["detector"]["hysteresis"]["value"],
        "min_move_bars":                   params["detector"]["min_move_bars"]["value"],
        "min_consol_bars":                 params["detector"]["min_consolidation_bars"]["value"],
        "timeout_mult":                    params["detector"]["consolidation_timeout_multiplier"]["value"],
        "fib_invalidation":                params["detector"]["fib_invalidation_level"]["value"],
        "breakout_uses_close":             params["detector"]["breakout_uses_close"]["value"],
        "invalidation_uses_close":         params["detector"]["invalidation_uses_close"]["value"],
        "scales":                          str(params["scoring"]["scales"]["value"]),
    }
    for row in rows:
        row["iteration"]  = name
        row["run_ts"]     = ts
        row.update(key_params)

    cols = (
        ["iteration", "run_ts", "timeframe", "ny_session", "pattern_count",
         "fib_depth_mean", "fib_depth_median", "fib_depth_std",
         "move_bars_mean", "move_bars_median",
         "consol_bars_mean", "consol_bars_median",
         "entry_score_mean"]
        + list(key_params.keys())
    )
    return pd.DataFrame(rows, columns=cols)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    # Fresh params load (clears cache so changes are picked up)
    params = reload_params()

    name = _next_name(ITERATIONS_DIR)
    run_dir = ITERATIONS_DIR / name
    run_dir.mkdir(parents=True, exist_ok=True)

    run_ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    print(f"\nNQ Fractal Pattern Detector — {name}")
    print(f"Run timestamp : {run_ts}")
    print(f"Output dir    : {run_dir}")

    # Snapshot params
    shutil.copy(PARAMS_PATH, run_dir / "params_snapshot.yaml")
    print(f"Params snapshot saved.")

    # Pull visualization / session / run config
    max_png      = _p("visualization", "max_png_per_tf")
    context_bars = _p("visualization", "context_bars")
    ny_flag      = _p("session", "ny_session_only")
    timeframes   = _p("run", "timeframes")

    print(f"Timeframes     : {timeframes}")
    print(f"NY session     : {ny_flag}  |  max PNG: {max_png}  |  context bars: {context_bars}")

    # Run each timeframe
    stats_rows = []
    for tf in timeframes:
        ny = ny_flag and (tf != "1day")
        try:
            row = _run_tf(tf, run_dir, max_png, context_bars, ny)
            stats_rows.append(row)
        except Exception as exc:
            print(f"\n  [ERROR] {tf}: {exc}")
            stats_rows.append(_empty_stats(tf, ny_flag and (tf != "1day")))

    # Summary CSV
    summary = _enrich_summary(stats_rows, params, name, run_ts)
    summary_path = run_dir / "summary.csv"
    summary.to_csv(summary_path, index=False)

    print(f"\n{'='*60}")
    print(f"Iteration complete: {name}")
    print(f"Summary:\n")
    print(summary[["timeframe", "pattern_count", "fib_depth_mean",
                   "move_bars_mean", "consol_bars_mean", "entry_score_mean"]].to_string(index=False))
    print(f"\nAll outputs in: {run_dir}")


if __name__ == "__main__":
    main()
