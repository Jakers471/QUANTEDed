"""
Binary decomposition score heatmap.
Dark style with 3-zone regime colors (teal/gray/red).
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import matplotlib.ticker as mticker
from matplotlib.gridspec import GridSpec
import yaml

from src.research.scoring import SCALES, score_history

# Load colors from params.yaml
_PARAMS_PATH = Path(__file__).resolve().parents[2] / "src" / "research" / "params.yaml"
with open(_PARAMS_PATH) as _f:
    _PARAMS = yaml.safe_load(_f)
_VIZ_COLORS = _PARAMS["visualization"]["colors"]

BG        = _VIZ_COLORS["background"]
TEAL      = _VIZ_COLORS["trending_up"]
RED       = _VIZ_COLORS["trending_down"]
GRAY      = _VIZ_COLORS["consolidating"]
PRICE_COL = _VIZ_COLORS["price_line"]
GRID_COL  = "#1e2530"
LABEL_COL = "#6b7a8d"

# Regime thresholds from params.yaml
_TREND_UP  = _PARAMS["regimes"]["trend_up_threshold"]["value"]
_RANGE_LOW = _PARAMS["regimes"]["range_low_threshold"]["value"]


def _score_cmap_3zone() -> tuple[mcolors.ListedColormap, mcolors.BoundaryNorm]:
    """
    3-zone colormap for the score background panel.
    score < RANGE_LOW     -> RED  (trending down)
    RANGE_LOW <= score <= TREND_UP -> GRAY (consolidating)
    score > TREND_UP      -> TEAL (trending up)
    Returns (cmap, norm) pair for use with pcolormesh.
    """
    cmap = mcolors.ListedColormap([RED, GRAY, TEAL], name="score_3zone")
    bounds = [0.0, _RANGE_LOW, _TREND_UP, 1.0]
    norm = mcolors.BoundaryNorm(bounds, ncolors=cmap.N)
    return cmap, norm


def _scale_cmap() -> mcolors.LinearSegmentedColormap:
    """Continuous cmap for per-scale binary rows (0/1 values, red->teal)."""
    return mcolors.LinearSegmentedColormap.from_list(
        "scale_cmap", [RED, "#1a1a2e", TEAL], N=512
    )


def plot_heatmap(
    tf: str,
    last_n_bars: int = 10000,
    save_path: str | None = None,
) -> None:
    """
    Plots binary decomp score heatmap for a single timeframe.

    Top panel:   price line with score-shaded background
    Bottom panel: heatmap — rows = SMA scales, columns = bars, color = score 0/1
    """
    data = score_history(tf, last_n_bars=last_n_bars)
    n = len(data)
    scale_cols = [f"s{s}" for s in SCALES]
    heatmap_arr = data[scale_cols].T.values.astype(float)  # (9, n)
    score_arr = data["score"].values
    xs = np.arange(n)

    score_cmap, score_norm = _score_cmap_3zone()
    scale_cmap = _scale_cmap()

    fig = plt.figure(figsize=(22, 9), facecolor=BG)
    gs = GridSpec(2, 1, height_ratios=[2.5, 1.8], hspace=0.04, figure=fig)
    ax_price = fig.add_subplot(gs[0])
    ax_heat  = fig.add_subplot(gs[1])

    # -- Price panel ----------------------------------------------------------
    ax_price.set_facecolor(BG)

    # Score background: pcolormesh 1-row, 3-zone colormap
    score_bg = score_arr.reshape(1, -1)
    ax_price.pcolormesh(
        np.arange(n + 1), [0, 1], score_bg,
        cmap=score_cmap, norm=score_norm,
        alpha=0.35, shading="flat",
        transform=ax_price.get_xaxis_transform(),
        zorder=0,
    )

    # Normalise price to [0,1] for overlay
    price = data["close"].values
    p_min, p_max = price.min(), price.max()
    price_norm = (price - p_min) / (p_max - p_min) if p_max > p_min else price * 0

    ax_price.plot(xs, price_norm, color=PRICE_COL, linewidth=0.7, alpha=0.95, zorder=2)
    ax_price.set_xlim(0, n)
    ax_price.set_ylim(-0.02, 1.02)
    ax_price.set_yticks([0, 0.5, 1.0])
    ax_price.set_yticklabels(
        [f"{p_min:,.0f}", f"{(p_min+p_max)/2:,.0f}", f"{p_max:,.0f}"],
        color=LABEL_COL, fontsize=7,
    )
    ax_price.tick_params(axis="x", labelbottom=False, colors=LABEL_COL, length=2)
    ax_price.tick_params(axis="y", colors=LABEL_COL, length=2)
    for spine in ax_price.spines.values():
        spine.set_color(GRID_COL)
    ax_price.yaxis.grid(True, color=GRID_COL, linewidth=0.4, alpha=0.5)

    # Overall score line
    ax_score = ax_price.twinx()
    ax_score.set_facecolor("none")
    ax_score.plot(xs, score_arr, color="#ffffff", linewidth=0.5, alpha=0.4, zorder=3)
    ax_score.set_ylim(-0.1, 1.1)
    ax_score.set_yticks([0, 0.5, 1.0])
    ax_score.set_yticklabels(["0.0", "0.5", "1.0"], color=LABEL_COL, fontsize=7)
    ax_score.tick_params(colors=LABEL_COL, length=2)
    for spine in ax_score.spines.values():
        spine.set_color(GRID_COL)

    # -- Heatmap panel --------------------------------------------------------
    ax_heat.set_facecolor(BG)
    ax_heat.pcolormesh(
        np.arange(n + 1), np.arange(len(SCALES) + 1),
        heatmap_arr,
        cmap=scale_cmap, vmin=0, vmax=1, shading="flat",
    )
    ax_heat.set_xlim(0, n)
    ax_heat.set_ylim(0, len(SCALES))
    ax_heat.set_yticks(np.arange(len(SCALES)) + 0.5)
    ax_heat.set_yticklabels(
        [f"SMA {s:>4}" for s in SCALES],
        color=LABEL_COL, fontsize=7, fontfamily="monospace",
    )

    # X-axis: show dates instead of bar numbers
    tick_positions = np.linspace(0, n - 1, min(10, n), dtype=int)
    tick_labels = [str(data.index[i].date()) for i in tick_positions]
    ax_heat.set_xticks(tick_positions)
    ax_heat.set_xticklabels(tick_labels, color=LABEL_COL, fontsize=7, rotation=30, ha="right")
    ax_heat.tick_params(colors=LABEL_COL, length=2)
    for spine in ax_heat.spines.values():
        spine.set_color(GRID_COL)

    # -- Title ----------------------------------------------------------------
    date_range = f"{data.index[0].date()} to {data.index[-1].date()}"
    scales_str = f"Scales: {SCALES}"
    fig.suptitle(
        f"NQ {tf}  |  Binary Decomposition Score  |  {n:,} bars  |  {date_range}  |  {scales_str}",
        color=LABEL_COL, fontsize=8, y=0.995,
    )

    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches="tight", facecolor=BG, pad_inches=0.1)
        print(f"  Saved: {save_path}")
    else:
        plt.show()
    plt.close(fig)
