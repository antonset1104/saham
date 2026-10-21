"""Append-only EOD decisions and forward-only simulated trade reconciliation."""

from __future__ import annotations

import json
import math
import sqlite3
from contextlib import closing
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from market_history_store import JAKARTA, validate_symbols
from mesin_forecast import BUY_FEE, SELL_FEE
from trading_research import HORIZONS, SLIPPAGE_PER_SIDE, signal_is_actionable


PAPER_BUDGET_IDR = 10_000_000
IDX_LOT_SHARES = 100


def ensure_tables(connection: sqlite3.Connection) -> None:
    connection.executescript("""
        CREATE TABLE IF NOT EXISTS paper_runs (
            id INTEGER PRIMARY KEY,
            model_version TEXT NOT NULL,
            horizon INTEGER NOT NULL,
            signal_date TEXT NOT NULL,
            report_generated_at TEXT NOT NULL,
            recorded_at TEXT NOT NULL,
            decision_status TEXT NOT NULL,
            decision_json TEXT NOT NULL,
            UNIQUE (model_version, horizon, signal_date)
        );
        CREATE TABLE IF NOT EXISTS paper_orders (
            id INTEGER PRIMARY KEY,
            run_id INTEGER NOT NULL REFERENCES paper_runs(id),
            ticker TEXT NOT NULL,
            probability_pct REAL NOT NULL,
            signal_close REAL NOT NULL,
            status TEXT NOT NULL,
            entry_date TEXT,
            entry_open REAL,
            entry_first_seen_at TEXT,
            exit_date TEXT,
            exit_close REAL,
            exit_first_seen_at TEXT,
            quantity_shares INTEGER,
            net_return_pct REAL,
            pnl_idr REAL,
            note TEXT,
            updated_at TEXT NOT NULL,
            UNIQUE (run_id, ticker)
        );
        CREATE INDEX IF NOT EXISTS idx_paper_orders_status ON paper_orders(status);
    """)


def _local_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError("Waktu laporan harus memiliki zona waktu.")
    return parsed.astimezone(JAKARTA)


def record_decisions(
    connection: sqlite3.Connection, report: dict[str, Any], *, now: datetime | None = None,
) -> int:
    """Freeze the first eligible published decision for each date and horizon."""
    ensure_tables(connection)
    observed = now or datetime.now(JAKARTA)
    observed = observed.astimezone(JAKARTA) if observed.tzinfo else observed.replace(tzinfo=JAKARTA)
    generated = _local_time(report["generated_at"])
    recorded = 0
    with connection:
        for horizon in HORIZONS:
            result = report.get("results", {}).get(str(horizon), {})
            signal_date = result.get("data_asof")
            if (result.get("status") not in ("ready", "no_edge")
                    or not result.get("actionable")
                    or result.get("universe_coverage_pct", 0) < 90
                    or signal_date != generated.date().isoformat()
                    or generated > observed
                    or not signal_is_actionable(signal_date, observed)):
                continue
            datetime.fromisoformat(signal_date)
            signals = result.get("signals", [])
            symbols = validate_symbols([signal["ticker"] for signal in signals]) if signals else []
            if len(symbols) != len(signals):
                raise ValueError("Sinyal paper trading berisi ticker duplikat.")
            decision = json.dumps(result, ensure_ascii=False, sort_keys=True, allow_nan=False)
            cursor = connection.execute(
                "INSERT OR IGNORE INTO paper_runs "
                "(model_version, horizon, signal_date, report_generated_at, recorded_at, "
                "decision_status, decision_json) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (result["version"], horizon, signal_date, generated.isoformat(),
                 observed.isoformat(), result["status"], decision),
            )
            if cursor.rowcount == 0:
                continue
            recorded += 1
            run_id = cursor.lastrowid
            for signal in signals:
                probability = float(signal["probability_pct"])
                close = float(signal["last_close"])
                if not math.isfinite(probability) or not 0 <= probability <= 100:
                    raise ValueError("Probabilitas sinyal tidak valid.")
                if not math.isfinite(close) or close <= 0:
                    raise ValueError("Harga penutupan sinyal tidak valid.")
                connection.execute(
                    "INSERT INTO paper_orders "
                    "(run_id, ticker, probability_pct, signal_close, status, updated_at) "
                    "VALUES (?, ?, ?, ?, 'pending_entry', ?)",
                    (run_id, signal["ticker"], probability, close, observed.isoformat()),
                )
    return recorded


