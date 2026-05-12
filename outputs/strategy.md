# Strategy Framework

---

## Core Philosophy

The system is not a parameter-optimization engine.
Parameters define the geometry of a pattern that has been empirically identified over years of observation.
Once the pattern structure is defined, the binary decomp score makes detection self-adaptive —
regime thresholds don't need recalibration per market cycle because the score is relative (fraction of SMAs), not absolute.

Two axes validate a signal:

- **Spatial** — the pattern validates against its own structure (price relative to its own high/low, fib retracement of the move itself)
- **Temporal** — the pattern must complete in a defined sequence of steps (move → consolidation → breakout)

Both axes must be satisfied. Spatial geometry without temporal sequencing is noise. Temporal sequencing without valid spatial structure is a false signal.

---

## Layer 1 — Scoring (Built)

**Binary decomposition score**

- Close is compared against N SMA scales simultaneously
- Score = fraction of scales where `close > SMA(scale)` → range 0.0 to 1.0
- Computed independently per timeframe (fractal: same theory, every TF)
- Self-adaptive: a score of 0.7 means the same structural thing in 2008 as in 2023

**Current scales:** `[2, 4, 8, 16, 32, 64, 128, 256, 512]` — 9 scales, geometric (2x each)

**Weighting:** Equal (1/9 per scale)

**Adjustable in params.yaml:**

| Parameter | Current | What it does |
|---|---|---|
| `scoring.scales` | [2,4,8,16,32,64,128,256,512] | Which SMA periods to use |
| `scoring.weights.mode` | `equal` | How scales are weighted |
| `scoring.decay_rate` | 0.85 | Rate for exponential decay mode (not yet active) |

---

## Layer 2 — Regime Detection (Built)

**Three zones derived from the score:**

| Zone | Score | Label |
|---|---|---|
| Trending up | > 0.65 | Bullish regime |
| Consolidating | 0.35 – 0.65 | Ranging regime |
| Trending down | < 0.35 | Bearish regime |

These are the same zones that color the heatmap, drive the state machine, and will eventually drive entry/exit conditions. One theory, every output.

**Adjustable in params.yaml:**

| Parameter | Current | What it does |
|---|---|---|
| `regimes.trend_up_threshold` | 0.65 | Score above this = trending up |
| `regimes.range_low_threshold` | 0.35 | Score below this = trending down |

---

## Layer 3 — Pattern Detection / Temporal Sequencing (Built)

**The sequence (up-move only, bearish to be added):**

```
Step 1  MOVE UP        score > 0.65 sustained for HYSTERESIS bars
Step 2  CONSOLIDATION  score drops below 0.65, holds above 0.35
Step 3  ENTRY SIGNAL   score > 0.65 again + close breaks consolidation high
```

Signal is invalidated (dies) if at any point during consolidation:
- Close drops below the 0.5 fib level of the move (spatial invalidation)
- Consolidation drags beyond `timeout_multiplier × move_duration` bars (temporal invalidation)
- Score drops below 0.35 for HYSTERESIS bars during the move (full reversal)

**Where the signal lives:**

The signal is the combination of two files working in sequence:

```
score/scoring.py        →    detection/detector.py
produces score per bar       reads score, applies pattern rules, emits signal
```

`scoring.py` defines what "trending" means numerically. `detector.py` defines the geometric and temporal pattern rules on top of that score. Neither produces a signal alone — the score is the input, the detector is the logic. Everything else (`export.py`, the visualization files, `run_iteration.py`) is feeding data in or reading results out.

**State machine parameters (params.yaml):**

| Parameter | Current | Enable/Disable | What it does |
|---|---|---|---|
| `detector.hysteresis` | 2 | Adjust | Bars a score condition must hold before state change |
| `detector.min_move_bars` | 5 | Adjust | Minimum move length in bars |
| `detector.min_move_atr_multiple` | null | null = off | Minimum move height as multiple of ATR — filters small moves |
| `detector.atr_period` | 14 | Adjust | ATR lookback for size filter |
| `detector.min_consolidation_bars` | 20 | Adjust | Minimum consolidation length to qualify |
| `detector.consolidation_max_bars` | 60 | null = off | Hard absolute cap on consolidation bars |
| `detector.consolidation_timeout_multiplier` | 3 | Adjust | Adaptive cap = N × move duration |
| `detector.fib_invalidation_level` | 0.5 | Adjust | Retracement depth that kills the pattern |
| `detector.breakout_uses_close` | true | true/false | Use close vs wick for breakout confirmation |
| `detector.invalidation_uses_close` | true | true/false | Use close vs wick for fib invalidation |

