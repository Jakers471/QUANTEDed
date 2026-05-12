from datetime import time
from pathlib import Path

import pandas as pd
import pytz

TZ_CT = pytz.timezone("America/Chicago")
TZ_NY = pytz.timezone("America/New_York")

RAW_DATA_DIR = Path(r"C:\Users\jakers\Desktop\quanted\data")
CLEAN_DATA_DIR = Path(r"C:\Users\jakers\Desktop\quanted\data\clean")

# NQ futures: Sunday 17:00 CT open, Friday 16:00 CT close
# Saturday is fully closed; Sunday before 17:00 is closed.
NQ_SESSION_START = time(17, 0)  # 5:00 PM CT (prior-day evening open)
NQ_SESSION_END = time(16, 0)    # 4:00 PM CT

# NY regular session (RTH): 9:30 AM – 4:00 PM ET
NY_RTH_OPEN  = time(9, 30)
NY_RTH_CLOSE = time(16, 0)


def filter_ny_session(df: pd.DataFrame) -> pd.DataFrame:
    """
    Keep only bars whose close falls within NY regular trading hours (9:30–16:00 ET).
    Input must have a UTC-aware DatetimeIndex. 1day bars are passed through unchanged.
    """
    ny_times = df.index.tz_convert(TZ_NY)
    mask = (ny_times.time >= NY_RTH_OPEN) & (ny_times.time <= NY_RTH_CLOSE)
    return df[mask]

# volume_source:
#   "updown" — intraday exports have Up/Down tick columns; volume = Up + Down
#   "vol"    — daily export has an explicit Vol column
TIMEFRAMES: dict[str, dict] = {
    "1min": {
        "bar_minutes": 1,
        "filename": "nq120.txt",
        "volume_source": "updown",
    },
    "5min": {
        "bar_minutes": 5,
        "filename": "nq520.txt",
        "volume_source": "updown",
    },
    "15min": {
        "bar_minutes": 15,
        "filename": "na1520.txt",
        "volume_source": "updown",
    },
    "60min": {
        "bar_minutes": 60,
        "filename": "nq6020.txt",
        "volume_source": "updown",
    },
    "1day": {
        "bar_minutes": 1440,
        "filename": "nq1day20.txt",
        "volume_source": "vol",
    },
}


def bar_duration_minutes(tf: str) -> int:
    if tf not in TIMEFRAMES:
        raise ValueError(f"Unknown timeframe: {tf!r}. Valid: {list(TIMEFRAMES)}")
    return TIMEFRAMES[tf]["bar_minutes"]
