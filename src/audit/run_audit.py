"""
Audit every raw CSV and write per-timeframe markdown reports to data/audit/.
Run: python src/audit/run_audit.py
"""

import sys
from pathlib import Path

# Allow imports from project root
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import textwrap
from datetime import datetime

import numpy as np
import pandas as pd

from src.utils.timeframes import RAW_DATA_DIR, TIMEFRAMES

AUDIT_DIR = Path(__file__).resolve().parents[2] / "data" / "audit"


# ---------------------------------------------------------------------------
# Individual check functions
# ---------------------------------------------------------------------------


def check_row_count(df: pd.DataFrame) -> dict:
    return {"row_count": len(df)}


def check_date_range(df: pd.DataFrame) -> dict:
    return {
        "first_timestamp": str(df["datetime"].iloc[0]),
        "last_timestamp": str(df["datetime"].iloc[-1]),
    }


def check_duplicates(df: pd.DataFrame) -> dict:
    dupes = df[df["datetime"].duplicated(keep=False)]
    examples = dupes["datetime"].drop_duplicates().head(5).tolist()
    return {
        "duplicate_timestamp_count": int(df["datetime"].duplicated().sum()),
        "duplicate_examples": [str(e) for e in examples],
    }


def check_ordering(df: pd.DataFrame) -> dict:
    diffs = df["datetime"].diff().dropna()
    out_of_order_mask = diffs < pd.Timedelta(0)
    count = int(out_of_order_mask.sum())
    bad_idx = out_of_order_mask[out_of_order_mask].index[:5]
    examples = df.loc[bad_idx, "datetime"].tolist()
    return {
        "out_of_order_count": count,
        "out_of_order_examples": [str(e) for e in examples],
    }


def check_missing_bars(df: pd.DataFrame, tf: str) -> dict:
    from src.utils.timeframes import bar_duration_minutes

    if tf == "1day":
        # Daily bars: skip weekend gaps, don't flag multi-day gaps as missing
        return {"missing_bars_note": "Daily timeframe — intraday gap check skipped."}

    bar_min = bar_duration_minutes(tf)
    expected_delta = pd.Timedelta(minutes=bar_min)
    diffs = df["datetime"].diff().dropna()
    # A gap is any diff strictly greater than one bar period
    gaps = diffs[diffs > expected_delta]

    gap_details = []
    for idx in gaps.index[:10]:
        prev_ts = df.loc[idx - 1, "datetime"] if idx > 0 else None
        curr_ts = df.loc[idx, "datetime"]
        gap_bars = int(gaps.loc[idx] / expected_delta) - 1
        gap_details.append(
            {
                "from": str(prev_ts),
                "to": str(curr_ts),
                "missing_bars": gap_bars,
            }
        )

    return {
        "gap_count": len(gaps),
        "top_10_gaps": gap_details,
    }


def check_zero_negative_prices(df: pd.DataFrame) -> dict:
    price_cols = ["open", "high", "low", "close"]
    counts = {}
    for col in price_cols:
        counts[col] = int((df[col] <= 0).sum())
    vol_zero = int((df["volume"] <= 0).sum())
    return {"zero_or_negative_prices": counts, "zero_volume_bars": vol_zero}


def check_ohlc_integrity(df: pd.DataFrame) -> dict:
    high_lt_low = int((df["high"] < df["low"]).sum())
    close_above_high = int((df["close"] > df["high"]).sum())
    close_below_low = int((df["close"] < df["low"]).sum())
    open_above_high = int((df["open"] > df["high"]).sum())
    open_below_low = int((df["open"] < df["low"]).sum())
    return {
        "high_lt_low": high_lt_low,
        "close_above_high": close_above_high,
        "close_below_low": close_below_low,
        "open_above_high": open_above_high,
        "open_below_low": open_below_low,
    }


def check_nulls(df: pd.DataFrame) -> dict:
    return {"null_counts": df[["open", "high", "low", "close", "volume"]].isnull().sum().to_dict()}


