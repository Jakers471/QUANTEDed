# quanted — NQ Futures Quant Research

## Directory Structure

```
quanted/
├── data/
│   ├── nq120.txt         # Raw NQ 1min  (NinjaTrader export, read-only)
│   ├── nq520.txt         # Raw NQ 5min
│   ├── na1520.txt        # Raw NQ 15min
│   ├── nq6020.txt        # Raw NQ 60min
│   ├── nq1day20.txt      # Raw NQ 1day
│   ├── clean/            # Parquet files produced by pipeline
│   └── audit/            # Audit reports + pipeline logs
├── src/
│   ├── utils/
│   │   └── timeframes.py     # Constants, path configs, helpers
│   ├── audit/
│   │   └── run_audit.py      # Raw data quality audit
│   ├── pipeline/
│   │   ├── clean.py          # Deterministic cleaning pipeline
│   │   └── decisions.md      # Why each cleaning decision was made
│   └── loader/
│       ├── loader.py         # Leak-proof bar access API
│       └── indicators.py     # as_of-aware indicator wrappers
├── tests/
│   ├── test_integrity.py     # Clean data quality assertions
│   ├── test_loader_leakage.py# Future-data leakage tests
│   └── test_crossframe.py    # Cross-timeframe consistency smoke tests
├── outputs/                  # Strategy outputs, charts, results
├── requirements.txt
└── README.md
```

## Install

```bash
pip install -r requirements.txt
```

## Run the Audit

Reads the raw `.txt` files in `data/`. Writes one markdown report per timeframe to `data/audit/`.

```bash
python src/audit/run_audit.py
```

Output: `data/audit/NQ_{tf}_audit.md` for each timeframe, plus a summary table printed to stdout.

## Run the Cleaning Pipeline

Reads raw `.txt` files from `data/`, applies deterministic cleaning, writes UTC-indexed parquet to `data/clean/`.

```bash
python src/pipeline/clean.py
```

Output: `data/clean/NQ_{tf}_clean.parquet` and `data/audit/NQ_{tf}_pipeline.log` per timeframe.

The pipeline is idempotent: running it twice produces identical output.

## Run Tests

```bash
pytest tests/
```

Tests skip gracefully if clean data has not been generated yet.

## Phase 2 — Pattern Detection Research

See `outputs/phase2_progress.md` for the full running log of what's been built and what's next.

### Binary Decomposition Score

Each timeframe gets an independent score (0.0–1.0) representing how trending it is.
Score = fraction of 9 SMA scales `[2, 4, 8, 16, 32, 64, 128, 256, 512]` where `close > SMA(scale)`.

```python
from src.research.scoring import binary_decomp_score, score_breakdown
import pandas as pd

as_of = pd.Timestamp("2023-07-01 00:00:00", tz="UTC")
score = binary_decomp_score("60min", as_of)          # → 0.78
detail = score_breakdown("60min", as_of)              # per-scale breakdown dict
```

### Generate Heatmaps

```bash
python src/research/run_heatmap.py
```

Output: `outputs/heatmap_NQ_{tf}.png` — dark teal/red heatmap per timeframe.
Top panel: price + score background. Bottom panel: per-scale binary grid over time.

### Research vs Backtest boundary

| Function | Backtest-safe | Notes |
|---|---|---|
| `binary_decomp_score(tf, as_of)` | Yes | Calls `get_bars`, fully leak-proof |
| `score_breakdown(tf, as_of)` | Yes | Same |
| `score_history(tf)` | **No** | Uses `load_all`, viz/research only |
| `plot_heatmap(tf, ...)` | **No** | Visualization only |

## Data Loader API

```python
import pandas as pd
from src.loader.loader import get_bars, get_last_closed_bar, get_multi_tf

# as_of must always be UTC timezone-aware
as_of = pd.Timestamp("2023-06-15 14:30:00", tz="UTC")

# All 1-minute bars strictly before as_of
bars = get_bars("1min", as_of)

# The last fully-closed 60-minute bar as of as_of
last_hourly = get_last_closed_bar("60min", as_of)
print(last_hourly["close"])

# Last closed bar on multiple timeframes simultaneously
multi = get_multi_tf(["1min", "5min", "60min"], as_of)
print(multi["5min"]["close"])

# Indicator wrappers — enforce as_of internally
from src.loader.indicators import sma, ema, atr, rolling_high, rolling_low

ma20    = sma("5min", as_of, period=20)
ema9    = ema("5min", as_of, period=9)
atr14   = atr("60min", as_of, period=14)
high50  = rolling_high("1day", as_of, period=50)
low50   = rolling_low("1day", as_of, period=50)
```

## Cleaning Decisions

See [`src/pipeline/decisions.md`](src/pipeline/decisions.md) for the full rationale behind every cleaning choice.

Summary:
- Exact duplicates: keep first (no information loss)
- Conflicting duplicates: halt and require manual inspection
- OHLC violations: drop (repair is speculative)
- NaN rows: drop
- Zero/negative prices: drop
- Timestamps: localize CT → convert to UTC, store UTC
- No forward-fill — gap policy is a strategy-level decision
- DST spring-forward: shift_forward; fall-back ambiguity: drop NaT rows

## Data Leakage Checklist

Every research script and strategy must follow these rules:

- [ ] `as_of` is always a UTC timezone-aware `pd.Timestamp` — never naive
- [ ] Use `get_bars(tf, as_of)` or `get_last_closed_bar(tf, as_of)` — never slice dataframes directly
- [ ] Never use `<=` when filtering by bar close time — always `<`
- [ ] Never access `df.iloc[-1]` on a full unfiltered frame inside a loop — always pass `as_of`
- [ ] Never cache a slice of bars at one `as_of` and reuse it at a later `as_of`
- [ ] When iterating a backtest, advance `as_of` only to bar close times — never to bar open times
- [ ] `get_multi_tf` guarantees all timeframes are filtered to the same `as_of` — always prefer it over calling each tf separately
- [ ] Indicators in `indicators.py` call `get_bars` internally — they are safe by construction

## Known Limitations

- **Data is UNADJUSTED (raw spliced).** NQ quarterly roll gaps of 1–11% are present at contract boundaries. Long-lookback percentage-based indicators (200-day SMA, ATR as % of price) will be distorted across rollovers. Session/structure/pattern work is unaffected. See `src/pipeline/decisions.md` for full details and the back-adjustment plan.
- Raw data covers 2005-01-11 to 2025-01-10 for all 5 timeframes (NinjaTrader `.txt` exports in `data/`). To update, re-export from NinjaTrader, replace the files, and re-run `clean.py`.
- The pipeline reads the per-timeframe exports from NinjaTrader. If NinjaTrader re-exports with updated data, re-run the pipeline.
- Cross-timeframe OHLC and volume consistency is not guaranteed because NinjaTrader exports each timeframe independently. Use `test_crossframe.py` smoke tests to detect large discrepancies.
- DST transition bars (ambiguous CT timestamps) are dropped. This affects approximately 2 bars per year on intraday timeframes.
- The audit's "expected bar count" check does not account for exchange holidays, emergency closures, or scheduled maintenance windows. Gap counts will include legitimate non-trading periods.

NEVER USE EMOJIS EVER ANYWHERRE!!!!!!! NO ENCODING ISSUES. 