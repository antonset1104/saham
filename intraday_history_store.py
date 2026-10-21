"""First-observed IDX five-minute bars for overnight trading research."""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from market_history_store import JAKARTA, validate_symbols
from market_tls import configure_yahoo_tls


LOGGER = logging.getLogger(__name__)
BAR_INTERVAL = timedelta(minutes=5)


def ensure_intraday_table(connection: sqlite3.Connection) -> None:
    connection.execute("""
        CREATE TABLE IF NOT EXISTS intraday_bars (
            ticker TEXT NOT NULL,
            bar_time TEXT NOT NULL,
            open REAL NOT NULL CHECK(open > 0),
            high REAL NOT NULL CHECK(high > 0),
            low REAL NOT NULL CHECK(low > 0),
            close REAL NOT NULL CHECK(close > 0),
            volume INTEGER NOT NULL CHECK(volume >= 0),
            first_seen_at TEXT NOT NULL,
            PRIMARY KEY(ticker, bar_time)
        )
    """)


def normalize_intraday_bars(raw: pd.DataFrame, *, now: datetime | None = None) -> pd.DataFrame:
    current = now or datetime.now(JAKARTA)
    current = current.astimezone(JAKARTA) if current.tzinfo else current.replace(tzinfo=JAKARTA)
    data = raw.copy()
    if isinstance(data.columns, pd.MultiIndex):
        data.columns = data.columns.get_level_values(0)
    columns = ["Open", "High", "Low", "Close", "Volume"]
    if any(column not in data for column in columns):
        raise ValueError("Data intraday Yahoo tidak memiliki OHLCV lengkap.")
    data = data[columns].apply(pd.to_numeric, errors="coerce")
    timestamps = pd.to_datetime(data.index)
    if timestamps.tz is None:
        raise ValueError("Candle intraday harus memiliki zona waktu bursa.")
    data.index = timestamps.tz_convert(JAKARTA)
    data = data.sort_index()
    data = data[~data.index.duplicated(keep="first")]
    data = data.replace([np.inf, -np.inf], np.nan).dropna()
    data = data[(data[columns[:4]] > 0).all(axis=1) & (data["Volume"] >= 0)]
    data = data[(data["High"] >= data[["Open", "Close", "Low"]].max(axis=1))
                & (data["Low"] <= data[["Open", "Close", "High"]].min(axis=1))]
    # Keep only complete five-minute bars; Yahoo also returns pre/post-auction bars.
    data = data[data.index + pd.Timedelta(minutes=5) <= pd.Timestamp(current)]
    minutes = data.index.hour * 60 + data.index.minute
    friday = data.index.weekday == 4
    morning_end = np.where(friday, 11 * 60 + 25, 11 * 60 + 55)
    afternoon_start = np.where(friday, 14 * 60, 13 * 60 + 30)
    regular = ((minutes >= 9 * 60) & (minutes <= morning_end)) | (
        (minutes >= afternoon_start) & (minutes <= 15 * 60 + 45)
    )
    return data[regular]


def insert_intraday_bars(
    connection: sqlite3.Connection, ticker: str, raw: pd.DataFrame, *, now: datetime | None = None,
) -> int:
    symbol = validate_symbols([ticker])[0]
    ensure_intraday_table(connection)
    current = now or datetime.now(JAKARTA)
    current = current.astimezone(JAKARTA) if current.tzinfo else current.replace(tzinfo=JAKARTA)
    data = normalize_intraday_bars(raw, now=current)
    rows = [
        (symbol, stamp.isoformat(), float(row.Open), float(row.High), float(row.Low),
         float(row.Close), int(row.Volume), current.isoformat())
        for stamp, row in data.iterrows()
    ]
    before = connection.total_changes
    with connection:
        connection.executemany(
            "INSERT OR IGNORE INTO intraday_bars VALUES (?, ?, ?, ?, ?, ?, ?, ?)", rows
        )
    return connection.total_changes - before


def read_intraday_bars(connection: sqlite3.Connection, symbols: list[str]) -> pd.DataFrame:
    tickers = validate_symbols(symbols)
    ensure_intraday_table(connection)
    placeholders = ",".join("?" for _ in tickers)
    data = pd.read_sql_query(
        f"SELECT ticker, bar_time, open, high, low, close, volume, first_seen_at "
        f"FROM intraday_bars WHERE ticker IN ({placeholders}) ORDER BY bar_time, ticker",
        connection, params=tickers,
    )
    if not data.empty:
        data["bar_time"] = pd.to_datetime(data["bar_time"], utc=True).dt.tz_convert(JAKARTA)
    return data


def download_intraday_bars(
    connection: sqlite3.Connection, symbols: list[str], *, now: datetime | None = None,
) -> dict[str, int]:
    """Bootstrap Yahoo's limited history, then refresh a rolling five-day window."""
    import yfinance as yf

    configure_yahoo_tls()
    tickers = validate_symbols(symbols)
    ensure_intraday_table(connection)
    latest = dict(connection.execute(
        "SELECT ticker, MAX(bar_time) FROM intraday_bars GROUP BY ticker"
    ).fetchall())
    counts: dict[str, int] = {}
    for offset in range(0, len(tickers), 5):
        chunk = tickers[offset:offset + 5]
        for period in ("60d", "5d"):
            selected = [ticker for ticker in chunk if (ticker not in latest) == (period == "60d")]
            if not selected:
                continue
            names = [f"{ticker}.JK" for ticker in selected]
            try:
                raw = yf.download(" ".join(names), period=period, interval="5m",
                                  group_by="ticker", auto_adjust=False, progress=False,
                                  threads=min(len(names), 5), timeout=25)
            except Exception as error:
                LOGGER.warning("Unduhan intraday batch gagal: %s", error)
                raw = pd.DataFrame()
            for ticker, name in zip(selected, names):
                frame: pd.DataFrame | None = None
                if not raw.empty:
                    if isinstance(raw.columns, pd.MultiIndex):
                        if name in raw.columns.get_level_values(0):
                            frame = raw[name]
                        elif name in raw.columns.get_level_values(1):
                            frame = raw.xs(name, axis=1, level=1)
                    elif len(selected) == 1:
                        frame = raw
                if frame is None or frame.empty or frame.get("Close", pd.Series(dtype=float)).notna().sum() == 0:
                    try:
                        frame = yf.download(name, period=period, interval="5m", auto_adjust=False,
                                            progress=False, threads=False, timeout=25)
                    except Exception as error:
                        LOGGER.warning("Unduhan intraday %s gagal: %s", ticker, error)
                        counts[ticker] = 0
                        continue
                try:
                    counts[ticker] = insert_intraday_bars(connection, ticker, frame, now=now)
                except (ValueError, KeyError) as error:
                    LOGGER.warning("Bar intraday %s ditolak: %s", ticker, error)
                    counts[ticker] = 0
    return counts
