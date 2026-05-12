"""
Fractal pattern detector: move → consolidation → breakout (up-moves only).

State machine that processes bars sequentially. Feed it the output of
score_history() and it returns a list of PatternRecord dataclasses.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from dataclasses import dataclass
from enum import Enum, auto

import pandas as pd

from src.research.params import get as _p


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class AbortRecord:
    """A pattern attempt that was started but never reached entry signal."""
    timeframe: str
    move_start_ts: pd.Timestamp
    move_end_ts: pd.Timestamp         # when move ended, or death ts if died in move
    move_duration_bars: int
    reached_consol: bool              # True if it made it to consolidation phase
    consol_start_ts: pd.Timestamp | None
    abort_ts: pd.Timestamp            # bar where it was discarded
    consol_bars_survived: int         # 0 if died before/during move phase
    death_reason: str                 # "reversal" | "move_too_short" | "fib_invalidated" | "timeout"


@dataclass
class PatternRecord:
    timeframe: str
    move_start_ts: pd.Timestamp
    move_end_ts: pd.Timestamp
    move_low: float
    move_high: float
    move_duration_bars: int
    consol_start_ts: pd.Timestamp
    consol_end_ts: pd.Timestamp
    consol_low: float
    consol_high: float
    consol_duration_bars: int
    fib_retracement_depth: float   # how deep pullback went as fraction of move height
    fib_50: float                  # absolute price of 0.5 fib level
    entry_ts: pd.Timestamp
    entry_price: float             # close of breakout bar
    entry_score: float             # score at entry


# ---------------------------------------------------------------------------
# State enum
# ---------------------------------------------------------------------------

class _State(Enum):
    IDLE             = auto()
    IN_MOVE          = auto()
    IN_CONSOLIDATION = auto()


# ---------------------------------------------------------------------------
# Detector
# ---------------------------------------------------------------------------

REQUIRED_COLUMNS = {"high", "low", "close", "score"}


class FractalDetector:
    """
    State machine: IDLE → IN_MOVE → IN_CONSOLIDATION → (emit PatternRecord) → IDLE
    All thresholds read from src/research/params.yaml at instantiation time.
    """

    def __init__(self, tf: str) -> None:
        self.tf = tf

        # Read all tunable constants from params.yaml
        self.TREND_THRESH    = _p("regimes",  "trend_up_threshold")
        self.RANGE_LOW       = _p("regimes",  "range_low_threshold")
        self.HYSTERESIS      = _p("detector", "hysteresis")
        self.MIN_MOVE_BARS   = _p("detector", "min_move_bars")
        self.MIN_CONSOL_BARS = _p("detector", "min_consolidation_bars")
        self.TIMEOUT_MULT    = _p("detector", "consolidation_timeout_multiplier")
        self.MAX_CONSOL_BARS = _p("detector", "consolidation_max_bars")
        self.FIB_INVALID     = _p("detector", "fib_invalidation_level")
        self.BREAKOUT_CLOSE  = _p("detector", "breakout_uses_close")
        self.INVALID_CLOSE   = _p("detector", "invalidation_uses_close")

        # Collects AbortRecords for every pattern attempt that didn't reach entry.
        # Populated during run(), not cleared by _reset().
        self.aborts: list[AbortRecord] = []

        self._state = _State.IDLE
        self._reset()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self, data: pd.DataFrame) -> list[PatternRecord]:
        """
        Process a full score_history DataFrame.
        data must have columns: high, low, close, score (output of score_history()).
        Returns list of PatternRecord, one per detected pattern.
        """
        missing = REQUIRED_COLUMNS - set(data.columns)
        if missing:
            raise ValueError(
                f"FractalDetector.run() requires columns {REQUIRED_COLUMNS}. "
                f"Missing: {missing}"
            )

        # Reset before each full run so the detector is reusable
        self._state = _State.IDLE
        self._reset()
        self.aborts = []

        patterns: list[PatternRecord] = []

        for ts, row in data.iterrows():
            result = self._process_bar(ts, row)
            if result is not None:
                patterns.append(result)

        return patterns

    # ------------------------------------------------------------------
    # Per-bar dispatch
    # ------------------------------------------------------------------

    def _process_bar(self, ts: pd.Timestamp, row: pd.Series) -> PatternRecord | None:
        if self._state is _State.IDLE:
            self._handle_idle(ts, row)
            return None
        elif self._state is _State.IN_MOVE:
            self._handle_in_move(ts, row)
            return None
        elif self._state is _State.IN_CONSOLIDATION:
            return self._handle_in_consol(ts, row)
        return None  # unreachable

    # ------------------------------------------------------------------
    # State handlers
    # ------------------------------------------------------------------

    def _handle_idle(self, ts: pd.Timestamp, row: pd.Series) -> None:
        """IDLE: look for HYSTERESIS consecutive bars above TREND_THRESH."""
        score = row["score"]

        if score > self.TREND_THRESH:
            self._hysteresis_up += 1
        else:
            self._hysteresis_up = 0

        if self._hysteresis_up >= self.HYSTERESIS:
            # Transition to IN_MOVE. Anchor start at the first bar of the run.
            # We don't have access to the earlier bar's timestamp here, so we
            # use the current bar as move_start (conservative).
            self._state = _State.IN_MOVE
            self._move_start_ts   = ts
            self._move_low        = row["low"]
            self._move_high       = row["high"]
            self._move_bars       = self._hysteresis_up
            self._hysteresis_up   = 0
            self._hysteresis_down = 0
            self._below_trend_count = 0

    def _handle_in_move(self, ts: pd.Timestamp, row: pd.Series) -> None:
        """IN_MOVE: track the move; detect reversal or transition to consolidation."""
        score = row["score"]

        # Expand move envelope
        self._move_high = max(self._move_high, row["high"])
        self._move_low  = min(self._move_low,  row["low"])
        self._move_bars += 1

        # Full reversal counter (score < RANGE_LOW)
        if score < self.RANGE_LOW:
            self._hysteresis_rev += 1
        else:
            self._hysteresis_rev = 0

        if self._hysteresis_rev >= self.HYSTERESIS:
            self._abort(ts, "reversal", reached_consol=False)
            return

        # Below-trend counter (score < TREND_THRESH → potential end of move)
        if score < self.TREND_THRESH:
            self._below_trend_count += 1
        else:
            self._below_trend_count = 0

        if self._below_trend_count >= self.HYSTERESIS:
            if self._move_bars >= self.MIN_MOVE_BARS:
                # Lock move end, transition to IN_CONSOLIDATION
                self._state         = _State.IN_CONSOLIDATION
                self._move_end_ts   = ts
                self._consol_start_ts = ts
                self._consol_high   = row["high"]
                self._consol_low    = row["low"]
                self._consol_bars   = 1
                self._below_trend_count = 0
                self._hysteresis_up     = 0
                self._breakout_count    = 0
            else:
                self._abort(ts, "move_too_short", reached_consol=False)

    def _handle_in_consol(
        self, ts: pd.Timestamp, row: pd.Series
    ) -> PatternRecord | None:
        """IN_CONSOLIDATION: wait for breakout, watch for invalidation / timeout."""
        score = row["score"]
        close = row["close"]

        # Snapshot the prior high BEFORE expanding — the breakout check compares
        # close against the level established by previous bars, not the current bar.
        prev_consol_high = self._consol_high

        # Expand consolidation envelope
        self._consol_high = max(self._consol_high, row["high"])
        self._consol_low  = min(self._consol_low,  row["low"])
        self._consol_bars += 1

        # Precompute fib level using params-driven invalidation depth
        move_height = self._move_high - self._move_low
        fib_level   = self._move_high - move_height * self.FIB_INVALID

        # --- Invalidation ---
        invalidation_price = close if self.INVALID_CLOSE else row["low"]
        if invalidation_price < fib_level:
            self._abort(ts, "fib_invalidated", reached_consol=True)
            return None

        # --- Timeout: consolidation too long (relative or absolute cap) ---
        if self._consol_bars > self.TIMEOUT_MULT * self._move_bars:
            self._abort(ts, "timeout", reached_consol=True)
            return None
        if self.MAX_CONSOL_BARS is not None and self._consol_bars > self.MAX_CONSOL_BARS:
            self._abort(ts, "timeout", reached_consol=True)
            return None

        # --- Breakout check ---
        if score > self.TREND_THRESH:
            self._breakout_count += 1
        else:
            self._breakout_count = 0

        breakout_price = close if self.BREAKOUT_CLOSE else row["high"]
        is_breakout = (
            breakout_price > prev_consol_high
            and self._breakout_count >= self.HYSTERESIS
            and self._consol_bars >= self.MIN_CONSOL_BARS
        )

        if is_breakout:
            record = self._emit_pattern(ts, row, fib_level, move_height)
            self._reset()
            return record

        return None

    # ------------------------------------------------------------------
    # Emit / reset
    # ------------------------------------------------------------------

    def _emit_pattern(
        self,
        ts: pd.Timestamp,
        row: pd.Series,
        fib_50: float,
        move_height: float,
    ) -> PatternRecord:
        """Build and return a PatternRecord from current accumulated state."""
        consol_height   = self._consol_high - self._consol_low
        retracement_raw = self._move_high - self._consol_low   # pullback from move_high
        fib_depth       = retracement_raw / move_height if move_height > 0 else 0.0

        return PatternRecord(
            timeframe            = self.tf,
            move_start_ts        = self._move_start_ts,
            move_end_ts          = self._move_end_ts,
            move_low             = self._move_low,
            move_high            = self._move_high,
            move_duration_bars   = self._move_bars,
            consol_start_ts      = self._consol_start_ts,
            consol_end_ts        = ts,
            consol_low           = self._consol_low,
            consol_high          = self._consol_high,
            consol_duration_bars = self._consol_bars,
            fib_retracement_depth= fib_depth,
            fib_50               = fib_50,
            entry_ts             = ts,
            entry_price          = row["close"],
            entry_score          = row["score"],
        )

    def _abort(self, ts: pd.Timestamp, reason: str, reached_consol: bool) -> None:
        """Record a failed pattern attempt and reset state."""
        if self._move_start_ts is not None:
            self.aborts.append(AbortRecord(
                timeframe            = self.tf,
                move_start_ts        = self._move_start_ts,
                move_end_ts          = self._move_end_ts if reached_consol else ts,
                move_duration_bars   = self._move_bars,
                reached_consol       = reached_consol,
                consol_start_ts      = self._consol_start_ts if reached_consol else None,
                abort_ts             = ts,
                consol_bars_survived = self._consol_bars if reached_consol else 0,
                death_reason         = reason,
            ))
        self._reset()

    def _reset(self) -> None:
        """Zero out ALL state variables. Must touch every field."""
        self._state = _State.IDLE

        # Move phase
        self._move_start_ts     = None
        self._move_end_ts       = None
        self._move_low          = 0.0
        self._move_high         = 0.0
        self._move_bars         = 0

        # Consolidation phase
        self._consol_start_ts   = None
        self._consol_high       = 0.0
        self._consol_low        = 0.0
        self._consol_bars       = 0

        # Hysteresis counters
        self._hysteresis_up     = 0
        self._hysteresis_down   = 0
        self._hysteresis_rev    = 0
        self._below_trend_count = 0
        self._breakout_count    = 0