def check_rollovers(df: pd.DataFrame) -> dict:
    """
    NQ rolls quarterly (Mar/Jun/Sep/Dec, ~3rd week of prior month).
    Looks for close-to-open gaps > 0.5% around rollover windows as a proxy
    for whether data is back-adjusted (smooth) or unadjusted (jump at roll).
    """
    # Approximate rollover months: Feb, May, Aug, Nov (week before expiry)
    roll_months = {2, 5, 8, 11}
    roll_mask = df["datetime"].dt.month.isin(roll_months)
    roll_df = df[roll_mask].copy()

    if roll_df.empty:
        return {"rollover_note": "No data in rollover months.", "rollover_gaps": []}

    close_to_open = (roll_df["open"] - roll_df["close"].shift(1)).abs() / roll_df["close"].shift(1)
    large_roll_gaps = close_to_open[close_to_open > 0.005].dropna()

    rollover_gaps = []
    for idx in large_roll_gaps.index[:10]:
        rollover_gaps.append({
            "timestamp": str(roll_df.loc[idx, "datetime"]),
            "prev_close": float(roll_df["close"].iloc[roll_df.index.get_loc(idx) - 1]),
            "open": float(roll_df.loc[idx, "open"]),
            "pct_gap": round(float(large_roll_gaps.loc[idx]) * 100, 3),
        })

    note = (
        "Large gaps detected near rollover windows — data likely UNADJUSTED (raw spliced)."
        if rollover_gaps else
        "No large gaps near rollover windows — data may be BACK-ADJUSTED or clean splice."
    )
    return {"rollover_note": note, "rollover_gaps": rollover_gaps}


def check_price_gaps(df: pd.DataFrame) -> dict:
    pct_change = df["close"].pct_change().abs()
    large_moves = pct_change[pct_change > 0.05].sort_values(ascending=False).head(10)
    results = []
    for idx in large_moves.index:
        results.append(
            {
                "timestamp": str(df.loc[idx, "datetime"]),
                "pct_change": round(float(large_moves.loc[idx]) * 100, 2),
                "close": float(df.loc[idx, "close"]),
                "prev_close": float(df.loc[idx - 1, "close"]) if idx > 0 else None,
            }
        )
    return {
        "anomalous_gap_count": int((pct_change > 0.05).sum()),
        "top_10_anomalous_gaps": results,
    }


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def run_checks(df: pd.DataFrame, tf: str) -> dict:
    results: dict = {}
    results.update(check_row_count(df))
    results.update(check_date_range(df))
    results.update(check_duplicates(df))
    results.update(check_ordering(df))
    results.update(check_missing_bars(df, tf))
    results.update(check_zero_negative_prices(df))
    results.update(check_ohlc_integrity(df))
    results.update(check_nulls(df))
    results.update(check_price_gaps(df))
    results.update(check_rollovers(df))
    return results


