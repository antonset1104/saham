"""Morning snapshot of major equity indices, with explicit exchange session dates."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import html
import math

import pandas as pd

from market_tls import configure_yahoo_tls


@dataclass(frozen=True)
class Index:
    name: str
    symbol: str


INDICES = (
    Index("IHSG", "^JKSE"),
    Index("Nikkei 225", "^N225"),
    Index("Hang Seng", "^HSI"),
    Index("Shanghai", "000001.SS"),
    Index("STI", "^STI"),
    Index("S&P 500", "^GSPC"),
    Index("Dow Jones", "^DJI"),
    Index("Nasdaq", "^IXIC"),
    Index("FTSE 100", "^FTSE"),
    Index("DAX", "^GDAXI"),
)


def _valid(value: object) -> float | None:
    try:
        number = float(value)
        return number if math.isfinite(number) and number > 0 else None
    except (TypeError, ValueError):
        return None


def _symbol_frame(download: pd.DataFrame, symbol: str) -> pd.DataFrame:
    if download.empty:
        return pd.DataFrame()
    if isinstance(download.columns, pd.MultiIndex):
        try:
            if symbol in download.columns.get_level_values(1):
                return download.xs(symbol, axis=1, level=1)
            return download.xs(symbol, axis=1, level=0)
        except KeyError:
            return pd.DataFrame()
    return download if len(INDICES) == 1 else pd.DataFrame()


def format_index_lines(download: pd.DataFrame, now: datetime) -> list[str]:
    """Never interpret an earlier session's open as today's opening quote."""
    today = now.date()
    lines = ["\n🌍 <b>INDEKS BURSA DUNIA</b>", "Penutupan sesi terakhir → pembukaan hari ini (tanggal WIB)"]
    for index in INDICES:
        frame = _symbol_frame(download, index.symbol)
        sessions: list[tuple[object, float | None, float | None]] = []
        for timestamp, row in frame.iterrows():
            day = pd.Timestamp(timestamp).date()
            if day <= today:
                sessions.append((day, _valid(row.get("Close")), _valid(row.get("Open"))))
        previous = next(((day, close) for day, close, _ in reversed(sessions)
                         if day < today and close is not None), None)
        opening = next(((day, opened) for day, _, opened in reversed(sessions)
                        if day == today and opened is not None), None)
        if previous:
            day, close = previous
            close_text = f"{close:,.2f} ({day:%d/%m})"
        else:
            close_text = "data belum tersedia"
        open_text = f"{opening[1]:,.2f}" if opening else "belum buka / data belum tersedia"
        gap = f" ({(opening[1] / previous[1] - 1) * 100:+.2f}%)" if previous and opening else ""
        lines.append(f"• <b>{html.escape(index.name)}</b>: tutup {close_text} → buka {open_text}{gap}")
    lines.append("<i>Sumber: Yahoo Finance; harga indeks bisa tertunda. Tanggal tutup mengikuti sesi bursa masing-masing.</i>")
    return lines


def morning_index_lines(now: datetime) -> list[str]:
    configure_yahoo_tls()
    try:
        import yfinance as yf

        download = yf.download(
            [index.symbol for index in INDICES], period="10d", interval="1d",
            auto_adjust=False, progress=False, threads=True, timeout=12,
        )
    except Exception:
        download = pd.DataFrame()
    return format_index_lines(download, now)