def reconcile_orders(
    connection: sqlite3.Connection, bars: pd.DataFrame, *, now: datetime | None = None,
    universe_size: int,
) -> int:
    """Use only completed bars first observed after the archived signal."""
    ensure_tables(connection)
    if bars.empty or universe_size < 1:
        return 0
    observed = now or datetime.now(JAKARTA)
    observed = observed.astimezone(JAKARTA) if observed.tzinfo else observed.replace(tzinfo=JAKARTA)
    frame = bars.copy()
    frame["trade_date"] = pd.to_datetime(frame["trade_date"]).dt.date.astype(str)
    frame = frame.drop_duplicates(["ticker", "trade_date"], keep="first")
    dates = sorted(frame["trade_date"].unique())
    position = {date: index for index, date in enumerate(dates)}
    counts = frame.groupby("trade_date")["ticker"].nunique().to_dict()
    lookup = {(row.ticker, row.trade_date): row for row in frame.itertuples(index=False)}
    pending = connection.execute(
        "SELECT o.id, o.ticker, o.status, o.entry_date, o.entry_open, "
        "o.entry_first_seen_at, r.horizon, r.signal_date, r.report_generated_at "
        "FROM paper_orders o JOIN paper_runs r ON r.id = o.run_id "
        "WHERE o.status IN ('pending_entry', 'open') ORDER BY r.signal_date, o.id"
    ).fetchall()
    changed = 0
    with connection:
        for (order_id, ticker, status, entry_date, entry_open, entry_seen,
             horizon, signal_date, generated_at) in pending:
            origin = position.get(signal_date)
            if origin is None or origin + 1 >= len(dates):
                continue
            target_entry = dates[origin + 1]
            if counts[target_entry] / universe_size < 0.9:
                continue
            if status == "pending_entry":
                entry = lookup.get((ticker, target_entry))
                if entry is None:
                    connection.execute(
                        "UPDATE paper_orders SET entry_date=?, "
                        "note='Harga open belum tersedia; menunggu perbaikan data', updated_at=? WHERE id=?",
                        (target_entry, observed.isoformat(), order_id),
                    )
                    continue
                if (_local_time(entry.first_seen_at) <= _local_time(generated_at)
                        or _local_time(entry.first_seen_at).date() != date.fromisoformat(target_entry)
                        or not math.isfinite(float(entry.open))
                        or float(entry.open) <= 0):
                    connection.execute(
                        "UPDATE paper_orders SET status='unverified_entry', entry_date=?, "
                        "note='Bar entry tidak diamati pada hari transaksi', updated_at=? WHERE id=?",
                        (target_entry, observed.isoformat(), order_id),
                    )
                    changed += 1
                    continue
                entry_price = float(entry.open)
                shares = math.floor(
                    PAPER_BUDGET_IDR / (entry_price * (1 + BUY_FEE + SLIPPAGE_PER_SIDE))
                    / IDX_LOT_SHARES
                ) * IDX_LOT_SHARES
                if shares < IDX_LOT_SHARES:
                    connection.execute(
                        "UPDATE paper_orders SET status='insufficient_budget', entry_date=?, "
                        "note='Anggaran simulasi tidak cukup untuk satu lot', updated_at=? WHERE id=?",
                        (target_entry, observed.isoformat(), order_id),
                    )
                    changed += 1
                    continue
                connection.execute(
                    "UPDATE paper_orders SET status='open', entry_date=?, entry_open=?, "
                    "entry_first_seen_at=?, quantity_shares=?, updated_at=? WHERE id=?",
                    (target_entry, entry_price, entry.first_seen_at, shares,
                     observed.isoformat(), order_id),
                )
                entry_date, entry_open, entry_seen = target_entry, entry_price, entry.first_seen_at
                changed += 1
            target_index = origin + horizon
            if target_index >= len(dates):
                continue
            target_exit = dates[target_index]
            if counts[target_exit] / universe_size < 0.9:
                continue
            exit_bar = lookup.get((ticker, target_exit))
            if exit_bar is None:
                connection.execute(
                    "UPDATE paper_orders SET exit_date=?, "
                    "note='Harga close belum tersedia; menunggu perbaikan data', updated_at=? WHERE id=?",
                    (target_exit, observed.isoformat(), order_id),
                )
                continue
            if (not math.isfinite(float(exit_bar.close))
                    or float(exit_bar.close) <= 0
                    or _local_time(exit_bar.first_seen_at).date() != date.fromisoformat(target_exit)
                    or _local_time(exit_bar.first_seen_at) < _local_time(entry_seen)):
                connection.execute(
                    "UPDATE paper_orders SET status='unverified_exit', exit_date=?, "
                    "note='Harga close keluar tidak terverifikasi', updated_at=? WHERE id=?",
                    (target_exit, observed.isoformat(), order_id),
                )
                changed += 1
                continue
            shares = connection.execute(
                "SELECT quantity_shares FROM paper_orders WHERE id=?", (order_id,)
            ).fetchone()[0]
            buy_cost = shares * float(entry_open) * (1 + BUY_FEE + SLIPPAGE_PER_SIDE)
            sale_value = shares * float(exit_bar.close) * (1 - SELL_FEE - SLIPPAGE_PER_SIDE)
            connection.execute(
                "UPDATE paper_orders SET status='closed', exit_date=?, exit_close=?, "
                "exit_first_seen_at=?, net_return_pct=?, pnl_idr=?, note=NULL, updated_at=? WHERE id=?",
                (target_exit, float(exit_bar.close), exit_bar.first_seen_at,
                 round((sale_value / buy_cost - 1) * 100, 4), round(sale_value - buy_cost, 2),
                 observed.isoformat(), order_id),
            )
            changed += 1
    return changed


