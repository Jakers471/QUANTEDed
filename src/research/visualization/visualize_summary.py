"""
Iteration-level summary visuals — zoomed-out view across all signals.

Two outputs per run:
  summary_dashboard.png  — pattern stats across all timeframes
  signal_map_{tf}.png    — per-TF lifecycle map: funnel, death reasons,
                           consol survival, and compact Gantt of recent signals
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from collections import Counter

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.ticker as ticker
from matplotlib.lines import Line2D

import pandas as pd

from src.research.detection.detector import PatternRecord, AbortRecord

# ---------------------------------------------------------------------------
# Visual constants (same palette as visualize.py)
# ---------------------------------------------------------------------------
BG        = "#0d1117"
TEAL      = "#00e5cc"
RED       = "#ff2952"
AMBER     = "#f59e0b"
GREEN     = "#22c55e"
GRAY      = "#4a4a5a"
GRID_COL  = "#1e2530"
LABEL_COL = "#6b7a8d"
WHITE     = "#c8d6e5"

REGIME_BG_ALPHA = 0.08

DEATH_COLORS = {
    "fib_invalidated": RED,
    "timeout":         AMBER,
    "reversal":        "#9b59b6",   # purple
    "move_too_short":  GRAY,
}

TF_ORDER = ["1min", "5min", "15min", "60min", "1day"]


# ---------------------------------------------------------------------------
# Summary dashboard
# ---------------------------------------------------------------------------

def plot_summary_dashboard(
    patterns_by_tf: dict[str, list[PatternRecord]],
    aborts_by_tf:   dict[str, list[AbortRecord]],
    run_name: str,
    save_path: Path,
) -> None:
    """
    5-panel summary dashboard saved to save_path.

    Panels:
      1 Signal funnel per TF (completed vs aborted breakdown)
      2 Fib depth distribution per TF (box)
      3 Move duration per TF (box)
      4 Consol duration per TF (box)
      5 Quarterly pattern frequency (line, completed only)
    """
    tfs = [tf for tf in TF_ORDER if tf in patterns_by_tf]
    if not tfs:
        return

    fig = plt.figure(figsize=(22, 14), facecolor=BG)
    fig.suptitle(f"{run_name} — Signal Summary Dashboard",
                 color=WHITE, fontsize=11, y=0.995)

    gs = fig.add_gridspec(3, 3, hspace=0.45, wspace=0.35,
                          left=0.07, right=0.97, top=0.96, bottom=0.06)

    ax_funnel   = fig.add_subplot(gs[0, :])   # full top row
    ax_fib      = fig.add_subplot(gs[1, 0])
    ax_move     = fig.add_subplot(gs[1, 1])
    ax_consol   = fig.add_subplot(gs[1, 2])
    ax_timeline = fig.add_subplot(gs[2, :])   # full bottom row

    for ax in [ax_funnel, ax_fib, ax_move, ax_consol, ax_timeline]:
        ax.set_facecolor(BG)
        ax.tick_params(colors=LABEL_COL, length=2)
        for spine in ax.spines.values():
            spine.set_color(GRID_COL)
        ax.yaxis.grid(True, color=GRID_COL, linewidth=0.3, alpha=0.5)
        ax.set_axisbelow(True)

    # --- Panel 1: Signal funnel per TF ---
    funnel_data = []
    for tf in tfs:
        p = patterns_by_tf.get(tf, [])
        a = aborts_by_tf.get(tf, [])
        completed   = len(p)
        ab_consol   = sum(1 for x in a if x.reached_consol)
        ab_move     = sum(1 for x in a if not x.reached_consol)
        funnel_data.append((tf, completed, ab_consol, ab_move))

    x = np.arange(len(tfs))
    w = 0.25
    ax_funnel.bar(x - w, [d[1] for d in funnel_data], w, label="Completed (entry)",      color=GREEN, alpha=0.85)
    ax_funnel.bar(x,     [d[2] for d in funnel_data], w, label="Died in consolidation",  color=AMBER, alpha=0.85)
    ax_funnel.bar(x + w, [d[3] for d in funnel_data], w, label="Died in move / too short", color=RED, alpha=0.85)
    ax_funnel.set_xticks(x)
    ax_funnel.set_xticklabels(tfs, color=LABEL_COL)
    ax_funnel.set_title("Signal Funnel — Completed vs Aborted per Timeframe",
                        color=LABEL_COL, fontsize=9)
    ax_funnel.legend(facecolor=BG, edgecolor=GRID_COL, labelcolor=LABEL_COL, fontsize=7)
    ax_funnel.yaxis.set_major_formatter(ticker.FuncFormatter(lambda v, _: f"{int(v):,}"))

    # --- Panels 2-4: Box plots ---
    def _box(ax, field, title):
        data_per_tf = []
        labels = []
        for tf in tfs:
            vals = [getattr(p, field) for p in patterns_by_tf.get(tf, [])]
            if vals:
                data_per_tf.append(vals)
                labels.append(tf)
        if not data_per_tf:
            return
        bp = ax.boxplot(data_per_tf, patch_artist=True, notch=False,
                        medianprops=dict(color=GREEN, linewidth=1.5),
                        boxprops=dict(facecolor=GRID_COL, color=TEAL, linewidth=0.7),
                        whiskerprops=dict(color=LABEL_COL, linewidth=0.7),
                        capprops=dict(color=LABEL_COL, linewidth=0.7),
                        flierprops=dict(marker=".", color=LABEL_COL, markersize=2, alpha=0.3))
        ax.set_xticklabels(labels, color=LABEL_COL, fontsize=8)
        ax.set_title(title, color=LABEL_COL, fontsize=8)

    _box(ax_fib,    "fib_retracement_depth", "Fib Depth Distribution")
    _box(ax_move,   "move_duration_bars",    "Move Duration (bars)")
    _box(ax_consol, "consol_duration_bars",  "Consol Duration (bars)")

    # --- Panel 5: Quarterly pattern frequency (completed) ---
    # Use 1min as the reference TF if present, else first available
    ref_tf = "1min" if "1min" in tfs else tfs[0]
    ref_patterns = patterns_by_tf.get(ref_tf, [])
    ref_aborts   = aborts_by_tf.get(ref_tf, [])

    if ref_patterns or ref_aborts:
        all_entries = (
            [(p.entry_ts, "completed") for p in ref_patterns] +
            [(a.abort_ts, a.death_reason) for a in ref_aborts]
        )
        ts_df = pd.DataFrame(all_entries, columns=["ts", "type"])
        ts_df["quarter"] = ts_df["ts"].dt.to_period("Q")
        counts = ts_df.groupby(["quarter", "type"]).size().unstack(fill_value=0)

        quarters = [str(q) for q in counts.index]
        qx = np.arange(len(quarters))

        bottom = np.zeros(len(quarters))
        for col, color in [
            ("completed",     GREEN),
            ("fib_invalidated", RED),
            ("timeout",         AMBER),
            ("reversal",        "#9b59b6"),
            ("move_too_short",  GRAY),
        ]:
            if col in counts.columns:
                vals = counts[col].values
                ax_timeline.bar(qx, vals, bottom=bottom, color=color, alpha=0.8, label=col)
                bottom += vals

        step = max(1, len(quarters) // 12)
        ax_timeline.set_xticks(qx[::step])
        ax_timeline.set_xticklabels(quarters[::step], color=LABEL_COL, fontsize=6, rotation=30, ha="right")
        ax_timeline.set_title(f"Signal Frequency Over Time ({ref_tf}) — Stacked by Outcome",
                              color=LABEL_COL, fontsize=9)
        ax_timeline.legend(facecolor=BG, edgecolor=GRID_COL, labelcolor=LABEL_COL, fontsize=7)
        ax_timeline.yaxis.set_major_formatter(ticker.FuncFormatter(lambda v, _: f"{int(v):,}"))

    plt.savefig(save_path, dpi=120, bbox_inches="tight", facecolor=BG, pad_inches=0.1)
    plt.close(fig)
    print(f"  Saved summary dashboard: {save_path.name}")


# ---------------------------------------------------------------------------
# Signal map (per timeframe)
# ---------------------------------------------------------------------------

def plot_signal_map(
    tf: str,
    patterns: list[PatternRecord],
    aborts:   list[AbortRecord],
    run_name: str,
    save_path: Path,
) -> None:
    """
    4-panel signal lifecycle map for one timeframe.

    Left (large): Compact Gantt — most recent 200 attempts.
      Green bar = move phase, Orange bar = consolidation phase.
      Green ▲ = entry signal fired. Colored ✕ = died (color = death reason).

    Top-right:    Funnel (moves started → reached consol → entry fired).
    Mid-right:    Death reason breakdown (bar chart).
    Bottom-right: Consol bars survived histogram (aborted vs completed overlay).
    """
    total_attempts = len(patterns) + len(aborts)
    if total_attempts == 0:
        return

    # Build unified attempt list sorted by start time
    # Each item: (start_ts, move_bars, consol_bars, reached_consol, completed, death_reason)
    attempts = []
    for p in patterns:
        attempts.append(dict(
            start_ts=p.move_start_ts,
            move_bars=p.move_duration_bars,
            consol_bars=p.consol_duration_bars,
            reached_consol=True,
            completed=True,
            death_reason=None,
        ))
    for a in aborts:
        attempts.append(dict(
            start_ts=a.move_start_ts,
            move_bars=a.move_duration_bars,
            consol_bars=a.consol_bars_survived,
            reached_consol=a.reached_consol,
            completed=False,
            death_reason=a.death_reason,
        ))

    attempts.sort(key=lambda x: x["start_ts"])
    gantt_sample = attempts[-200:]   # most recent 200 for readability

    # --- Layout ---
    fig = plt.figure(figsize=(24, 14), facecolor=BG)
    fig.suptitle(f"{run_name} — Signal Lifecycle Map  [{tf}]  "
                 f"({len(patterns):,} completed  /  {len(aborts):,} aborted  /  {total_attempts:,} total attempts)",
                 color=WHITE, fontsize=10, y=0.998)

    gs = fig.add_gridspec(3, 5, hspace=0.5, wspace=0.4,
                          left=0.04, right=0.98, top=0.96, bottom=0.04)

    ax_gantt  = fig.add_subplot(gs[:, :3])   # full left column
    ax_funnel = fig.add_subplot(gs[0, 3:])
    ax_death  = fig.add_subplot(gs[1, 3:])
    ax_hist   = fig.add_subplot(gs[2, 3:])

    for ax in [ax_gantt, ax_funnel, ax_death, ax_hist]:
        ax.set_facecolor(BG)
        ax.tick_params(colors=LABEL_COL, length=2)
        for spine in ax.spines.values():
            spine.set_color(GRID_COL)
        ax.set_axisbelow(True)

    # ---- Gantt ----
    n = len(gantt_sample)
    row_h = 0.75

    for i, att in enumerate(gantt_sample):
        y = i * 1.0
        # Move bar (green)
        ax_gantt.broken_barh([(0, att["move_bars"])], (y, row_h),
                             facecolors=GREEN, alpha=0.7, linewidth=0)
        # Consol bar
        if att["consol_bars"] > 0:
            c_color = AMBER if att["reached_consol"] else GRAY
            ax_gantt.broken_barh(
                [(att["move_bars"], att["consol_bars"])], (y, row_h),
                facecolors=c_color, alpha=0.7, linewidth=0
            )
        end_x = att["move_bars"] + att["consol_bars"]
        # Outcome marker
        if att["completed"]:
            ax_gantt.plot(end_x, y + row_h / 2, marker="^", markersize=5,
                         color=GREEN, zorder=5)
        else:
            dc = DEATH_COLORS.get(att["death_reason"], GRAY)
            ax_gantt.plot(end_x, y + row_h / 2, marker="x", markersize=5,
                         color=dc, markeredgewidth=1.2, zorder=5)

    ax_gantt.set_ylim(-0.5, n)
    ax_gantt.set_xlabel("Bars elapsed from move start", color=LABEL_COL, fontsize=8)
    ax_gantt.set_ylabel(f"Signal index (most recent {n})", color=LABEL_COL, fontsize=8)
    ax_gantt.set_title("Signal Gantt — Each row = one attempt  "
                       "( ▲ entry fired  |  ✕ died )",
                       color=LABEL_COL, fontsize=8)
    ax_gantt.xaxis.grid(True, color=GRID_COL, linewidth=0.3, alpha=0.5)

    legend_els = [
        mpatches.Patch(facecolor=GREEN, alpha=0.7, label="Move phase"),
        mpatches.Patch(facecolor=AMBER, alpha=0.7, label="Consol phase"),
        Line2D([0],[0], marker="^", color="none", markerfacecolor=GREEN, markersize=7, label="Entry fired"),
    ] + [
        Line2D([0],[0], marker="x", color="none", markeredgecolor=c, markersize=7,
               markeredgewidth=1.5, label=f"Died: {reason}")
        for reason, c in DEATH_COLORS.items()
    ]
    ax_gantt.legend(handles=legend_els, loc="lower right",
                    facecolor=BG, edgecolor=GRID_COL, labelcolor=LABEL_COL, fontsize=6)

    # ---- Funnel ----
    n_moves     = total_attempts
    n_consol    = len(patterns) + sum(1 for a in aborts if a.reached_consol)
    n_completed = len(patterns)
    funnel_vals   = [n_moves, n_consol, n_completed]
    funnel_labels = ["Moves started", "Reached consolidation", "Entry fired"]
    funnel_colors = [RED, AMBER, GREEN]
    bars = ax_funnel.barh(funnel_labels, funnel_vals, color=funnel_colors, alpha=0.85)
    for bar, val in zip(bars, funnel_vals):
        ax_funnel.text(bar.get_width() * 1.01, bar.get_y() + bar.get_height() / 2,
                       f"{val:,}", va="center", ha="left", color=WHITE, fontsize=8)
    ax_funnel.set_title("Signal Funnel", color=LABEL_COL, fontsize=8)
    ax_funnel.xaxis.set_major_formatter(ticker.FuncFormatter(lambda v, _: f"{int(v):,}"))
    ax_funnel.xaxis.grid(True, color=GRID_COL, linewidth=0.3, alpha=0.5)

    # ---- Death reason breakdown ----
    reason_counts = Counter(a.death_reason for a in aborts)
    reasons = list(DEATH_COLORS.keys())
    counts  = [reason_counts.get(r, 0) for r in reasons]
    colors  = [DEATH_COLORS[r] for r in reasons]
    b2 = ax_death.bar(range(len(reasons)), counts, color=colors, alpha=0.85)
    for bar, val in zip(b2, counts):
        if val > 0:
            ax_death.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + max(counts, default=1) * 0.01,
                          f"{val:,}", ha="center", va="bottom", color=WHITE, fontsize=7)
    ax_death.set_title("Abort Reasons", color=LABEL_COL, fontsize=8)
    ax_death.set_xticks(range(len(reasons)))
    ax_death.set_xticklabels(reasons, color=LABEL_COL, fontsize=7, rotation=15, ha="right")
    ax_death.yaxis.set_major_formatter(ticker.FuncFormatter(lambda v, _: f"{int(v):,}"))
    ax_death.yaxis.grid(True, color=GRID_COL, linewidth=0.3, alpha=0.5)

    # ---- Consol bars survived histogram ----
    aborted_consol_bars   = [a.consol_bars_survived for a in aborts if a.reached_consol]
    completed_consol_bars = [p.consol_duration_bars for p in patterns]
    bins = np.linspace(0, max(
        max(aborted_consol_bars, default=1),
        max(completed_consol_bars, default=1)
    ), 40)
    if aborted_consol_bars:
        ax_hist.hist(aborted_consol_bars, bins=bins, color=RED,   alpha=0.6, label="Aborted")
    if completed_consol_bars:
        ax_hist.hist(completed_consol_bars, bins=bins, color=GREEN, alpha=0.6, label="Completed")
    ax_hist.set_xlabel("Consolidation bars", color=LABEL_COL, fontsize=7)
    ax_hist.set_title("Consol Bars: Aborted vs Completed", color=LABEL_COL, fontsize=8)
    ax_hist.legend(facecolor=BG, edgecolor=GRID_COL, labelcolor=LABEL_COL, fontsize=7)
    ax_hist.yaxis.grid(True, color=GRID_COL, linewidth=0.3, alpha=0.5)

    plt.savefig(save_path, dpi=120, bbox_inches="tight", facecolor=BG, pad_inches=0.1)
    plt.close(fig)
    print(f"  Saved signal map: {save_path.name}")


# ---------------------------------------------------------------------------
# Detection overlay (zoomed-out candlestick + all attempts painted on price)
# ---------------------------------------------------------------------------

def plot_detection_overlay(
    tf: str,
    data: pd.DataFrame,
    patterns: list[PatternRecord],
    aborts: list[AbortRecord],
    run_name: str,
    save_path: "Path",
    window_bars: int = 1000,
    n_panels: int = 6,
) -> None:
    """
    6-panel (2 rows x 3 cols) detection overlay.

    Panels are evenly distributed across the full data history so you see
    detector activity at different points in time — not just the recent period.
    Each panel shows window_bars of candlestick data with every detection attempt
    painted as phase bands + outcome markers.

    Green bands  = move phase (alpha accumulates with density)
    Amber bands  = consolidation phase
    Green  ^     = entry signal fired
    Colored x    = aborted (color = death reason)
    """
    from src.research.visualization.visualize import _draw_candlesticks, _draw_regime_backgrounds

    total = len(data)
    if total == 0:
        return

    # Clamp panel bars so we never exceed total data
    panel_bars = min(window_bars, total)

    # Start indices evenly distributed so panels span the full history.
    # Last panel always ends at the final bar.
    if total <= panel_bars:
        starts = [0] * n_panels
    else:
        starts = np.linspace(0, total - panel_bars, n_panels, dtype=int).tolist()

    n_cols = 3
    n_rows = (n_panels + n_cols - 1) // n_cols

    fig, axes = plt.subplots(
        n_rows, n_cols,
        figsize=(28, 6 * n_rows),
        facecolor=BG,
    )
    fig.subplots_adjust(hspace=0.38, wspace=0.08, left=0.04, right=0.97,
                        top=0.93, bottom=0.05)

    axes_flat = axes.flatten() if n_panels > 1 else [axes]

    total_completed = 0
    total_aborted   = 0

    for panel_idx, start in enumerate(starts):
        ax = axes_flat[panel_idx]
        ax.set_facecolor(BG)

        end    = min(start + panel_bars, total)
        window = data.iloc[start:end].copy()
        n      = len(window)
        xs     = np.arange(n)

        win_start = window.index[0]
        win_end   = window.index[-1]

        def _rel(ts, _n=n, _w=window):
            idx = _w.index.searchsorted(ts)
            return int(min(max(idx, 0), _n - 1))

        y_min = window["low"].min()  * 0.9993
        y_max = window["high"].max() * 1.0007
        price_range = y_max - y_min

        _draw_regime_backgrounds(ax, window["score"].values, alpha=REGIME_BG_ALPHA)

        n_completed = 0
        n_aborted   = 0

        for p in patterns:
            if p.entry_ts < win_start or p.move_start_ts > win_end:
                continue
            n_completed += 1
            ax.axvspan(_rel(p.move_start_ts),   _rel(p.move_end_ts),
                       alpha=0.10, color=GREEN, zorder=0)
            ax.axvspan(_rel(p.consol_start_ts), _rel(p.consol_end_ts),
                       alpha=0.10, color=AMBER, zorder=0)
            ex = _rel(p.entry_ts)
            ax.plot(ex, window["close"].iloc[min(ex, n - 1)],
                    marker="^", markersize=5, color=GREEN, zorder=5, markeredgewidth=0)

        for a in aborts:
            if a.abort_ts < win_start or a.move_start_ts > win_end:
                continue
            n_aborted += 1
            move_end_ts = a.move_end_ts if a.reached_consol else a.abort_ts
            ax.axvspan(_rel(a.move_start_ts), _rel(move_end_ts),
                       alpha=0.06, color=GREEN, zorder=0)
            if a.reached_consol and a.consol_start_ts:
                ax.axvspan(_rel(a.consol_start_ts), _rel(a.abort_ts),
                           alpha=0.06, color=AMBER, zorder=0)
            ax_x = _rel(a.abort_ts)
            dc = DEATH_COLORS.get(a.death_reason, GRAY)
            ax.plot(ax_x, window["close"].iloc[min(ax_x, n - 1)],
                    marker="x", markersize=4, color=dc, markeredgewidth=1.0, zorder=5)

        total_completed += n_completed
        total_aborted   += n_aborted

        _draw_candlesticks(ax, window, xs, price_range)

        # Score overlay (right axis)
        ax_s = ax.twinx()
        ax_s.set_facecolor("none")
        ax_s.plot(xs, window["score"].values, color=WHITE,
                  linewidth=0.5, alpha=0.30, zorder=1)
        ax_s.axhline(0.65, color=GREEN, linewidth=0.4, linestyle=":", alpha=0.35)
        ax_s.axhline(0.35, color=RED,   linewidth=0.4, linestyle=":", alpha=0.35)
        ax_s.set_ylim(-0.05, 1.15)
        ax_s.set_yticks([])
        for spine in ax_s.spines.values():
            spine.set_color(GRID_COL)

        # Axes
        ax.set_xlim(-1, n)
        ax.set_ylim(y_min, y_max)
        ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:,.0f}"))
        ax.tick_params(colors=LABEL_COL, length=2, labelsize=6)
        for spine in ax.spines.values():
            spine.set_color(GRID_COL)
        ax.yaxis.grid(True, color=GRID_COL, linewidth=0.3, alpha=0.4)

        tick_positions = np.linspace(0, n - 1, min(5, n), dtype=int)
        tick_labels    = [str(window.index[i].date()) for i in tick_positions]
        ax.set_xticks(tick_positions)
        ax.set_xticklabels(tick_labels, color=LABEL_COL, fontsize=6, rotation=20, ha="right")

        # Panel subtitle
        ax.set_title(
            f"{win_start.date()} — {win_end.date()}  "
            f"| {n_completed} fired  {n_aborted} aborted",
            color=LABEL_COL, fontsize=7, pad=3,
        )

    # Hide unused panels
    for i in range(n_panels, len(axes_flat)):
        axes_flat[i].set_visible(False)

    # Shared legend on the figure
    legend_els = [
        mpatches.Patch(facecolor=GREEN, alpha=0.5, label="Move phase"),
        mpatches.Patch(facecolor=AMBER, alpha=0.5, label="Consol phase"),
        Line2D([0], [0], marker="^", color="none", markerfacecolor=GREEN,
               markersize=7, label="Entry fired"),
    ] + [
        Line2D([0], [0], marker="x", color="none", markeredgecolor=c,
               markersize=7, markeredgewidth=1.5, label=f"Died: {reason}")
        for reason, c in DEATH_COLORS.items()
    ]
    fig.legend(
        handles=legend_els,
        loc="lower center",
        ncol=len(legend_els),
        facecolor=BG, edgecolor=GRID_COL, labelcolor=LABEL_COL, fontsize=7,
        bbox_to_anchor=(0.5, 0.0),
    )

    fig.suptitle(
        f"{run_name}  [{tf}]  Detection Overlay — {n_panels} sample periods  |  "
        f"{data.index[0].date()} to {data.index[-1].date()}  |  "
        f"{total_completed:,} completed  /  {total_aborted:,} aborted shown",
        color=LABEL_COL, fontsize=9, y=0.97,
    )

    plt.savefig(save_path, dpi=120, bbox_inches="tight", facecolor=BG, pad_inches=0.15)
    plt.close(fig)
    print(f"  Saved detection overlay: {save_path.name}")