**Move quality filters — two independent checks:**
`min_move_bars` filters on duration. `min_move_atr_multiple` filters on size (height relative to recent volatility). Both can be active simultaneously — either alone can kill a move before consolidation starts. The ATR filter is self-scaling: a 1.5× ATR move means the same thing in a low-vol period as in a high-vol period.

**Consolidation caps — how they interact:**
Both `consolidation_max_bars` and `consolidation_timeout_multiplier` run every bar. Whichever fires first kills the signal. The multiplier is adaptive (scales with move length). The hard cap is a ceiling regardless. Set `consolidation_max_bars: null` to rely on multiplier only.

**Bearish signal (to be added):**
Same exact state machine, score thresholds inverted. Entry trigger is score < 0.35 sustained for HYSTERESIS bars (move down), consolidation when score rises back above 0.35, breakout when score breaks below 0.35 again and close breaks consolidation low. Fib invalidation flipped: close above 0.5 fib of the down-move kills it. All size/duration filters apply equally. When added it will be a direction flag in params, not a separate detector.

---

## Layer 4 — Spatial Geometry (Built, validation only so far)

The pattern measures its own structure after the fact:
- `move_high`, `move_low` — anchors of the impulse move
- `fib_50` — absolute price of the 0.5 retracement level
- `fib_retracement_depth` — how deep the consolidation actually pulled back as a fraction of move height
- `consol_high`, `consol_low` — the range the market compressed into

Fib invalidation is currently the only active spatial rule (close below 0.5 fib kills the pattern).
Further spatial geometry (e.g. tighter fib ranges, consol range width relative to move height) is research-phase.

---

## Session Filter (Built)

| Parameter | Current | Enable/Disable | What it does |
|---|---|---|---|
| `session.ny_session_only` | true | true/false | Restrict to NY RTH (9:30–16:00 ET) for intraday TFs |

---

## Run Config (Built)

| Parameter | Current | What it does |
|---|---|---|
| `run.timeframes` | all 5 TFs | Which TFs to include in each iteration run |
| `visualization.max_png_per_tf` | 20 | How many individual pattern PNGs to generate |
| `visualization.context_bars` | 50 | Bars of history shown before/after pattern in PNGs |

---

## Iteration System (Built)

Run `python src/research/runners/run_iteration.py` — auto-numbers each run.

Each iteration saves:
- `params_snapshot.yaml` — exact params used (run permanently reproducible)
- `patterns_NQ_{tf}.csv` — every completed signal
- `summary.csv` — aggregate stats + all key params embedded per row
- `summary_dashboard.png` — signal funnel, distributions, quarterly frequency
- `signal_map_{tf}.png` — Gantt of last 200 attempts, funnel, death reasons, consol survival
- `patterns_{tf}/pattern_NNNN.png` — individual inspection charts

---

## To Be Added

**Scoring layer:**
- Exponential decay weighting — shorter scales get more weight, decay rate configurable (`scoring.decay_rate`)
- Geometric progression alternative scale sets (e.g. Fibonacci-spaced scales)

**Pattern detection:**
- Bearish version — move down → consolidation → move down
- Extensions and exhaustion signals — for exit conditions and stopping entries

**Entry / exit logic:**
- Entry mechanics (to be defined)
- Exit logic (to be defined, extensions/exhaustion as one input)

**Post-signal analysis:**
- What happened after the signal fired
- Did completed signals produce positive expectancy
- Did signals that died (aborted) produce negative or positive expectancy
- Requires entry/exit definition first

---

## Signal Funnel (Baseline, 1min NY session)

| Stage | Count |
|---|---|
| Moves started (total attempts) | ~68,094 |
| Reached consolidation | ~14,166 |
| Entry signal fired (completed) | 7,072 |
| Aborted | 61,022 |

Roughly 1 in 9 move attempts result in a completed signal.

---

## Code Architecture — Portable Core vs Research Infrastructure

The Python project is not the deployment. It is the specification and validation layer.
When going live, the core logic gets re-implemented or wrapped — it does not get directly deployed as-is.

