# Research Roadmap

Everything that needs to be researched, tested, and eventually built into the strategy.
Items move from "Research" → "Validated" → "Strategy-ready" as work progresses.
Nothing gets deleted from this list — completed items get marked and dated.

---

## How to read this

- **Research:** needs empirical study on historical data first
- **Build:** can be coded once research validates the concept
- **Strategy:** becomes a live input to the backtest/strategy engine
- **Blocked by:** what must be done first

---

## CURRENT PHASE — Phase 2: Single-TF Pattern Detection

### Active
- [x] Binary decomp score (9 scales, equal weight) — DONE
- [x] Heatmap: 3-zone teal/gray/red per regime — DONE
- [x] State machine detector: move → consolidation → breakout (up only) — DONE
- [x] Regime persistence statistics + survival curves — DONE
- [x] params.yaml — all parameters documented — DONE
- [x] Visualization: candlestick inspection charts — DONE
- [x] Visualization: move high/low lines + phase-scoped drawing — DONE
- [x] Visualization: all-window regime backgrounds + step annotations — DONE
- [x] NY session filter (RTH only, 9:30–16:00 ET) — DONE
- [x] Iteration system: params.yaml → run_iteration.py → versioned outputs — DONE
- [x] Signal lifecycle visuals: AbortRecord tracking, summary_dashboard.png, signal_map_{tf}.png — DONE

---

## SCORING LAYER — future research items

### Exponential decay weighting
- **What:** Instead of equal weights (1/9 per scale), apply decay so shorter
  scales (recent price action) matter more than longer scales.
  `weight[i] = decay_rate ^ i`, then normalize to sum=1.
- **Why research it:** Equal weighting assumes all timeframes matter equally.
  Exponential decay reflects that recent structure is more relevant than ancient.
- **Test:** Compare signal quality (pattern fib depth, win rate eventually) between
  equal-weight and decay-weighted scores. Use in-sample data only.
- **Decay rates to test:** 0.7, 0.8, 0.85, 0.9
- **Blocked by:** Pattern validation (need to know what "better" means first)
- **Status:** Documented in params.yaml under `scoring.decay_rate`
- **Phase:** Research → Strategy

### Geometric progression of scales
- **What:** Current scales [2,4,8,16,32,64,128,256,512] are already geometric (2x each).
  Alternative progressions to test: Fibonacci-spaced [3,5,8,13,21,34,55,89,144],
  or custom sets that emphasize certain regime windows.
- **Why research it:** The 2x doubling is arbitrary. Fibonacci spacing reflects
  natural market rhythm. Test whether a different scale set produces cleaner regime signals.
- **Test:** Compare regime clarity (how crisp are the transitions?) across scale sets.
- **Status:** Documented in params.yaml under `scoring.scales`
- **Phase:** Research → Strategy

### Score smoothing / confirmation filter
- **What:** Apply a short EMA or rolling mean to the raw score to reduce
  1-2 bar oscillations that cause false state transitions.
- **Why research it:** The survival curves show most regimes die in 1-2 bars —
  a lot of that is score chatter, not real regime change.
- **Test:** Compare hysteresis=2 (current) vs short score EMA vs both together.
- **Blocked by:** Current hysteresis parameter covers some of this — test overlap
- **Status:** Not yet in params.yaml
- **Phase:** Research → Strategy

---

## DETECTOR LAYER — future research items

### Down-move detection
- **What:** Mirror of the current up-move detector.
  Move down (score < 0.35) → consolidation → move continues down.
  Fib invalidation flipped: close above 0.5 fib of the down-move invalidates.
- **Why:** Complete the pattern library — up AND down fractals.
- **Blocked by:** Up-move detector fully validated first
- **Status:** Architecture is clear, not yet coded
- **Phase:** Research → Strategy

### Consolidation quality scoring
- **What:** Beyond fib_retracement_depth, score the quality of the consolidation:
  - How tight was the range? (consol_high - consol_low) / move_height
  - How long relative to the move? (consol_duration / move_duration)
  - Did the score stay cleanly in the gray zone, or oscillate?
  A "quality score" per pattern lets us filter for the cleanest setups.
