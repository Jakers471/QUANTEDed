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

**State machine parameters (params.yaml):**

| Parameter | Current | Enable/Disable | What it does |
|---|---|---|---|
| `detector.hysteresis` | 2 | Adjust | Bars a score condition must hold before state change |
| `detector.min_move_bars` | 5 | Adjust | Minimum move length to qualify |
| `detector.min_consolidation_bars` | 5 | Adjust | Minimum consolidation length to qualify |
| `detector.consolidation_timeout_multiplier` | 3 | Adjust | Max consol = N × move duration |
| `detector.fib_invalidation_level` | 0.5 | Adjust | Retracement depth that kills the pattern |
| `detector.breakout_uses_close` | true | true/false | Use close vs wick for breakout confirmation |
| `detector.invalidation_uses_close` | true | true/false | Use close vs wick for fib invalidation |

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

Run `python src/research/run_iteration.py` — auto-numbers each run.

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
