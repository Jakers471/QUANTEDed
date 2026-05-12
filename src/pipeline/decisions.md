# Pipeline Cleaning Decisions

## Project architecture — research → strategy loop

This project is built in phases. The data foundation (Phase 1) feeds the research layer
(Phase 2), which feeds the strategy layer (Phase 3). Phases are not linear — the expectation
is to iterate: research → strategy → back to research → adjust → strategy again.

The binary decomposition score is the single detection theory used across all phases.
The same score that colors the heatmap drives the pattern detector and will drive the
strategy's entry filter. Parameters live in `src/research/params.yaml` and are shared
across all layers. Changing a threshold there changes behavior everywhere.

Every design decision, parameter choice, and empirical finding is documented so that
when moving between phases, nothing needs to be reverse-engineered.

## Continuous contract: UNADJUSTED (raw spliced)

The raw data is unadjusted — NQ quarterly contracts are spliced together without applying a back-adjustment offset. Roll gaps of 1–11% are visible at each rollover (confirmed by the audit's rollover analysis section).

**What this means in practice:**
- Long-lookback percentage-based indicators (200-day SMA, ATR as % of price, percentage stops) will be distorted across rollover boundaries because they mix prices from different contracts.
- Structure, session, pattern, and tick-based work is unaffected — these operate within single-contract windows.
- Entry/exit price simulation is accurate because unadjusted prices reflect what actually traded.

**If back-adjustment is needed later:** Apply a cumulative offset to all historical prices at each rollover so the series is smooth. Historical prices will no longer match actual traded prices, but indicators computed across rollovers will be meaningful. This is a pipeline step to add when building long-lookback indicator strategies. Do not mix back-adjusted and unadjusted data in the same calculation.

## Duplicate handling: keep first, error on conflicting

Exact duplicates (same timestamp AND same OHLCV) are silently dropped keeping the first occurrence. These are true duplicates with no information loss.

Conflicting duplicates (same timestamp, different OHLCV) raise an error and halt the pipeline. There is no principled way to choose which bar is correct without inspecting the source. Silent resolution would hide a data quality problem that could corrupt backtest results.

## OHLC violations: drop, not fix

Rows where `high < low`, `close` outside `[low, high]`, or `open` outside `[low, high]` are dropped. Attempting to repair them (e.g., swap high/low) requires assumptions about which field is wrong. In a futures context the most likely cause is a data feed error, not a legitimate trade. Dropping is conservative and auditable; repair is speculative.

## No forward-fill of gaps

The pipeline does not fill missing bars. Gap-filling is a strategy-level decision: some strategies treat a missing bar as "no activity" (volume=0, OHLC = prior close), others treat it as a data error. Baking a fill policy into the pipeline would silently affect all downstream consumers. The loader API exposes raw history; callers decide how to handle gaps.

## UTC storage

All timestamps are converted from Central Time (NinjaTrader source) to UTC before writing to parquet. UTC has no DST transitions, making arithmetic on timestamps unambiguous. Strategy code should reason in UTC and convert to local time only for display. The original CT timezone is preserved in `decisions.md` for provenance.

## Bar-close label convention

NinjaTrader labels bars at close (a 1-min bar opening at 17:00 CT is stamped 17:01 CT). This convention is preserved. `bar_close_utc` is an explicit column equal to the index, making the convention visible to downstream code without requiring documentation lookup.

## DST ambiguity: drop NaT rows

During the "fall back" DST transition, one hour of CT timestamps is ambiguous (clocks repeat). pandas `tz_localize` with `ambiguous="NaT"` marks these as NaT, and the pipeline drops them. The count is logged. This is a conservative choice: ambiguous bars cannot be reliably placed in UTC time.

## DST nonexistent: shift_forward

During the "spring forward" DST transition, one hour of CT timestamps does not exist. `nonexistent="shift_forward"` moves them to the first valid moment after the gap. NinjaTrader may or may not emit bars during this window; the shift ensures no crash.

## Idempotency

The pipeline can be run multiple times with identical output because:
- Sort is deterministic (ascending datetime)
- Duplicate logic is deterministic (keep first)
- DST handling uses fixed rules (no random or time-dependent behavior)
- Output is overwritten, not appended

## Column retention

Only the six canonical columns (`open`, `high`, `low`, `close`, `volume`, and added `bar_close_utc`) are written. All NinjaTrader indicator columns (MACD, MACDAvg, MACDDiff, ZeroLine, ConsecDn, ConsecUp) and the daily OI column are dropped at parse time. Indicators baked into a data export are parameter-specific and have no place in a general-purpose data foundation.

## Volume source: intraday vs daily

NinjaTrader intraday exports (1min, 5min, 15min, 60min) provide `Up` and `Down` tick-volume columns rather than a single volume. `volume = Up + Down` is the total number of trades in the bar, which is the standard volume definition for futures. The daily export provides an explicit `Vol` column which is used directly. OI (open interest) from the daily export is dropped — it is a per-contract figure that changes meaning across rollovers and is not used in bar-level research.

## 4h timeframe: not included

No 4h export was available. The timeframe is omitted from the pipeline entirely rather than stub-configured. Add it by exporting from NinjaTrader, placing the file in `data/`, and adding an entry to `src/utils/timeframes.py`.