def write_report(results: dict, tf: str) -> None:
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = AUDIT_DIR / f"NQ_{tf}_audit.md"

    nulls = results.get("null_counts", {})
    null_lines = "\n".join(f"  - {col}: {cnt}" for col, cnt in nulls.items())

    zp = results.get("zero_or_negative_prices", {})
    zp_lines = "\n".join(f"  - {col}: {cnt}" for col, cnt in zp.items())

    ohlc = results.get("ohlc_integrity", {})

    gaps = results.get("top_10_gaps", [])
    gap_lines = "\n".join(
        f"  - {g['from']} → {g['to']} ({g['missing_bars']} missing bars)" for g in gaps
    )

    price_gaps = results.get("top_10_anomalous_gaps", [])
    pg_lines = "\n".join(
        f"  - {p['timestamp']}: {p['pct_change']}% (prev={p['prev_close']}, curr={p['close']})"
        for p in price_gaps
    )

    dupe_ex = ", ".join(results.get("duplicate_examples", []))
    ooo_ex = ", ".join(results.get("out_of_order_examples", []))

    report = textwrap.dedent(f"""\
    # NQ {tf} Audit Report
    Generated: {datetime.utcnow().isoformat()} UTC

    ## Row Count
    - Total rows: {results.get("row_count")}

    ## Date Range
    - First: {results.get("first_timestamp")}
    - Last: {results.get("last_timestamp")}

    ## Duplicate Timestamps
    - Count: {results.get("duplicate_timestamp_count")}
    - Examples: {dupe_ex or "none"}

    ## Out-of-Order Timestamps
    - Count: {results.get("out_of_order_count")}
    - Examples: {ooo_ex or "none"}

    ## Missing Bars (Intraday Gaps)
    {results.get("missing_bars_note", f"- Total gap events: {results.get('gap_count', 0)}")}
    {gap_lines or "  (no gaps beyond top 10 shown)" if not results.get("missing_bars_note") else ""}

    ## Zero / Negative Prices
    {zp_lines}
    - Zero-volume bars: {results.get("zero_volume_bars")}

    ## OHLC Integrity
    - high < low: {results.get("high_lt_low")}
    - close > high: {results.get("close_above_high")}
    - close < low: {results.get("close_below_low")}
    - open > high: {results.get("open_above_high")}
    - open < low: {results.get("open_below_low")}

    ## NaN / Null Values
    {null_lines}

    ## Anomalous Price Gaps (>5% bar-to-bar close change)
    - Total count: {results.get("anomalous_gap_count")}
    - Top 10:
    {pg_lines or "  none"}

    ## Continuous Contract / Rollover Analysis
    - Assessment: {results.get("rollover_note")}
    - Large gaps near rollover windows (>0.5%):
    {chr(10).join(f"  - {r['timestamp']}: open={r['open']} prev_close={r['prev_close']} gap={r['pct_gap']}%" for r in results.get("rollover_gaps", [])) or "  none"}
    """)

    out_path.write_text(report, encoding="utf-8")
    print(f"  Wrote {out_path}")


def load_raw(tf: str) -> pd.DataFrame:
    meta = TIMEFRAMES[tf]
    raw_path = RAW_DATA_DIR / meta["filename"]
    df = pd.read_csv(raw_path, dtype=str)
    df["datetime"] = pd.to_datetime(
        df["Date"].astype(str) + " " + df["Time"].astype(str),
        format="%m/%d/%Y %H:%M",
    )
    if meta["volume_source"] == "updown":
        df["volume"] = pd.to_numeric(df["Up"], errors="coerce") + pd.to_numeric(df["Down"], errors="coerce")
    else:
        df["volume"] = pd.to_numeric(df["Vol"], errors="coerce")
    df = df.rename(columns={"Open": "open", "High": "high", "Low": "low", "Close": "close"})
    for col in ["open", "high", "low", "close"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df[["datetime", "open", "high", "low", "close", "volume"]]


def print_summary_table(summary: list[dict]) -> None:
    header = f"{'TF':<8} {'Rows':>10} {'Dupes':>8} {'OOO':>6} {'Gaps':>8} {'OHLC_bad':>10} {'NaN':>6}"
    print("\n" + "=" * len(header))
    print(header)
    print("-" * len(header))
    for row in summary:
        ohlc_bad = (
            row.get("high_lt_low", 0)
            + row.get("close_above_high", 0)
            + row.get("close_below_low", 0)
            + row.get("open_above_high", 0)
            + row.get("open_below_low", 0)
        )
        nan_total = sum(row.get("null_counts", {}).values())
        print(
            f"{row['tf']:<8} {row.get('row_count', 0):>10,} "
            f"{row.get('duplicate_timestamp_count', 0):>8,} "
            f"{row.get('out_of_order_count', 0):>6,} "
            f"{row.get('gap_count', '-'):>8} "
            f"{ohlc_bad:>10,} "
            f"{nan_total:>6,}"
        )
    print("=" * len(header) + "\n")


def main() -> None:
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    summary = []

    for tf in TIMEFRAMES:
        print(f"Auditing {tf}...")
        df = load_raw(tf)
        results = run_checks(df, tf)
        results["tf"] = tf
        write_report(results, tf)
        summary.append(results)

    print_summary_table(summary)


if __name__ == "__main__":
    main()
