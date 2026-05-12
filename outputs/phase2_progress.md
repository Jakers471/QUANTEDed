# Phase 2 Progress Log

---

## ARCHITECTURE — Read This First

**Deployment note (no decision needed yet):**
The Python project is the research and specification layer — not the deployment.
When the strategy is ready to go live, three options exist: NinjaTrader (re-implement core in C#),
n8n + Python (wrap detector as a callable script/endpoint, n8n schedules and routes),
or Cloud Python (deploy directly, no n8n). All three are viable. The research architecture
supports all of them because the portable core (scoring + detection) is isolated from
visualization and infrastructure. Full detail in `outputs/strategy.md` and `outputs/research_roadmap.md`.

---

**One theory. Multiple outputs.**

The binary decomposition score is the single underlying engine for everything in this project.
The heatmap, the pattern detector, the regime stats, and eventually the strategy — they all
speak the same language. Nothing here is a separate competing system.

```
Binary Decomp Score  (per bar, per timeframe, fully independent)
  score = fraction of 9 SMA scales where close > SMA(scale)
  scales = [2, 4, 8, 16, 32, 64, 128, 256, 512]
  range = 0.0 (fully below all SMAs) to 1.0 (fully above all SMAs)
         │
         ├── Heatmap             visualizes score over time — teal/gray/red per regime zone
         │
         ├── Regime Stats        measures empirical regime persistence (descriptive, not optimization)
         │
         └── Pattern Detector    sequences score regimes into tradeable patterns
                  │
                  ├── score > 0.65 sustained  →  "move up" phase
                  ├── score 0.35–0.65         →  "consolidation" phase
                  ├── Fibonacci geometry       validates consolidation depth (< 0.5 fib)
                  └── score > 0.65 + breakout →  entry signal
```

The three regime zones (teal/gray/red on the heatmap) are the SAME zones the detector
uses to transition state. They are the same thing rendered differently.

---

## RESEARCH → STRATEGY ROADMAP

```
Phase 2 (current):  Research
  - Binary decomp is the detection theory
  - Detect fractal patterns on historical data (single TF, up-moves only)
  - Visualize: heatmap, per-pattern inspection charts, regime stats
  - Measure: regime persistence, pattern statistics, survival curves
  - NO P&L, NO stops, NO exits — signal detection and characterization only
  - Document every finding, parameter, and design decision

Phase 3 (future):   Strategy
  - Use Phase 2 modules as building blocks
  - Add: entry execution, stop loss, exits, position sizing
  - Run: walk-forward backtest with P&L on clean data via the loader
  - Multi-TF fractal nesting (1D move → 4H consol → 1H entry)

Phase 4+ (iterate): Research ↔ Strategy loop
  - Come back to research, adjust parameters in params.yaml
  - Measure what changed, compare distributions
  - Combine / drop / swap pieces based on backtest findings
  - The modular structure is what makes this loop fast
```

Everything is documented so that when Phase 3 begins, no reverse-engineering is needed.
Every parameter, every decision, every finding is written down.

---

## VISUALIZATION — COMPLETE

All pending fixes shipped:

1. **Candlesticks** — OHLC with LineCollection wicks + FancyBboxPatch bodies. Min body height = `max(price_range * 0.005, 1e-6)` to keep bodies visible at any scale.
2. **Move high / move low lines** — teal dashed (move_start → consol_end), red dashed (move_start → consol_end).
3. **Phase-scoped lines** — all level lines (move_high, move_low, consol_high, fib_level) span only their relevant phase window.
4. **All-window regime backgrounds** — every bar in the visible window is lightly tinted green/orange/red by score. Pattern phases layered over with stronger highlight.
5. **Step annotations** — "① MOVE", "② CONSOL", "③ ENTRY" labeled at each detection step.
6. **Move direction color** — GREEN for bullish move (will add RED when down-move detector is built).
7. **NY session filter** — intraday charts show only RTH bars (9:30–16:00 ET).

---

## Step 1 — Binary Decomposition Scoring + Heatmap (COMPLETE)

### What was added
- `src/research/scoring.py` — core scoring module
- `src/research/heatmap.py` — heatmap visualization (3-zone teal/gray/red)
- `src/research/run_heatmap.py` — runner script
- `src/loader/loader.py` — added `load_all(tf)` for research use

### How it works
Score = fraction of 9 SMA scales where `close > SMA(scale)`.
Scales: `[2, 4, 8, 16, 32, 64, 128, 256, 512]`
Range: 0.0 (below all SMAs, bearish/ranging) to 1.0 (above all SMAs, strong trend).
Each timeframe is scored fully independently.

### How to generate heatmaps
```bash
python src/research/run_heatmap.py
```
Outputs: `outputs/heatmap_NQ_{tf}.png` per timeframe.

### How to test manually
```python
from src.research.scoring import score_breakdown
import pandas as pd

# Should be high score (strong 2023 bull run)
print(score_breakdown("1day", pd.Timestamp("2023-07-01 00:00:00", tz="UTC")))

# Should be low score (COVID crash)
print(score_breakdown("1day", pd.Timestamp("2020-03-20 00:00:00", tz="UTC")))

# Should be mid score (sideways 2022)
print(score_breakdown("1day", pd.Timestamp("2022-06-01 00:00:00", tz="UTC")))
```

---

## Steps 2–4 — Detector, Export, Visual Inspection (COMPLETE — visualization fixes pending)

### What was added
- `src/research/detector.py` — FractalDetector state machine
- `src/research/export.py` — patterns_to_dataframe, save_patterns, load_patterns
- `src/research/visualize.py` — plot_pattern, plot_all_patterns

### State machine parameters (all in params.yaml)
| Parameter | Value | Meaning |
|---|---|---|
| TREND_THRESH | 0.65 | Score above this = trending up |
| RANGE_LOW | 0.35 | Score below this = full reversal |
| HYSTERESIS | 2 | Consecutive bars before state change |
| MIN_MOVE_BARS | 5 | Minimum move length |
| MIN_CONSOL_BARS | 5 | Minimum consolidation length |
| TIMEOUT_MULT | 3 | Consolidation max = 3x move duration |
| FIB_INVALIDATION | 0.5 | Close below this fib level invalidates pattern |

### Pattern counts (full dataset, 2005–2025)
| Timeframe | Patterns | Fib depth mean | Move bars mean |
|---|---|---|---|
| 1min | 21,445 | 0.55 | 25.0 |
| 5min | 5,170 | 0.53 | 27.2 |
| 15min | 2,038 | 0.48 | 29.1 |
| 60min | 605 | 0.50 | 30.4 |
| 1day | 25 | 0.45 | 33.9 |

### How to run
```bash
python src/research/run_detector.py
```
Outputs:
- `outputs/patterns/patterns_NQ_{tf}.csv` — all detected patterns
- `outputs/patterns/{tf}/pattern_NNNN.png` — inspection chart per pattern (first 20)

### Invalidation rules
- Close below fib_50 → consolidation invalidated, reset to IDLE
- Consolidation timeout (> 3x move duration) → reset to IDLE
- Full reversal (score < 0.35 for 2 bars during move) → reset to IDLE

---

## Heatmap Update — 3-Zone Regime Colors (COMPLETE)

Heatmap score background now uses 3 distinct zones:
- Teal: score > 0.65 (trending up)
- Gray: 0.35–0.65 (consolidating)
- Red: score < 0.35 (trending down / reversal)

Colors sourced from `src/research/params.yaml`.

---

## Step 5 — Regime Statistics Module (COMPLETE)

### What was added
- `src/research/regime_stats.py` — regime run extraction, duration stats, survival curves
- `src/research/run_regime_stats.py` — runner

### How to run
```bash
python src/research/run_regime_stats.py
```

### Outputs per timeframe in `outputs/regime_stats/NQ_{tf}/`
- `regime_runs.csv` — every regime run with start/end timestamps and duration
- `duration_histogram.png` — distribution of how long each regime type lasts
- `survival_curve.png` — % of regimes surviving to each duration
- `rolling_median.png` — how regime persistence has changed over time

### Key findings (60min, 2005–2025)
| Regime | Count | Median bars | 90th pct | Max |
|---|---|---|---|---|
| Trending Up | 10,753 | 2 | 15 | 90 |
| Consolidating | 14,867 | 1 | 3 | 11 |
| Trending Down | 9,181 | 2 | 10 | 58 |

**Interpretation:** Most regime signals are short-lived noise. The fat tail is real — the top
10% of bullish regimes last 15+ hours. Established trends (already survived 10+ bars)
are structurally different from nascent ones. This validates the fractal thesis:
entering after a move has proven itself with a pullback is entering the fat tail, not the noise.

### Key framing — NOT optimization
This is DESCRIPTIVE analysis. The statistics measure what NQ regimes actually do.
They are NOT used to set strategy parameters. Using them to optimize thresholds
would create in-sample bias. The in_sample_end date in params.yaml (`2018-12-31`)
is the boundary — never look at post-2018 data to make research decisions.

---

## Parameters File (COMPLETE)

`src/research/params.yaml` — every tunable value in the system, with:
- Current value
- Plain-English explanation
- Whether it's tunable and its impact level
- Notes on interactions and risks

Change parameters here, not in code. Code reads from this file.

---

## Tests Added
- `tests/test_scoring.py` — 7 tests covering score range, edge cases, output shape
- `tests/test_detector.py` — 6 tests covering pattern field completeness and parameter enforcement
- Total test suite: **65 tests, all passing**

---

## Step 7 — Signal Lifecycle Visuals (COMPLETE)

### What was added
- `src/research/detector.py` — `AbortRecord` dataclass; detector now tracks every failed pattern attempt and exposes `detector.aborts` after `run()`
- `src/research/visualize_summary.py` — two new chart types, separate from individual pattern PNGs:
  - `plot_summary_dashboard()` → `summary_dashboard.png`: 5-panel stats view across all TFs (funnel, fib depth, move/consol duration distributions, quarterly frequency)
  - `plot_signal_map()` → `signal_map_{tf}.png` per TF: compact Gantt of last 200 signal attempts + funnel + abort reason breakdown + consol survival histogram
- `src/research/run_iteration.py` — collects aborts from detector, calls both new visuals per run, adds `abort_count` to summary CSV

### AbortRecord fields
| Field | Meaning |
|---|---|
| `death_reason` | `fib_invalidated` \| `timeout` \| `reversal` \| `move_too_short` |
| `reached_consol` | Did it make it to consolidation phase? |
| `consol_bars_survived` | How long it lasted in consolidation before dying |
| `abort_ts` | Exact bar where it was discarded |

### What the signal map shows (per TF)
- **Gantt** (left, large): each row = one of the last 200 attempts. Green block = move, orange = consol, green ▲ = completed, colored ✕ = died (color = reason)
- **Funnel** (top-right): moves started → reached consolidation → entry fired
- **Death reasons** (mid-right): bar chart of abort reasons
- **Consol survival** (bottom-right): histogram of bars survived, aborted (red) vs completed (green) overlaid

### Key finding from baseline run
1min: 7,072 completed / 61,022 aborted — roughly 1 in 9 moves that start result in an entry signal.

---

## Step 6 — Iteration System (COMPLETE)

### What was added
- `src/research/params.py` — shared YAML loader, `lru_cache`, `get(section, key)` accessor
- `src/research/run_iteration.py` — auto-numbered iteration runner
- `src/utils/timeframes.py` — `filter_ny_session()`, `NY_RTH_OPEN/CLOSE` constants
- All params now read from `params.yaml` at runtime — `detector.py` and `scoring.py` no longer have hardcoded constants

### How it works
Edit `params.yaml`, then:
```bash
python src/research/run_iteration.py
```
Auto-creates `outputs/iterations/iteration_NNN/` with:
- `params_snapshot.yaml` — exact copy of params used (run is permanently reproducible)
- `patterns_NQ_{tf}.csv` — signal-by-signal output per timeframe
- `summary.csv` — one aggregate row per TF with stats + key param values embedded
- `patterns_{tf}/pattern_NNNN.png` — inspection charts

### Comparing iterations
```python
import pandas as pd
import glob

dfs = [pd.read_csv(f) for f in glob.glob("outputs/iterations/*/summary.csv")]
pd.concat(dfs).sort_values(["iteration","timeframe"])
```
Or diff the params snapshots:
```bash
diff outputs/iterations/iteration_001/params_snapshot.yaml \
     outputs/iterations/iteration_002/params_snapshot.yaml
```

### params.yaml now controls
| Module | Parameter |
|---|---|
| `scoring.py` | scales (SCALES list) |
| `detector.py` | trend_up_threshold, range_low_threshold, hysteresis, min_move_bars, min_consol_bars, timeout_mult, fib_invalidation_level, breakout_uses_close, invalidation_uses_close |
| `run_iteration.py` | ny_session_only, max_png_per_tf, context_bars |

---

## What's NOT built yet (next steps)
- Down-move detection (mirror of current up-move logic)
- Multi-timeframe fractal nesting / alignment score
- Pattern quality scoring beyond fib_depth
- In-sample vs out-of-sample comparative analysis
- Phase 3: strategy layer (entries, stops, exits, P&L)
