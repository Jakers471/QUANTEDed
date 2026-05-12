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

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import numpy as np
import pandas as pd
import yaml

from src.research.params                      import load_params, reload_params, PARAMS_PATH, get as _p
from src.research.score.scoring               import score_history
from src.research.detection.detector          import FractalDetector, PatternRecord, AbortRecord
from src.research.detection.export            import patterns_to_dataframe, save_patterns
from src.research.visualization.visualize     import plot_all_patterns
from src.research.visualization.visualize_summary import (
    plot_summary_dashboard, plot_signal_map, plot_detection_overlay,
)
from src.loader.loader import load_all as _load_all_raw

ITERATIONS_DIR = Path(__file__).resolve().parents[3] / "outputs" / "iterations"


# ---------------------------------------------------------------------------
# Auto-naming
# ---------------------------------------------------------------------------

def _data_date_range(timeframes: list) -> tuple[str, str]:
    """Get data start/end dates from the smallest available TF parquet (fast)."""
    tf = "1day" if "1day" in timeframes else timeframes[0]
    df = _load_all_raw(tf)
    return str(df.index[0].date()), str(df.index[-1].date())


def _next_name(iterations_dir: Path, d_start: str, d_end: str) -> str:
    """Return next auto-incremented name: iteration_001_2005-01-11_2025-01-10"""
    existing = []
    if iterations_dir.exists():
        for d in iterations_dir.iterdir():
            if d.is_dir() and d.name.startswith("iteration_"):
                try:
                    existing.append(int(d.name.split("_")[1]))
                except (IndexError, ValueError):
                    pass
    num = max(existing, default=0) + 1
    return f"iteration_{num:03d}_{d_start}_{d_end}"


# ---------------------------------------------------------------------------
# Per-timeframe run
# ---------------------------------------------------------------------------

def _add_atr(data: pd.DataFrame, period: int) -> pd.DataFrame:
    prev_close = data["close"].shift(1)
    tr = pd.concat([
        data["high"] - data["low"],
        (data["high"] - prev_close).abs(),
        (data["low"]  - prev_close).abs(),
    ], axis=1).max(axis=1)
    data = data.copy()
    data["atr"] = tr.rolling(period, min_periods=1).mean()
    return data


def _clip_dates(data: pd.DataFrame, start, end) -> pd.DataFrame:
    if start:
        data = data[data.index >= pd.Timestamp(str(start), tz="UTC")]
    if end:
        data = data[data.index <= pd.Timestamp(str(end), tz="UTC")]
    return data


def _run_tf(tf: str, run_dir: Path, max_png: int, context_bars: int, ny: bool,
            start_date: str | None, end_date: str | None) -> tuple[dict, list[PatternRecord], list[AbortRecord], "pd.DataFrame"]:
    """
    Detect patterns for one timeframe, save CSV + PNGs, return (stats, patterns, aborts, data).
    """
    print(f"\n  [{tf}] loading score history...")
    data = score_history(tf, ny_session=ny)
    data = _clip_dates(data, start_date, end_date)
    data = _add_atr(data, _p("detector", "atr_period"))
    print(f"  [{tf}] {len(data):,} bars  ({data.index[0].date()} to {data.index[-1].date()})")

    detector = FractalDetector(tf)
    patterns = detector.run(data)
    aborts   = detector.aborts
    print(f"  [{tf}] {len(patterns):,} completed  |  {len(aborts):,} aborted")

    # Signal-by-signal CSV
    save_patterns(patterns, tf, run_dir)

    # Inspection PNGs (individual pattern charts — unchanged)
    subset = patterns[:max_png]
    if subset:
        plot_all_patterns(subset, data, run_dir, tf)

    if not patterns:
        return _empty_stats(tf, ny), patterns, aborts, data

    df = patterns_to_dataframe(patterns)
    stats = {
        "timeframe":          tf,
        "ny_session":         ny,
        "pattern_count":      len(patterns),
        "abort_count":        len(aborts),
        "fib_depth_mean":     round(df["fib_retracement_depth"].mean(),  3),
        "fib_depth_median":   round(df["fib_retracement_depth"].median(), 3),
        "fib_depth_std":      round(df["fib_retracement_depth"].std(),   3),
        "move_bars_mean":     round(df["move_duration_bars"].mean(),     1),
        "move_bars_median":   round(df["move_duration_bars"].median(),   1),
        "consol_bars_mean":   round(df["consol_duration_bars"].mean(),   1),
        "consol_bars_median": round(df["consol_duration_bars"].median(), 1),
        "entry_score_mean":   round(df["entry_score"].mean(),            3),
    }
    return stats, patterns, aborts, data


