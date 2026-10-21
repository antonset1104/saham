"""Append-only daily OHLCV observations for repeatable trading research."""

from __future__ import annotations

import re
import sqlite3
from datetime import datetime, time, timedelta
import logging
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from market_tls import configure_yahoo_tls


JAKARTA = ZoneInfo("Asia/Jakarta")
DEFAULT_DB = Path("Database/market_history.sqlite3")
SYMBOL_PATTERN = re.compile(r"[A-Z0-9]{3,6}")
LOGGER = logging.getLogger(__name__)


def validate_symbols(symbols: list[str]) -> list[str]:
    cleaned = list(dict.fromkeys(symbol.strip().upper() for symbol in symbols))
    if not cleaned or any(not SYMBOL_PATTERN.fullmatch(symbol) for symbol in cleaned):
        raise ValueError("Daftar ticker harus berisi kode IDX 3–6 karakter alfanumerik.")
    return cleaned


def connect_store(path: Path = DEFAULT_DB) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=30)
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("""
        CREATE TABLE IF NOT EXISTS daily_bars (
            ticker TEXT NOT NULL,
            trade_date TEXT NOT NULL,
            open REAL NOT NULL CHECK (open > 0),
            high REAL NOT NULL CHECK (high > 0),
            low REAL NOT NULL CHECK (low > 0),
            close REAL NOT NULL CHECK (close > 0),
            volume INTEGER NOT NULL CHECK (volume >= 0),
            first_seen_at TEXT NOT NULL,
            source TEXT NOT NULL,
            PRIMARY KEY (ticker, trade_date)
        )
    """)
    return connection


def normalize_daily_bars(raw: pd.DataFrame, *, now: datetime | None = None) -> pd.DataFrame:
    """Keep completed regular daily bars; reject impossible OHLC values."""
    current = now or datetime.now(JAKARTA)
    current = current.astimezone(JAKARTA) if current.tzinfo else current.replace(tzinfo=JAKARTA)
    data = raw.copy()
    if isinstance(data.columns, pd.MultiIndex):
        data.columns = data.columns.get_level_values(0)
    columns = ["Open", "High", "Low", "Close", "Volume"]
    if any(column not in data for column in columns):
        raise ValueError("Data Yahoo tidak memiliki OHLCV lengkap.")
    data = data[columns].apply(pd.to_numeric, errors="coerce")
    dates = pd.to_datetime(data.index)
    data.index = dates.tz_convert(JAKARTA).tz_localize(None) if dates.tz is not None else dates
    data = data.sort_index()
    data = data[~data.index.duplicated(keep="last")]
    data = data.replace([np.inf, -np.inf], np.nan).dropna()
    data = data[(data[columns[:4]] > 0).all(axis=1) & (data["Volume"] >= 0)]
    data = data[(data["High"] >= data[["Open", "Close", "Low"]].max(axis=1))
                & (data["Low"] <= data[["Open", "Close", "High"]].min(axis=1))]
    if current.time() < time(17, 30):
        data = data[data.index.date < current.date()]
    else:
        data = data[data.index.date <= current.date()]
    return data


def insert_daily_bars(
    connection: sqlite3.Connection,
    ticker: str,
    raw: pd.DataFrame,
    *,
    now: datetime | None = None,
) -> int:
    symbol = validate_symbols([ticker])[0]
    observed = now or datetime.now(JAKARTA)
    observed = observed.astimezone(JAKARTA) if observed.tzinfo else observed.replace(tzinfo=JAKARTA)
    data = normalize_daily_bars(raw, now=observed)
    rows = [
        (symbol, index.date().isoformat(), float(row.Open), float(row.High), float(row.Low),
         float(row.Close), int(row.Volume), observed.isoformat(), "yahoo_raw_first_observation")
        for index, row in data.iterrows()
    ]
    before = connection.total_changes
    with connection:
        connection.executemany(
            "INSERT OR IGNORE INTO daily_bars VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", rows
        )
    return connection.total_changes - before


def read_daily_bars(connection: sqlite3.Connection, symbols: list[str]) -> pd.DataFrame:
    tickers = validate_symbols(symbols)
    placeholders = ",".join("?" for _ in tickers)
    data = pd.read_sql_query(
        f"SELECT ticker, trade_date, open, high, low, close, volume, first_seen_at "
        f"FROM daily_bars WHERE ticker IN ({placeholders}) ORDER BY trade_date, ticker",
        connection,
        params=tickers,
    )
    if not data.empty:
        data["trade_date"] = pd.to_datetime(data["trade_date"])
    return data


def download_and_store(
    connection: sqlite3.Connection,
    symbols: list[str],
    *,
    period: str = "5y",
    now: datetime | None = None,
) -> dict[str, int]:
    """Import Yahoo raw prices once per date; old observations stay unchanged."""
    import yfinance as yf

    configure_yahoo_tls()
    tickers = validate_symbols(symbols)
    counts: dict[str, int] = {}
    current = now or datetime.now(JAKARTA)
    latest_rows = connection.execute(
        "SELECT ticker, MAX(trade_date) FROM daily_bars GROUP BY ticker"
    ).fetchall()
    latest = {ticker: datetime.fromisoformat(date).date() for ticker, date in latest_rows}
    recent = [ticker for ticker in tickers if ticker in latest
              and latest[ticker] >= current.date() - timedelta(days=25)]
    backfill = [ticker for ticker in tickers if ticker not in recent]
    batches = [(recent, "1mo"), (backfill, period)]
    for group, fetch_period in batches:
        for offset in range(0, len(group), 10):
            chunk = group[offset:offset + 10]
            yahoo_symbols = [f"{ticker}.JK" for ticker in chunk]
            raw = yf.download(
                " ".join(yahoo_symbols), period=fetch_period, interval="1d", group_by="ticker",
                auto_adjust=False, progress=False, threads=min(len(chunk), 5), timeout=20,
            )
            failed: list[str] = []
            for ticker, yahoo_symbol in zip(chunk, yahoo_symbols):
                frame: pd.DataFrame | None = None
                if raw is not None and not raw.empty:
                    if isinstance(raw.columns, pd.MultiIndex):
                        if yahoo_symbol in raw.columns.get_level_values(0):
                            frame = raw[yahoo_symbol]
                        elif yahoo_symbol in raw.columns.get_level_values(1):
                            frame = raw.xs(yahoo_symbol, axis=1, level=1)
                    elif len(chunk) == 1:
                        frame = raw
                try:
                    if frame is None or frame.empty or frame["Close"].notna().sum() == 0:
                        failed.append(ticker)
                        continue
                    counts[ticker] = insert_daily_bars(connection, ticker, frame, now=now)
                except (ValueError, KeyError):
                    failed.append(ticker)
            for ticker in failed:
                yahoo_symbol = f"{ticker}.JK"
                try:
                    single = yf.download(
                        yahoo_symbol, period=fetch_period, interval="1d", auto_adjust=False,
                        progress=False, threads=False, timeout=20,
                    )
                    if single is None or single.empty:
                        counts[ticker] = 0
                        LOGGER.warning("Yahoo tidak memberi bar untuk %s", ticker)
                        continue
                    counts[ticker] = insert_daily_bars(connection, ticker, single, now=now)
                except Exception as error:
                    counts[ticker] = 0
                    LOGGER.warning("Gagal mengambil bar %s: %s", ticker, error)
    return counts
