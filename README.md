# quanted — NQ Futures Quant Research

---

## Directory Structure

```
quanted/
├── data/
│   ├── nq120.txt              Raw NQ 1min  (NinjaTrader export, read-only)
│   ├── nq520.txt              Raw NQ 5min
│   ├── na1520.txt             Raw NQ 15min
│   ├── nq6020.txt             Raw NQ 60min
│   ├── nq1day20.txt           Raw NQ 1day
│   ├── clean/                 Parquet files produced by the pipeline
│   └── audit/                 Audit reports + pipeline logs
├── src/
│   ├── utils/
│   │   └── timeframes.py      Constants, path configs, NY session filter
│   ├── audit/
│   │   └── run_audit.py       Raw data quality audit
│   ├── pipeline/
│   │   ├── clean.py           Deterministic cleaning pipeline
│   │   └── decisions.md       Why each cleaning decision was made
│   ├── loader/
│   │   ├── loader.py          Leak-proof bar access API
│   │   └── indicators.py      as_of-aware indicator wrappers
│   └── research/
│       ├── params.yaml        All tunable parameters (single source of truth)
│       ├── params.py          Shared YAML loader (lru_cache, reload_params)
│       ├── scoring.py         Binary decomp score — per bar, per timeframe
│       ├── detector.py        FractalDetector state machine + PatternRecord + AbortRecord
│       ├── export.py          patterns_to_dataframe, save_patterns, load_patterns
│       ├── heatmap.py         Heatmap visualization
│       ├── visualize.py       Individual pattern inspection charts
│       ├── visualize_summary.py  summary_dashboard.png + signal_map_{tf}.png
│       ├── regime_stats.py    Regime run extraction + duration stats + survival curves
│       ├── run_heatmap.py     Runner: generate heatmaps
│       ├── run_detector.py    Runner: quick detect + export (no iteration tracking)
│       ├── run_regime_stats.py  Runner: regime stats
│       └── run_iteration.py   Runner: full versioned iteration (use this)
├── tests/
│   ├── test_integrity.py      Clean data quality assertions
│   ├── test_loader_leakage.py Future-data leakage tests
│   ├── test_crossframe.py     Cross-timeframe consistency smoke tests
│   ├── test_scoring.py        Scoring unit tests
│   └── test_detector.py       Detector unit tests
├── outputs/
│   ├── strategy.md            Strategy framework and parameter reference
│   ├── phase2_progress.md     Running build log
│   ├── research_roadmap.md    All research items and status
│   └── iterations/
│       └── iteration_NNN/     One folder per run (auto-numbered)
│           ├── params_snapshot.yaml
│           ├── patterns_NQ_{tf}.csv
│           ├── summary.csv
│           ├── summary_dashboard.png
│           ├── signal_map_{tf}.png
│           └── patterns_{tf}/pattern_NNNN.png
├── requirements.txt
└── README.md
```

---

## Setup

```bash
pip install -r requirements.txt
```

---

## Running an Iteration

Edit `src/research/params.yaml`, then:

```bash
python src/research/run_iteration.py
```

Auto-creates `outputs/iterations/iteration_NNN/` with all outputs for that run.
See `outputs/strategy.md` for what every parameter does.

---

## Other Runners

```bash
python src/pipeline/clean.py          # clean raw data -> parquet
python src/audit/run_audit.py         # audit raw data quality
python src/research/run_heatmap.py    # generate heatmap PNGs
python src/research/run_regime_stats.py  # regime duration stats + survival curves
pytest tests/                         # run all tests
```

---

## Data Loader API

```python
import pandas as pd
from src.loader.loader import get_bars, get_last_closed_bar, get_multi_tf

as_of = pd.Timestamp("2023-06-15 14:30:00", tz="UTC")

bars       = get_bars("1min", as_of)
last_60min = get_last_closed_bar("60min", as_of)
multi      = get_multi_tf(["1min", "5min", "60min"], as_of)
```

`as_of` must always be UTC timezone-aware. `get_bars` returns all bars strictly before `as_of` (no lookahead).

---

## Research vs Backtest Boundary

| Function | Backtest-safe | Notes |
|---|---|---|
| `binary_decomp_score(tf, as_of)` | Yes | Calls `get_bars`, fully leak-proof |
| `score_breakdown(tf, as_of)` | Yes | Same |
| `score_history(tf)` | No | Uses `load_all`, visualization/research only |
| `plot_heatmap(tf, ...)` | No | Visualization only |

---

## Cleaning Decisions

See `src/pipeline/decisions.md` for full rationale.

- Exact duplicates: keep first
- Conflicting duplicates: halt, require inspection
- OHLC violations: drop
- NaN / zero / negative prices: drop
- Timestamps: CT to UTC
- No forward-fill (gap policy is strategy-level)
- DST spring-forward: shift_forward. Fall-back ambiguity: drop.

---

## Data Leakage Rules

- `as_of` is always a UTC timezone-aware `pd.Timestamp`
- Always use `get_bars(tf, as_of)` or `get_last_closed_bar(tf, as_of)`
- Filter is strict `<` not `<=`
- Never slice dataframes directly in research or strategy code
- `get_multi_tf` guarantees all TFs filtered to the same `as_of`
- Indicators in `indicators.py` call `get_bars` internally — safe by construction

---

## Known Limitations

- Data is UNADJUSTED (raw spliced). NQ quarterly roll gaps of 1-11% are present. Long-lookback percentage indicators will be distorted across rollovers. See `src/pipeline/decisions.md`.
- Raw data covers 2005-01-11 to 2025-01-10. To update, re-export from NinjaTrader and re-run `clean.py`.
- Cross-timeframe OHLC consistency not guaranteed (NinjaTrader exports each TF independently).
- DST transition bars (ambiguous CT) are dropped — approximately 2 bars per year on intraday TFs.
