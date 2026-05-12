"""
Runner: compute and visualize regime duration statistics for all timeframes.

Usage:
    python src/research/run_regime_stats.py

Outputs per timeframe in outputs/regime_stats/NQ_{tf}/:
    regime_runs.csv        -- every regime run with timestamps and duration
    duration_histogram.png -- distribution of how long each regime type lasts
    survival_curve.png     -- % of regimes surviving to each duration
    rolling_median.png     -- how regime persistence has changed over time
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import yaml

from src.research.score.scoring      import score_history
from src.research.score.regime_stats import (
    extract_regime_runs,
    regime_duration_stats,
    survival_table,
    rolling_median_duration,
    RegimeRun,
)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

_PARAMS_PATH = Path(__file__).resolve().parents[3] / "src" / "research" / "params.yaml"
with open(_PARAMS_PATH) as _f:
    _PARAMS = yaml.safe_load(_f)

_VIZ   = _PARAMS["visualization"]
_REGS  = _PARAMS["regimes"]
_STATS = _PARAMS["regime_stats"]

TREND_UP  = _REGS["trend_up_threshold"]["value"]
RANGE_LOW = _REGS["range_low_threshold"]["value"]
ROLLING_WINDOW = _STATS["rolling_window_bars"]["value"]
SURVIVAL_MAX   = _STATS["survival_curve_max_bars"]["value"]

COLORS = _VIZ["colors"]
BG        = COLORS["background"]
TEAL      = COLORS["trending_up"]
RED       = COLORS["trending_down"]
GRAY      = COLORS["consolidating"]
GRID_COL  = "#1e2530"
LABEL_COL = "#6b7a8d"

REGIME_COLOR = {
    "trending_up":   TEAL,
    "consolidating": GRAY,
    "trending_down": RED,
}

TIMEFRAMES = ["1min", "5min", "15min", "60min", "1day"]

OUTPUT_BASE = Path(__file__).resolve().parents[3] / "outputs" / "regime_stats"


# ---------------------------------------------------------------------------
# Plot helpers
# ---------------------------------------------------------------------------

def _style_ax(ax: plt.Axes) -> None:
    ax.set_facecolor(BG)
    ax.tick_params(colors=LABEL_COL, length=2)
    for spine in ax.spines.values():
        spine.set_color(GRID_COL)
    ax.yaxis.grid(True, color=GRID_COL, linewidth=0.4, alpha=0.6)
    ax.xaxis.grid(False)


def plot_duration_histogram(
    runs: list[RegimeRun],
    tf: str,
    save_path: Path,
) -> None:
    """3 stacked subplots, one per regime type. Dark style."""
    regimes = ["trending_up", "consolidating", "trending_down"]
    labels  = ["Trending Up", "Consolidating", "Trending Down"]

    fig, axes = plt.subplots(3, 1, figsize=(14, 10), facecolor=BG)
    fig.subplots_adjust(hspace=0.45)
    fig.suptitle(
        f"NQ {tf}  |  Regime Duration Distribution",
        color=LABEL_COL, fontsize=9, y=0.98,
    )

    for ax, regime, label in zip(axes, regimes, labels):
        durations = [r.duration_bars for r in runs if r.regime == regime]
        color = REGIME_COLOR[regime]
        _style_ax(ax)
        if durations:
            max_d = max(durations)
            # Cap bin range to avoid extreme outliers dominating the chart
            cap = int(np.percentile(durations, 97))
            bins = min(60, cap) if cap > 1 else 2
            ax.hist(
                [min(d, cap) for d in durations],
                bins=bins,
                color=color,
                alpha=0.85,
                edgecolor=BG,
                linewidth=0.4,
            )
            ax.set_title(
                f"{label}  (n={len(durations)}, median={np.median(durations):.0f} bars,"
                f" max={max_d} bars)",
                color=LABEL_COL, fontsize=7.5, pad=4,
            )
        else:
            ax.set_title(f"{label}  (no data)", color=LABEL_COL, fontsize=7.5, pad=4)
        ax.set_xlabel("Duration (bars)", color=LABEL_COL, fontsize=7)
        ax.set_ylabel("Count", color=LABEL_COL, fontsize=7)
        ax.tick_params(axis="x", colors=LABEL_COL, labelsize=7)
        ax.tick_params(axis="y", colors=LABEL_COL, labelsize=7)

    save_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(save_path, dpi=150, bbox_inches="tight", facecolor=BG, pad_inches=0.1)
    print(f"  Saved: {save_path}")
    plt.close(fig)


def plot_survival_curve(
    runs: list[RegimeRun],
    tf: str,
    max_bars: int,
    save_path: Path,
) -> None:
    """All 3 regime survival curves on one plot. Dark style."""
    fig, ax = plt.subplots(figsize=(14, 6), facecolor=BG)
    _style_ax(ax)
    ax.yaxis.grid(True, color=GRID_COL, linewidth=0.4, alpha=0.6)

    regimes = ["trending_up", "consolidating", "trending_down"]
    labels  = ["Trending Up", "Consolidating", "Trending Down"]

    for regime, label in zip(regimes, labels):
        tbl = survival_table(runs, regime, max_bars=max_bars)
        color = REGIME_COLOR[regime]
        ax.plot(
            tbl["duration_bars"],
            tbl["pct_surviving"] * 100,
            color=color,
            linewidth=1.4,
            label=label,
        )

    ax.set_xlabel("Duration (bars)", color=LABEL_COL, fontsize=8)
    ax.set_ylabel("% of regimes surviving", color=LABEL_COL, fontsize=8)
    ax.set_title(
        f"NQ {tf}  |  Regime Survival Curves",
        color=LABEL_COL, fontsize=9,
    )
    ax.tick_params(axis="both", colors=LABEL_COL, labelsize=7)
    ax.set_xlim(1, max_bars)
    ax.set_ylim(0, 100)

    legend = ax.legend(
        fontsize=7,
        facecolor=GRID_COL,
        edgecolor=GRID_COL,
        labelcolor=LABEL_COL,
    )

    save_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(save_path, dpi=150, bbox_inches="tight", facecolor=BG, pad_inches=0.1)
    print(f"  Saved: {save_path}")
    plt.close(fig)


def plot_rolling_median(
    runs: list[RegimeRun],
    tf: str,
    window: int,
    save_path: Path,
) -> None:
    """Rolling median regime duration over time, one line per regime type."""
    fig, ax = plt.subplots(figsize=(16, 5), facecolor=BG)
    _style_ax(ax)

    regimes = ["trending_up", "consolidating", "trending_down"]
    labels  = ["Trending Up", "Consolidating", "Trending Down"]

    for regime, label in zip(regimes, labels):
        series = rolling_median_duration(runs, regime, window=window)
        if series.empty:
            continue
        color = REGIME_COLOR[regime]
        ax.plot(series.index, series.values, color=color, linewidth=1.2, label=label)

    ax.set_xlabel("Date", color=LABEL_COL, fontsize=8)
    ax.set_ylabel(f"Median Duration (bars, rolling {window} runs)", color=LABEL_COL, fontsize=8)
    ax.set_title(
        f"NQ {tf}  |  Rolling Median Regime Duration",
        color=LABEL_COL, fontsize=9,
    )
    ax.tick_params(axis="both", colors=LABEL_COL, labelsize=7)
    plt.setp(ax.get_xticklabels(), rotation=30, ha="right")

    legend = ax.legend(
        fontsize=7,
        facecolor=GRID_COL,
        edgecolor=GRID_COL,
        labelcolor=LABEL_COL,
    )

    save_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(save_path, dpi=150, bbox_inches="tight", facecolor=BG, pad_inches=0.1)
    print(f"  Saved: {save_path}")
    plt.close(fig)


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------

def run_tf(tf: str) -> None:
    print(f"\n=== {tf} ===")
    out_dir = OUTPUT_BASE / f"NQ_{tf}"
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"  Loading score history...")
    data = score_history(tf)
    print(f"  Loaded {len(data):,} bars")

    runs = extract_regime_runs(data, tf, trend_up=TREND_UP, range_low=RANGE_LOW)
    print(f"  Extracted {len(runs)} regime runs")

    # -- Duration stats --
    stats = regime_duration_stats(runs)
    print("\n  Duration stats:")
    print(stats.to_string())

    # -- Save CSV --
    runs_records = [
        {
            "regime": r.regime,
            "start_ts": r.start_ts,
            "end_ts": r.end_ts,
            "duration_bars": r.duration_bars,
            "timeframe": r.timeframe,
        }
        for r in runs
    ]
    csv_path = out_dir / "regime_runs.csv"
    pd.DataFrame(runs_records).to_csv(csv_path, index=False)
    print(f"  Saved: {csv_path}")

    # -- Plots --
    plot_duration_histogram(
        runs, tf,
        save_path=out_dir / "duration_histogram.png",
    )
    plot_survival_curve(
        runs, tf,
        max_bars=SURVIVAL_MAX,
        save_path=out_dir / "survival_curve.png",
    )
    plot_rolling_median(
        runs, tf,
        window=ROLLING_WINDOW,
        save_path=out_dir / "rolling_median.png",
    )


def main() -> None:
    print("Regime statistics runner")
    print(f"Output base: {OUTPUT_BASE}")
    for tf in TIMEFRAMES:
        run_tf(tf)
    print("\nDone.")


if __name__ == "__main__":
    main()