- **Why:** Not all patterns are equal. A tight, shallow consolidation is stronger
  than a wide, deep one. Quality scoring enables filtering without adding hard thresholds.
- **Test:** Correlate quality score with eventual price continuation (Phase 3 P&L).
- **Blocked by:** Phase 3 P&L data
- **Status:** Not yet coded
- **Phase:** Research → Strategy

### Minimum move size (regime-adaptive)
- **What:** Currently we only filter by move_duration_bars (min 5 bars).
  Future: filter by move SIZE relative to recent ATR (e.g., move must be > 1.5x ATR).
  This is regime-adaptive — a "significant" move in 2020 volatility is different from 2017.
- **Why:** A 5-bar micro-wiggle and a 5-bar explosive move both pass the current filter.
  ATR-relative sizing distinguishes them.
- **Blocked by:** ATR indicator is in indicators.py — just needs wiring
- **Status:** Not yet coded
- **Phase:** Research → Strategy

---

## MULTI-TIMEFRAME LAYER — future research items

### Cross-timeframe alignment score
- **What:** A single number representing how aligned ALL timeframes are at a moment.
  `alignment = weighted_mean([score(tf, as_of) for tf in timeframes])`
  When alignment is high (e.g., > 0.75), all TFs agree the market is trending up.
- **Why:** A 5min pattern forming during a 1day trending regime is a different
  quality signal than a 5min pattern forming in a 1day consolidation.
- **Geometric progression for TF weights:** Lower timeframes (1min, 5min) get less
  weight; higher timeframes (60min, 1day) get more. Reflects that higher TF context
  dominates.
  Example: weight(1day)=0.35, weight(60min)=0.30, weight(15min)=0.20,
           weight(5min)=0.10, weight(1min)=0.05
- **Test:** Does high alignment predict better pattern continuation?
- **Blocked by:** Single-TF detector validated first
- **Status:** Architecture clear, not yet coded. Colors for alignment in params.yaml.
- **Phase:** Research → Strategy

### Nested fractal detection
- **What:** Detect that a pattern on a lower TF is occurring INSIDE the consolidation
  phase of a higher-TF pattern. This is the full fractal structure:
  1D move → 1D consolidation contains → 4H move → 4H consolidation contains → 1H entry signal
- **Why:** This is the core thesis. A lower-TF entry that aligns with higher-TF structure
  has the highest probability of continuation.
- **Blocked by:** Single-TF detector validated + alignment score built
- **Status:** Not yet coded — this is the Phase 3 centerpiece
- **Phase:** Research → Strategy

### Multi-TF heatmap
- **What:** One chart, all 5 timeframes stacked. Each row = one TF, color = overall
  TF score. Allows visual detection of alignment/divergence across TFs over time.
- **Blocked by:** Single-TF heatmap done (it is)
- **Status:** Not yet coded
- **Phase:** Research (visualization)

---

## STRATEGY LAYER — Phase 3 items (not yet started)

These are NOT research items — they require validated research as inputs first.

- Entry execution: which bar to enter, what price (close, open+1, limit?)
- Stop loss: ATR-based, below consolidation low, below fib_50?
- Exit: score-based (exit when score drops), time-based, target-based?
- Position sizing: fixed, volatility-adjusted (1/ATR), Kelly?
- Walk-forward backtest framework: time-based splits, not random
- In-sample boundary enforcement: all parameter choices from pre-2018 data only
- Out-of-sample validation: 2019–2022, held-out 2023–2025

---

## NOTES ON METHODOLOGY

**Research vs optimization boundary:**
Measuring statistics on historical data (regime durations, pattern frequencies,
fib depth distributions) is descriptive research — fine and encouraged.
Using those measurements to pick exact numerical thresholds that maximize backtest P&L
is hidden optimization — creates in-sample bias that doesn't generalize.

The correct pattern: measure the distribution, understand the shape, use
adaptive/rolling references rather than fixed numbers derived from the data.

**In-sample cutoff: 2018-12-31** (set in params.yaml)
Everything before this date is fair game for research and parameter choice.
Everything after is validation — look at it only to confirm, never to decide.