Two distinct categories of code:

**Portable core** — the algorithm itself. Small, isolated, no visualization dependencies.
Anything in this category must be re-implementable in another language by reading it.

```
score/
  scoring.py      binary decomp math — pure computation
  
detection/
  detector.py     state machine logic — pure rules
  export.py       serialization only
```

**Research infrastructure** — Python-only, never deployed. Gets stripped when going live.

```
score/
  regime_stats.py   statistical analysis
  heatmap.py        visualization

visualization/
  visualize.py
  visualize_summary.py

runners/
  run_*.py
```

The folder structure of `src/research/` reflects this split directly.
`score/` and `detection/` survive into live deployment in one form or another.
Everything else stays in research forever.

---

## Deployment Options

Three viable paths when the strategy is ready to go live.
None need to be decided now. The research architecture supports all three.

---

### Option 1 — NinjaTrader (NinjaScript / C#)

The portable core (`scoring.py` + `detector.py`) gets re-implemented in NinjaScript.
Python stays as the reference implementation.

Verification process:
1. Run Python detector on historical data, save detected patterns to CSV (already done)
2. Build the NinjaScript version following the same rules
3. Run NinjaScript on the same data
4. Compare detected pattern timestamps bar-by-bar — they must match

If they match, the port is correct. If not, debug until they do.

NinjaTrader handles its own data access (`AddDataSeries`, `BarsArray[]`), its own indicators, and its own order execution (`EnterLong`, `ExitLong`). The Python loader and Python indicators are not used in NT.

---

### Option 2 — n8n + Python (workflow orchestration)

n8n acts as the scheduler and signal router. The Python code runs on a server (local or cloud).

Flow:
```
n8n trigger (every bar close, or on schedule)
  → calls Python detector script or HTTP endpoint
  → Python returns signal: { signal: "entry", price: 21450, tf: "5min" }
  → n8n routes signal to broker API or alert system
```

For this to work, the detector needs to be wrapped as either:
- A standalone Python script with clean stdin/stdout (simplest)
- A minimal HTTP endpoint (Flask or FastAPI, one file)

The key: n8n does not care about the folder structure. It calls one entry point.
The complexity of the research project stays inside that entry point.

This path keeps everything in Python — no C# port required.
Requires a server (cloud VM, Raspberry Pi, local machine) that stays running.

---

### Option 3 — Cloud Python (direct deployment)

The Python detector runs on a cloud server on a schedule.
No n8n in the middle — the script itself handles scheduling, data fetching, and signal output.

Options: AWS Lambda, GCP Cloud Run, a simple VPS with cron.

Same requirement as Option 2: the detector needs a clean entry point.
The research infrastructure (visualization, iteration system) is not deployed — only the core.

---

### What all three options share

All three deployment paths require the same thing from the Python project:

1. The core logic is correct and validated (happening now in research phase)
2. The algorithm is fully specified in plain English so it can be verified or re-implemented
3. The historical pattern CSV serves as ground truth for verifying any new implementation

The Python research codebase is already structured to produce all three.
No rework needed when it's time to choose a deployment path — just wrap or re-implement the core.

---

## Specification (Plain English Rules)

To be filled in as the detector is finalized.
This is the portable artifact — language-agnostic, unambiguous.
Any implementation (Python, C#, n8n workflow) must produce results that match this spec.

### Binary Decomposition Score
- Compute SMA for each scale in `[2, 4, 8, 16, 32, 64, 128, 256, 512]`
- Score = count of scales where `close > SMA(scale)` divided by total scale count
- Range: 0.0 to 1.0. Computed independently per timeframe. No cross-TF logic.

### Regime Classification
- Score > 0.65 → trending up
- Score 0.35–0.65 → consolidating
- Score < 0.35 → trending down

### Pattern Detection Sequence (bullish, up-move only currently)
- Step 1 MOVE: score > 0.65 for at least 2 consecutive bars
- Step 2 CONSOL: score drops below 0.65, stays above 0.35. Track high/low of range.
  - Invalidated if close < (move_high - move_height × 0.5)
  - Invalidated if consolidation exceeds 3 × move_duration bars
  - Invalidated if score drops below 0.35 for 2 bars
- Step 3 ENTRY: score > 0.65 again AND close > prior consolidation high, confirmed for 2 bars, after minimum 5 consolidation bars
