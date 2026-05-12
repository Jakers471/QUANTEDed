"""
Generates binary decomp score heatmaps for all timeframes.
Run: python src/research/run_heatmap.py

Output: outputs/heatmap_NQ_{tf}.png per timeframe
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from src.research.score.heatmap import plot_heatmap
from src.utils.timeframes import TIMEFRAMES

OUTPUTS = Path(__file__).resolve().parents[3] / "outputs"

# How many bars to show per timeframe — balance detail vs file size
N_BARS = {
    "1min":  5000,
    "5min":  10000,
    "15min": 10000,
    "60min": 5000,
    "1day":  2000,
}

def main() -> None:
    OUTPUTS.mkdir(exist_ok=True)
    for tf in TIMEFRAMES:
        n = N_BARS.get(tf, 5000)
        print(f"Generating {tf} ({n:,} bars)...")
        plot_heatmap(tf, last_n_bars=n, save_path=str(OUTPUTS / f"heatmap_NQ_{tf}.png"))
    print("Done. Outputs in outputs/")

if __name__ == "__main__":
    main()