def pending_symbols(connection: sqlite3.Connection) -> list[str]:
    ensure_tables(connection)
    return [row[0] for row in connection.execute(
        "SELECT DISTINCT ticker FROM paper_orders "
        "WHERE status IN ('pending_entry', 'open') ORDER BY ticker"
    ).fetchall()]


def read_summary(connection: sqlite3.Connection, *, limit: int = 20) -> dict[str, Any]:
    if limit < 1 or limit > 100:
        raise ValueError("Batas baris jurnal harus 1–100.")
    run_counts = dict(connection.execute(
        "SELECT decision_status, COUNT(*) FROM paper_runs GROUP BY decision_status"
    ).fetchall())
    order_counts = dict(connection.execute(
        "SELECT status, COUNT(*) FROM paper_orders GROUP BY status"
    ).fetchall())
    closed = connection.execute(
        "SELECT COALESCE(SUM(pnl_idr), 0), AVG(net_return_pct) "
        "FROM paper_orders WHERE status='closed'"
    ).fetchone()
    rows = connection.execute(
        "SELECT r.signal_date, r.horizon, o.ticker, o.probability_pct, o.status, "
        "o.entry_date, o.entry_open, o.exit_date, o.exit_close, o.net_return_pct, "
        "o.pnl_idr, o.note FROM paper_orders o "
        "JOIN paper_runs r ON r.id=o.run_id ORDER BY r.signal_date DESC, o.id DESC LIMIT ?",
        (limit,),
    ).fetchall()
    columns = ("signal_date", "horizon", "ticker", "probability_pct", "status",
               "entry_date", "entry_open", "exit_date", "exit_close",
               "net_return_pct", "pnl_idr", "note")
    return {
        "recorded_runs": sum(run_counts.values()),
        "no_signal_runs": run_counts.get("no_edge", 0),
        "order_counts": order_counts,
        "closed_pnl_idr": round(float(closed[0]), 2),
        "average_closed_return_pct": round(float(closed[1]), 4) if closed[1] is not None else None,
        "orders": [dict(zip(columns, row)) for row in rows],
    }


def load_summary(path: Path, *, limit: int = 20) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    uri = f"{path.resolve().as_uri()}?mode=ro"
    with closing(sqlite3.connect(uri, uri=True, timeout=10)) as connection:
        if connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='paper_runs'"
        ).fetchone() is None:
            return None
        return read_summary(connection, limit=limit)
