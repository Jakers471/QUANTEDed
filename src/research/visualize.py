"""
Visual inspection chart for a single detected fractal pattern.
Dark style matching heatmap.py (BG="#0d1117", TEAL="#00e5cc", RED="#ff2952").
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.collections as mc
from matplotlib.lines import Line2D

import pandas as pd

from src.research.detector import PatternRecord

# ---------------------------------------------------------------------------
# Visual constants
# ---------------------------------------------------------------------------
BG        = "#0d1117"
TEAL      = "#00e5cc"
RED       = "#ff2952"
AMBER     = "#f59e0b"
GREEN     = "#22c55e"
GRAY      = "#4a4a5a"
PRICE_COL = "#c8d6e5"
GRID_COL  = "#1e2530"
LABEL_COL = "#6b7a8d"
SCORE_COL = "#ffffff"

CANDLE_UP    = "#00e5cc"
CANDLE_DOWN  = "#ff2952"
CANDLE_WIDTH = 0.6
WICK_WIDTH   = 0.8

# Regime background alphas
REGIME_BG_ALPHA   = 0.08   # all-window ambient regime tint
PATTERN_BG_ALPHA  = 0.22   # highlighted pattern phases


# ---------------------------------------------------------------------------
# Candlestick drawing helper
# ---------------------------------------------------------------------------

def _draw_candlesticks(ax, window: pd.DataFrame, xs: np.ndarray, price_range: float) -> None:
    """
    Draw OHLC candlesticks on ax.
    price_range: visible y-range used to set minimum body height.
    """
    required = {"open", "high", "low", "close"}
    if not required.issubset(window.columns):
        ax.plot(xs, window["close"].values, color=PRICE_COL, linewidth=0.8)
        return

    opens  = window["open"].values
    highs  = window["high"].values
    lows   = window["low"].values
    closes = window["close"].values

    up_mask = closes >= opens
    min_body = max(price_range * 0.005, 1e-6)

    # Wicks
    wick_segs   = [[(x, lows[i]), (x, highs[i])] for i, x in enumerate(xs)]
    wick_colors = [CANDLE_UP if up_mask[i] else CANDLE_DOWN for i in range(len(xs))]
    wick_col = mc.LineCollection(wick_segs, colors=wick_colors, linewidths=WICK_WIDTH, zorder=2)
    ax.add_collection(wick_col)

    # Bodies
    for i, x in enumerate(xs):
        body_bottom = min(opens[i], closes[i])
        body_height = max(abs(closes[i] - opens[i]), min_body)
        color = CANDLE_UP if up_mask[i] else CANDLE_DOWN
        rect = mpatches.FancyBboxPatch(
            (x - CANDLE_WIDTH / 2, body_bottom),
            CANDLE_WIDTH,
            body_height,
            boxstyle="square,pad=0",
            linewidth=0,
            facecolor=color,
            zorder=3,
        )
        ax.add_patch(rect)


# ---------------------------------------------------------------------------
# Phase-scoped horizontal level line helper
# ---------------------------------------------------------------------------

def _phase_line(ax, x_start: int, x_end: int, y: float, color: str,
                label: str, linestyle: str = "--", linewidth: float = 0.9,
                alpha: float = 0.85) -> Line2D:
    """Draw a horizontal level line only between x_start and x_end."""
    line, = ax.plot(
        [x_start, x_end], [y, y],
        color=color, linestyle=linestyle, linewidth=linewidth,
        alpha=alpha, zorder=4, label=label,
    )
    return line


# ---------------------------------------------------------------------------
# Regime background helper
# ---------------------------------------------------------------------------

def _draw_regime_backgrounds(ax, scores: np.ndarray, alpha: float) -> None:
    """
    Paint ambient regime backgrounds across the full visible window.
    Green = trending up (>0.65), Orange = consolidating (0.35–0.65), Red = trending down (<0.35).
    Groups consecutive same-regime bars into single axvspan calls for performance.
    """
    def _color(s):
        if s > 0.65:
            return GREEN
        if s < 0.35:
            return RED
        return AMBER

    n = len(scores)
    i = 0
    while i < n:
        c = _color(scores[i])
        j = i + 1
        while j < n and _color(scores[j]) == c:
            j += 1
        ax.axvspan(i - 0.5, j - 0.5, alpha=alpha, color=c, zorder=0)
        i = j


# ---------------------------------------------------------------------------
# Single-pattern chart
# ---------------------------------------------------------------------------

def plot_pattern(
    pattern: PatternRecord,
    data: pd.DataFrame,
    context_bars: int = 50,
    save_path: str | None = None,
) -> None:
    """
    Plots a single pattern with context_bars of price on each side.

    Background layers (bottom to top):
      1. Ambient regime tint for every bar (green/orange/red by score)
      2. Stronger highlight on detected move phase (green = bullish) and consol (orange)

    Level lines (phase-scoped):
      - Move high: teal dashed, move_start -> consol_end
      - Move low:  red dashed,  move_start -> consol_end
      - Fib 0.5:   red dotted,  consol_start -> entry
      - Consol high: teal dotted, consol_start -> entry

    Step annotations at the top of the chart mark each detection step:
      Step 1 (move start), Step 2 (consolidation start), Step 3 (entry signal)
    """
    required = {"high", "low", "close", "score"}
    missing = required - set(data.columns)
    if missing:
        raise ValueError(f"plot_pattern() requires columns {required}. Missing: {missing}")

    # --- Slice window around pattern ----------------------------------------
    move_loc  = data.index.searchsorted(pattern.move_start_ts)
    entry_loc = data.index.searchsorted(pattern.entry_ts)

    start_loc = max(0, move_loc - context_bars)
    end_loc   = min(len(data) - 1, entry_loc + context_bars)

    window = data.iloc[start_loc : end_loc + 1].copy()
    n = len(window)
    xs = np.arange(n)

    if n == 0:
        return

    def _rel(ts: pd.Timestamp) -> int:
        idx = window.index.searchsorted(ts)
        return int(min(max(idx, 0), n - 1))

    move_start_x   = _rel(pattern.move_start_ts)
    move_end_x     = _rel(pattern.move_end_ts)
    consol_start_x = _rel(pattern.consol_start_ts)
    consol_end_x   = _rel(pattern.consol_end_ts)
    entry_x        = _rel(pattern.entry_ts)

    # --- Figure setup -------------------------------------------------------
    fig, ax = plt.subplots(figsize=(20, 8), facecolor=BG)
    ax.set_facecolor(BG)

    # --- Price range (needed for candlestick body sizing) -------------------
    y_min_raw = min(window["low"].min(), pattern.move_low, pattern.fib_50)
    y_max_raw = max(window["high"].max(), pattern.move_high, pattern.consol_high)
    y_min = y_min_raw * 0.9993
    y_max = y_max_raw * 1.0007
    price_range = y_max - y_min

    # --- Layer 1: Ambient regime backgrounds (full window) ------------------
    _draw_regime_backgrounds(ax, window["score"].values, alpha=REGIME_BG_ALPHA)

    # --- Layer 2: Pattern phase highlights (stronger tint) ------------------
    # Move direction: green (bullish). Red would be used when down-moves are added.
    ax.axvspan(move_start_x,   move_end_x,   alpha=PATTERN_BG_ALPHA, color=GREEN, zorder=0)
    ax.axvspan(consol_start_x, consol_end_x, alpha=PATTERN_BG_ALPHA, color=AMBER, zorder=0)

    # --- Candlesticks -------------------------------------------------------
    _draw_candlesticks(ax, window, xs, price_range)

    # --- Level lines (phase-scoped) -----------------------------------------
    _phase_line(ax, move_start_x, consol_end_x, pattern.move_high,
                color=TEAL, linestyle="--", linewidth=1.0,
                label=f"Move high ({pattern.move_high:,.1f})")

    _phase_line(ax, move_start_x, consol_end_x, pattern.move_low,
                color=RED, linestyle="--", linewidth=1.0,
                label=f"Move low ({pattern.move_low:,.1f})")

    _phase_line(ax, consol_start_x, entry_x, pattern.fib_50,
                color=RED, linestyle=":", linewidth=1.1,
                label=f"Fib 0.5 ({pattern.fib_50:,.1f})")

    _phase_line(ax, consol_start_x, entry_x, pattern.consol_high,
                color=TEAL, linestyle=":", linewidth=1.1,
                label=f"Consol high ({pattern.consol_high:,.1f})")

    # --- Entry marker -------------------------------------------------------
    ax.axvline(entry_x, color=GREEN, linewidth=1.0, linestyle="--", alpha=0.85, zorder=5)
    ax.plot(entry_x, pattern.entry_price,
            marker="^", markersize=9, color=GREEN, zorder=6,
            label=f"Entry ({pattern.entry_price:,.1f})")

    # --- Step annotations at top of chart -----------------------------------
    step_y = y_max - price_range * 0.02
    step_configs = [
        (move_start_x,   "1  MOVE",  GREEN),
        (consol_start_x, "2  CONSOL", AMBER),
        (entry_x,        "3  ENTRY",  GREEN),
    ]
    for sx, label, color in step_configs:
        ax.axvline(sx, color=color, linewidth=0.5, linestyle=":", alpha=0.4, zorder=4)
        ax.text(
            sx, step_y, label,
            color=color, fontsize=7, fontweight="bold",
            ha="center", va="top", zorder=7,
            bbox=dict(facecolor=BG, edgecolor=color, linewidth=0.5,
                      boxstyle="round,pad=0.2", alpha=0.8),
        )

    # --- Axes limits and formatting -----------------------------------------
    ax.set_xlim(-1, n)
    ax.set_ylim(y_min, y_max)
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:,.0f}"))
    ax.tick_params(colors=LABEL_COL, length=2)
    for spine in ax.spines.values():
        spine.set_color(GRID_COL)
    ax.yaxis.grid(True, color=GRID_COL, linewidth=0.35, alpha=0.4)

    tick_positions = np.linspace(0, n - 1, min(10, n), dtype=int)
    tick_labels    = [str(window.index[i].date()) for i in tick_positions]
    ax.set_xticks(tick_positions)
    ax.set_xticklabels(tick_labels, color=LABEL_COL, fontsize=7, rotation=25, ha="right")

    # --- Score overlay (right y-axis) ---------------------------------------
    ax_score = ax.twinx()
    ax_score.set_facecolor("none")
    ax_score.plot(xs, window["score"].values, color=SCORE_COL,
                  linewidth=0.6, alpha=0.4, zorder=1)
    ax_score.axhline(0.65, color=GREEN, linewidth=0.4, linestyle=":", alpha=0.4)
    ax_score.axhline(0.35, color=RED,   linewidth=0.4, linestyle=":", alpha=0.4)
    ax_score.set_ylim(-0.05, 1.15)
    ax_score.set_yticks([0.0, 0.35, 0.5, 0.65, 1.0])
    ax_score.set_yticklabels(["0.0", "0.35", "0.5", "0.65", "1.0"],
                              color=LABEL_COL, fontsize=7)
    ax_score.tick_params(colors=LABEL_COL, length=2)
    for spine in ax_score.spines.values():
        spine.set_color(GRID_COL)
    ax_score.set_ylabel("Score", color=LABEL_COL, fontsize=8)

    # --- Legend -------------------------------------------------------------
    legend_elements = [
        mpatches.Patch(facecolor=GREEN, alpha=0.40, label=f"Move UP ({pattern.move_duration_bars} bars)"),
        mpatches.Patch(facecolor=AMBER, alpha=0.40, label=f"Consol ({pattern.consol_duration_bars} bars)"),
        Line2D([0], [0], color=TEAL,      linestyle="--", linewidth=1.0, label=f"Move high @ {pattern.move_high:,.1f}"),
        Line2D([0], [0], color=RED,       linestyle="--", linewidth=1.0, label=f"Move low @ {pattern.move_low:,.1f}"),
        Line2D([0], [0], color=RED,       linestyle=":",  linewidth=1.1, label=f"Fib 0.5 @ {pattern.fib_50:,.1f}"),
        Line2D([0], [0], color=TEAL,      linestyle=":",  linewidth=1.1, label=f"Consol high @ {pattern.consol_high:,.1f}"),
        Line2D([0], [0], color=GREEN,     linestyle="--", linewidth=1.0, label=f"Entry @ {pattern.entry_price:,.1f}"),
        Line2D([0], [0], color=SCORE_COL, linewidth=0.6,  alpha=0.6,    label="Score"),
    ]
    ax.legend(
        handles=legend_elements,
        loc="upper left",
        facecolor=BG,
        edgecolor=GRID_COL,
        labelcolor=LABEL_COL,
        fontsize=7,
    )

    # --- Title --------------------------------------------------------------
    title = (
        f"NQ {pattern.timeframe}  |  "
        f"Fib depth: {pattern.fib_retracement_depth:.2f}  |  "
        f"Move: {pattern.move_duration_bars} bars  |  "
        f"Consol: {pattern.consol_duration_bars} bars  |  "
        f"Entry score: {pattern.entry_score:.2f}  |  "
        f"Entry: {pattern.entry_ts.date()}"
    )
    fig.suptitle(title, color=LABEL_COL, fontsize=8.5, y=0.998)

    plt.tight_layout()

    if save_path:
        plt.savefig(save_path, dpi=130, bbox_inches="tight", facecolor=BG, pad_inches=0.1)
    else:
        plt.show()

    plt.close(fig)


# ---------------------------------------------------------------------------
# Batch export
# ---------------------------------------------------------------------------

def plot_all_patterns(
    patterns: list[PatternRecord],
    data: pd.DataFrame,
    output_dir: Path,
    tf: str,
) -> None:
    """
    Saves one PNG per pattern to output_dir/patterns_{tf}/pattern_{i:04d}.png
    """
    output_dir  = Path(output_dir)
    pattern_dir = output_dir / f"patterns_{tf}"
    pattern_dir.mkdir(parents=True, exist_ok=True)

    skipped = 0
    saved   = 0

    for i, pattern in enumerate(patterns):
        dest = pattern_dir / f"pattern_{i:04d}.png"

        if pattern.move_start_ts < data.index[0] or pattern.entry_ts > data.index[-1]:
            skipped += 1
            continue

        start_loc = data.index.searchsorted(pattern.move_start_ts)
        end_loc   = data.index.searchsorted(pattern.entry_ts)
        if (end_loc - start_loc) < 2:
            skipped += 1
            continue

        try:
            plot_pattern(pattern, data, context_bars=50, save_path=str(dest))
            saved += 1
        except Exception as exc:
            print(f"  [WARN] pattern {i:04d} skipped: {exc}")
            skipped += 1

    print(f"  Saved {saved} PNGs to {pattern_dir}  ({skipped} skipped)")
