"""
Export utilities for PatternRecord collections.
Converts PatternRecord lists to/from flat DataFrames and CSV files.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import pandas as pd

from src.research.detection.detector import PatternRecord


def patterns_to_dataframe(patterns: list[PatternRecord]) -> pd.DataFrame:
    """Convert list of PatternRecord to a flat DataFrame."""
    if not patterns:
        return pd.DataFrame()

    rows = [
        {
            "timeframe":             p.timeframe,
            "move_start_ts":         p.move_start_ts,
            "move_end_ts":           p.move_end_ts,
            "move_low":              p.move_low,
            "move_high":             p.move_high,
            "move_duration_bars":    p.move_duration_bars,
            "consol_start_ts":       p.consol_start_ts,
            "consol_end_ts":         p.consol_end_ts,
            "consol_low":            p.consol_low,
            "consol_high":           p.consol_high,
            "consol_duration_bars":  p.consol_duration_bars,
            "fib_retracement_depth": p.fib_retracement_depth,
            "fib_50":                p.fib_50,
            "entry_ts":              p.entry_ts,
            "entry_price":           p.entry_price,
            "entry_score":           p.entry_score,
        }
        for p in patterns
    ]
    return pd.DataFrame(rows)


def save_patterns(patterns: list[PatternRecord], tf: str, output_dir: Path) -> Path:
    """
    Save patterns to CSV at output_dir/patterns_NQ_{tf}.csv.
    Returns the path written. Creates output_dir if needed.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    dest = output_dir / f"patterns_NQ_{tf}.csv"
    df = patterns_to_dataframe(patterns)
    df.to_csv(dest, index=False)
    return dest


def load_patterns(tf: str, output_dir: Path) -> pd.DataFrame:
    """Load previously saved patterns CSV. Raises FileNotFoundError if missing."""
    output_dir = Path(output_dir)
    path = output_dir / f"patterns_NQ_{tf}.csv"

    if not path.exists():
        raise FileNotFoundError(
            f"Patterns file not found: {path}\n"
            f"Run run_detector.py first to generate it."
        )

    df = pd.read_csv(path, parse_dates=[
        "move_start_ts", "move_end_ts",
        "consol_start_ts", "consol_end_ts",
        "entry_ts",
    ])
    return df