def _empty_stats(tf: str, ny: bool) -> dict:
    return {
        "timeframe": tf, "ny_session": ny, "pattern_count": 0, "abort_count": 0,
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
        "consol_max_bars":                 params["detector"]["consolidation_max_bars"]["value"],
        "min_move_atr_multiple":           params["detector"]["min_move_atr_multiple"]["value"],
        "atr_period":                      params["detector"]["atr_period"]["value"],
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
        ["iteration", "run_ts", "timeframe", "ny_session",
         "pattern_count", "abort_count",
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

    timeframes   = _p("run", "timeframes")
    start_date   = _p("run", "start_date")
    end_date     = _p("run", "end_date")

    # Folder label uses the configured date range; fall back to parquet bounds if null
    if start_date or end_date:
        raw_start, raw_end = _data_date_range(timeframes)
        d_start = start_date or raw_start
        d_end   = str(end_date) if end_date else raw_end
    else:
        d_start, d_end = _data_date_range(timeframes)
    name = _next_name(ITERATIONS_DIR, d_start, d_end)
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
    overlay_bars_cfg = _p("visualization", "detection_overlay_bars")

    print(f"Timeframes     : {timeframes}")
    print(f"Date range     : {start_date or 'all'} to {end_date or 'latest'}")
    print(f"NY session     : {ny_flag}  |  max PNG: {max_png}  |  context bars: {context_bars}")

    # Run each timeframe
    stats_rows     = []
    patterns_by_tf = {}
    aborts_by_tf   = {}
    data_by_tf     = {}

    for tf in timeframes:
        ny = ny_flag and (tf != "1day")
        try:
            row, patterns, aborts, data = _run_tf(tf, run_dir, max_png, context_bars, ny, start_date, end_date)
            stats_rows.append(row)
            patterns_by_tf[tf] = patterns
            aborts_by_tf[tf]   = aborts
            data_by_tf[tf]     = data
        except Exception as exc:
            print(f"\n  [ERROR] {tf}: {exc}")
            stats_rows.append(_empty_stats(tf, ny_flag and (tf != "1day")))

    # Summary CSV
    summary = _enrich_summary(stats_rows, params, name, run_ts)
    summary_path = run_dir / "summary.csv"
    summary.to_csv(summary_path, index=False)

    # Summary dashboard PNG
    print(f"\n  Generating summary visuals...")
    try:
        plot_summary_dashboard(
            patterns_by_tf, aborts_by_tf, name,
            run_dir / "summary_dashboard.png"
        )
    except Exception as exc:
        print(f"  [WARN] summary_dashboard failed: {exc}")

    # Per-TF signal map PNGs
    for tf in patterns_by_tf:
        try:
            plot_signal_map(
                tf,
                patterns_by_tf[tf],
                aborts_by_tf.get(tf, []),
                name,
                run_dir / f"signal_map_{tf}.png",
            )
        except Exception as exc:
            print(f"  [WARN] signal_map_{tf} failed: {exc}")

    # Per-TF detection overlay PNGs (6 sample periods across full history)
    overlay_per_tf = overlay_bars_cfg.get("per_timeframe", {}) if isinstance(overlay_bars_cfg, dict) else {}
    for tf in data_by_tf:
        try:
            plot_detection_overlay(
                tf,
                data_by_tf[tf],
                patterns_by_tf.get(tf, []),
                aborts_by_tf.get(tf, []),
                name,
                run_dir / f"detection_overlay_{tf}.png",
                window_bars=overlay_per_tf.get(tf, 1000),
            )
        except Exception as exc:
            print(f"  [WARN] detection_overlay_{tf} failed: {exc}")

    print(f"\n{'='*60}")
    print(f"Iteration complete: {name}")
    print(f"Summary:\n")
    print(summary[["timeframe", "pattern_count", "abort_count", "fib_depth_mean",
                   "move_bars_mean", "consol_bars_mean", "entry_score_mean"]].to_string(index=False))
    print(f"\nAll outputs in: {run_dir}")


if __name__ == "__main__":
    main()
