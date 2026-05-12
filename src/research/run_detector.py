"""
Runner: detect fractal patterns for every NQ timeframe.

Usage:
    python src/research/run_detector.py

Outputs:
    outputs/patterns/patterns_NQ_{tf}.csv  — all detected patterns per TF
    outputs/patterns/{tf}/pattern_NNNN.png — inspection chart (first 20 patterns)
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import numpy as np

from src.research.scoring  import score_history
from src.research.detector import FractalDetector
from src.research.export   import save_patterns
from src.research.visualize import plot_all_patterns

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
TIMEFRAMES   = ["1min", "5min", "15min", "60min", "1day"]
OUTPUT_DIR   = Path(__file__).resolve().parents[2] / "outputs" / "patterns"
MAX_PNG      = 20   # how many inspection PNGs to generate per TF

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fib_stats(patterns) -> str:
    if not patterns:
        return "n/a"
    depths = [p.fib_retracement_depth for p in patterns]
    return (
        f"min={min(depths):.2f}  mean={np.mean(depths):.2f}  max={max(depths):.2f}"
    )


def _move_stats(patterns) -> str:
    if not patterns:
        return "n/a"
    durations = [p.move_duration_bars for p in patterns]
    return (
        f"min={min(durations)}  mean={np.mean(durations):.1f}  max={max(durations)}"
    )


def _consol_stats(patterns) -> str:
    if not patterns:
        return "n/a"
    durations = [p.consol_duration_bars for p in patterns]
    return (
        f"min={min(durations)}  mean={np.mean(durations):.1f}  max={max(durations)}"
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run_timeframe(tf: str) -> None:
    print(f"\n{'='*60}")
    print(f"  Timeframe: {tf}")
    print(f"{'='*60}")

    print(f"  Loading score history...")
    ny = tf != "1day"
    data = score_history(tf, ny_session=ny)
    session_note = " [NY session only]" if ny else ""
    print(f"  {len(data):,} bars loaded{session_note}  ({data.index[0].date()} to {data.index[-1].date()})")

    print(f"  Running FractalDetector...")
    detector = FractalDetector(tf)
    patterns = detector.run(data)
    print(f"  Patterns detected: {len(patterns)}")

    if patterns:
        print(f"  Fib depth stats  : {_fib_stats(patterns)}")
        print(f"  Move bars stats  : {_move_stats(patterns)}")
        print(f"  Consol bars stats: {_consol_stats(patterns)}")

    # Save CSV
    csv_path = save_patterns(patterns, tf, OUTPUT_DIR)
    print(f"  Saved CSV: {csv_path}")

    # Generate inspection PNGs for first MAX_PNG patterns
    subset = patterns[:MAX_PNG]
    if subset:
        print(f"  Generating {len(subset)} inspection PNGs...")
        plot_all_patterns(subset, data, OUTPUT_DIR, tf)
    else:
        print(f"  No patterns — skipping PNG generation.")


def main() -> None:
    print("NQ Fractal Pattern Detector")
    print(f"Output dir: {OUTPUT_DIR}")

    for tf in TIMEFRAMES:
        try:
            run_timeframe(tf)
        except Exception as exc:
            print(f"\n  [ERROR] {tf}: {exc}")

    print(f"\nDone. CSVs and PNGs in: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
