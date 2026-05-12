"""
Deterministic cleaning pipeline for NQ futures raw .txt exports.
Run: python src/pipeline/clean.py
Outputs: data/clean/NQ_{tf}_clean.parquet (UTC-indexed)
Logs:    data/audit/NQ_{tf}_pipeline.log
"""

import logging
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pandas as pd
import pytz

from src.utils.timeframes import CLEAN_DATA_DIR, RAW_DATA_DIR, TIMEFRAMES, TZ_CT

AUDIT_DIR = Path(__file__).resolve().parents[2] / "data" / "audit"
OHLCV_COLS = ["open", "high", "low", "close", "volume"]

# Columns to keep after parsing; everything else (MACD, ConsecDn, OI, etc.) is dropped.
_INTRADAY_KEEP = {"Date", "Time", "Open", "High", "Low", "Close", "Up", "Down"}
_DAILY_KEEP = {"Date", "Time", "Open", "High", "Low", "Close", "Vol"}


def _make_logger(tf: str) -> logging.Logger:
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    log_path = AUDIT_DIR / f"NQ_{tf}_pipeline.log"

    logger = logging.getLogger(f"pipeline.{tf}")
    logger.setLevel(logging.DEBUG)

    # Remove stale handlers so the pipeline is idempotent on repeated imports
    logger.handlers.clear()

    fh = logging.FileHandler(log_path, mode="w", encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(asctime)s UTC | %(levelname)s | %(message)s"))
    logger.addHandler(fh)
    return logger


# ---------------------------------------------------------------------------
# Individual cleaning steps
# ---------------------------------------------------------------------------


def step_parse_raw_format(
    df: pd.DataFrame, volume_source: str, logger: logging.Logger
) -> pd.DataFrame:
    """
    Converts NinjaTrader .txt export format into the canonical internal shape:
    datetime (combined), open, high, low, close, volume.
    Drops all indicator/extra columns (MACD, OI, ConsecDn, etc.).
    """
    df = df.copy()
    df["datetime"] = pd.to_datetime(
        df["Date"].astype(str) + " " + df["Time"].astype(str),
        format="%m/%d/%Y %H:%M",
    )

    if volume_source == "updown":
        df["volume"] = df["Up"] + df["Down"]
    elif volume_source == "vol":
        df["volume"] = df["Vol"]
    else:
        raise ValueError(f"Unknown volume_source: {volume_source!r}")

    df = df.rename(columns={
        "Open": "open", "High": "high", "Low": "low", "Close": "close"
    })
    df = df[["datetime", "open", "high", "low", "close", "volume"]]
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    logger.info("parse_raw_format | volume_source=%s rows=%d", volume_source, len(df))
    return df


def step_sort(df: pd.DataFrame, logger: logging.Logger) -> pd.DataFrame:
    df = df.sort_values("datetime").reset_index(drop=True)
    logger.info("sort | rows=%d", len(df))
    return df


def step_drop_exact_duplicates(df: pd.DataFrame, logger: logging.Logger) -> pd.DataFrame:
    before = len(df)
    df = df.drop_duplicates(subset=["datetime"] + OHLCV_COLS, keep="first")
    dropped = before - len(df)
    if dropped:
        logger.info("drop_exact_duplicates | dropped=%d rows", dropped)
    return df.reset_index(drop=True)


def step_check_conflicting_duplicates(df: pd.DataFrame, logger: logging.Logger) -> pd.DataFrame:
    dup_ts = df[df["datetime"].duplicated(keep=False)]
    if not dup_ts.empty:
        examples = dup_ts["datetime"].drop_duplicates().head(5).tolist()
        msg = (
            f"Conflicting duplicate timestamps found ({len(dup_ts)} rows). "
            f"Examples: {examples}. Aborting — manual inspection required."
        )
        logger.error("check_conflicting_duplicates | %s", msg)
        raise ValueError(msg)
    return df


def step_enforce_ohlc_integrity(df: pd.DataFrame, logger: logging.Logger) -> pd.DataFrame:
    mask_high_lt_low = df["high"] < df["low"]
    mask_close_outside = (df["close"] > df["high"]) | (df["close"] < df["low"])
    mask_open_outside = (df["open"] > df["high"]) | (df["open"] < df["low"])
    bad_mask = mask_high_lt_low | mask_close_outside | mask_open_outside

    bad_rows = df[bad_mask]
    for _, row in bad_rows.iterrows():
        reasons = []
        if row["high"] < row["low"]:
            reasons.append("high<low")
        if row["close"] > row["high"] or row["close"] < row["low"]:
            reasons.append("close_outside")
        if row["open"] > row["high"] or row["open"] < row["low"]:
            reasons.append("open_outside")
        logger.warning(
            "drop_ohlc_violation | ts=%s reasons=%s o=%.2f h=%.2f l=%.2f c=%.2f",
            row["datetime"],
            ",".join(reasons),
            row["open"],
            row["high"],
            row["low"],
            row["close"],
        )

    df = df[~bad_mask].reset_index(drop=True)
    logger.info("enforce_ohlc_integrity | dropped=%d rows", int(bad_mask.sum()))
    return df


def step_drop_nans(df: pd.DataFrame, logger: logging.Logger) -> pd.DataFrame:
    before = len(df)
    df = df.dropna(subset=OHLCV_COLS).reset_index(drop=True)
    dropped = before - len(df)
    if dropped:
        logger.info("drop_nans | dropped=%d rows", dropped)
    return df


def step_drop_zero_negative_prices(df: pd.DataFrame, logger: logging.Logger) -> pd.DataFrame:
    price_cols = ["open", "high", "low", "close"]
    bad_mask = (df[price_cols] <= 0).any(axis=1)
    dropped = int(bad_mask.sum())
    if dropped:
        logger.info("drop_zero_negative_prices | dropped=%d rows", dropped)
    return df[~bad_mask].reset_index(drop=True)


def step_localize_to_utc(df: pd.DataFrame, logger: logging.Logger) -> pd.DataFrame:
    # Bar timestamps from NinjaTrader are CT (bar-close label, naive)
    # Localize as CT then convert to UTC. Use nonexistent="shift_forward" and
    # ambiguous="NaT" to handle DST transitions deterministically.
    df = df.copy()
    ct_series = pd.to_datetime(df["datetime"])
    ct_localized = ct_series.dt.tz_localize(
        TZ_CT, nonexistent="shift_forward", ambiguous="NaT"
    )
    # Drop any rows where DST ambiguity produced NaT
    ambiguous_count = ct_localized.isna().sum()
    if ambiguous_count:
        logger.warning(
            "localize_to_utc | %d rows dropped due to DST ambiguity (NaT after localize)",
            ambiguous_count,
        )
    df["datetime"] = ct_localized
    df = df.dropna(subset=["datetime"]).reset_index(drop=True)
    df["datetime"] = df["datetime"].dt.tz_convert("UTC")
    logger.info("localize_to_utc | rows_remaining=%d", len(df))
    return df


def step_add_bar_close_utc(df: pd.DataFrame, logger: logging.Logger) -> pd.DataFrame:
    df = df.copy()
    df["bar_close_utc"] = df["datetime"]
    logger.info("add_bar_close_utc | column added")
    return df


# ---------------------------------------------------------------------------
# Pipeline orchestration
# ---------------------------------------------------------------------------


def clean_timeframe(tf: str) -> None:
    logger = _make_logger(tf)
    logger.info("pipeline_start | tf=%s", tf)

    meta = TIMEFRAMES[tf]
    raw_path = RAW_DATA_DIR / meta["filename"]

    raw = pd.read_csv(raw_path, dtype=str)
    logger.info("loaded_raw | path=%s rows=%d", raw_path, len(raw))

    df = step_parse_raw_format(raw, meta["volume_source"], logger)
    df = step_sort(df, logger)
    df = step_drop_exact_duplicates(df, logger)
    df = step_check_conflicting_duplicates(df, logger)
    df = step_enforce_ohlc_integrity(df, logger)
    df = step_drop_nans(df, logger)
    df = step_drop_zero_negative_prices(df, logger)
    df = step_localize_to_utc(df, logger)
    df = step_add_bar_close_utc(df, logger)

    df = df.set_index("datetime")
    df.index.name = "datetime"

    CLEAN_DATA_DIR.mkdir(parents=True, exist_ok=True)
    out_path = CLEAN_DATA_DIR / f"NQ_{tf}_clean.parquet"
    df.to_parquet(out_path, engine="pyarrow", compression="snappy")
    logger.info("pipeline_complete | output=%s rows=%d", out_path, len(df))
    print(f"  [{tf}] {len(df):,} rows -> {out_path}")


def main() -> None:
    for tf in TIMEFRAMES:
        print(f"Cleaning {tf}...")
        clean_timeframe(tf)
    print("Done.")


if __name__ == "__main__":
    main()
