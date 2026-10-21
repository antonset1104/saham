"""Refresh the EOD research store and publish gated daily/weekly signals."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from contextlib import closing
from datetime import datetime, time
from pathlib import Path
from typing import Any

from market_history_store import JAKARTA, DEFAULT_DB, connect_store, download_and_store, read_daily_bars, validate_symbols
from paper_trading import pending_symbols, read_summary, reconcile_orders, record_decisions
from trading_research import HORIZONS, research_signals, signal_is_actionable


DEFAULT_UNIVERSE = Path("Konfigurasi/trading_universe.txt")
DEFAULT_REPORT = Path("Database/trading_research_report.json")


def report_has_current_eod(path: Path, now: datetime) -> bool:
    """Skip a backup scheduled run only after a complete same-day EOD report."""
    current = now.astimezone(JAKARTA) if now.tzinfo else now.replace(tzinfo=JAKARTA)
    if current.time() < time(17, 45):
        return False
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
        generated = datetime.fromisoformat(report["generated_at"]).astimezone(JAKARTA)
        results = report["results"]
    except (OSError, ValueError, KeyError, TypeError):
        return False
    return (
        generated.date() == current.date()
        and generated.time() >= time(17, 45)
        and all(
            results.get(str(horizon), {}).get("data_asof") == current.date().isoformat()
            and results.get(str(horizon), {}).get("universe_coverage_pct", 0) >= 90
            and results.get(str(horizon), {}).get("status") in ("ready", "no_edge")
            for horizon in HORIZONS
        )
    )


def load_universe(path: Path = DEFAULT_UNIVERSE) -> list[str]:
    if not path.exists():
        raise FileNotFoundError(f"Daftar universe tidak ditemukan: {path}")
    lines = [line.split("#", 1)[0].strip() for line in path.read_text(encoding="utf-8").splitlines()]
    return validate_symbols([line for line in lines if line])


def publish_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile("w", dir=path.parent, prefix=f".{path.name}.", suffix=".tmp",
                                     encoding="utf-8", delete=False) as output:
            temporary = Path(output.name)
            json.dump(payload, output, ensure_ascii=False, indent=2, allow_nan=False)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def run_pipeline(
    symbols: list[str], *, db_path: Path = DEFAULT_DB, report_path: Path = DEFAULT_REPORT,
    period: str = "5y", download: bool = True, now: datetime | None = None,
) -> dict[str, Any]:
    current = now or datetime.now(JAKARTA)
    current = current.astimezone(JAKARTA) if current.tzinfo else current.replace(tzinfo=JAKARTA)
    tickers = validate_symbols(symbols)
    with closing(connect_store(db_path)) as connection:
        watch_symbols = list(dict.fromkeys(tickers + pending_symbols(connection)))
        ingested = (download_and_store(connection, watch_symbols, period=period, now=current)
                    if download else {})
        bars = read_daily_bars(connection, tickers)
    covered = set(bars["ticker"]) if not bars.empty else set()
    missing = sorted(set(tickers) - covered)
    results: dict[str, Any] = {}
    for horizon in HORIZONS:
        try:
            results[str(horizon)] = research_signals(bars, horizon)
            actionable = signal_is_actionable(results[str(horizon)]["data_asof"], current)
            results[str(horizon)]["actionable"] = actionable
            coverage = results[str(horizon)]["symbols_with_latest_bar"] / len(tickers)
            results[str(horizon)]["universe_coverage_pct"] = round(coverage * 100, 1)
            if coverage < 0.90:
                results[str(horizon)]["signals"] = []
                results[str(horizon)]["status"] = "partial_data"
            elif not actionable:
                results[str(horizon)]["signals"] = []
                results[str(horizon)]["status"] = "stale"
        except (ValueError, FloatingPointError) as error:
            results[str(horizon)] = {"status": "insufficient_data", "message": str(error), "signals": []}
    payload = {
        "generated_at": current.astimezone(JAKARTA).isoformat(),
        "universe_size": len(tickers),
        "stored_rows": len(bars),
        "missing_symbols": missing,
        "new_rows": sum(ingested.values()),
        "results": results,
        "data_note": "OHLCV mentah Yahoo dicatat saat pertama diunduh. Backfill sebelum tanggal pengambilan bukan data point-in-time terverifikasi; universe historis masih rentan survivorship bias.",
    }
    journal_time = current if now is not None else datetime.now(JAKARTA)
    with closing(connect_store(db_path)) as connection:
        recorded_runs = record_decisions(connection, payload, now=journal_time)
        settlement_symbols = list(dict.fromkeys(tickers + pending_symbols(connection)))
        settlement_bars = (bars if len(settlement_symbols) == len(tickers)
                           else read_daily_bars(connection, settlement_symbols))
        reconciled_orders = reconcile_orders(
            connection, settlement_bars, now=journal_time,
            universe_size=len(settlement_symbols),
        )
        journal = read_summary(connection, limit=1)
    payload["paper_trading"] = {
        "recorded_runs": recorded_runs,
        "reconciled_orders": reconciled_orders,
        "total_runs": journal["recorded_runs"],
        "order_counts": journal["order_counts"],
    }
    publish_json(report_path, payload)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Riset trading harian/mingguan IDX dengan walk-forward EOD")
    parser.add_argument("--tickers", help="Kode ticker dipisahkan koma; default trading_universe.txt")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--period", choices=("2y", "5y", "10y"), default="5y")
    parser.add_argument("--no-download", action="store_true", help="Uji ulang data SQLite tanpa Yahoo")
    parser.add_argument("--skip-if-current-eod", action="store_true",
                        help="Cadangan scheduler: lewati bila laporan EOD hari ini sudah lengkap")
    args = parser.parse_args()
    if args.skip_if_current_eod and report_has_current_eod(args.report, datetime.now(JAKARTA)):
        print("Laporan EOD hari ini sudah lengkap; pembaruan cadangan dilewati.")
        return 0
    symbols = validate_symbols(args.tickers.split(",")) if args.tickers else load_universe()
    try:
        report = run_pipeline(symbols, db_path=args.db, report_path=args.report,
                              period=args.period, download=not args.no_download)
    except Exception as error:
        parser.exit(1, f"Pipeline gagal: {error}\n")
    print(json.dumps({
        "generated_at": report["generated_at"], "universe_size": report["universe_size"],
        "stored_rows": report["stored_rows"], "new_rows": report["new_rows"],
        "horizons": {key: {"status": result["status"], "signals": len(result["signals"])}
                     for key, result in report["results"].items()},
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
