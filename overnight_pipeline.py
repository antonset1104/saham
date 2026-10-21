"""Collect IDX five-minute bars and publish a gated overnight research report."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from intraday_history_store import download_intraday_bars, read_intraday_bars
from market_history_store import DEFAULT_DB, JAKARTA, connect_store, validate_symbols
from overnight_research import research_overnight
from trading_pipeline import load_universe, publish_json


DEFAULT_REPORT = Path("Database/overnight_research_report.json")


def run_pipeline(
    symbols: list[str], *, db_path: Path = DEFAULT_DB, report_path: Path = DEFAULT_REPORT,
    download: bool = True, now: datetime | None = None,
) -> dict[str, Any]:
    current = now or datetime.now(JAKARTA)
    current = current.astimezone(JAKARTA) if current.tzinfo else current.replace(tzinfo=JAKARTA)
    tickers = validate_symbols(symbols)
    with connect_store(db_path) as connection:
        ingested = download_intraday_bars(connection, tickers, now=now) if download else {}
        bars = read_intraday_bars(connection, tickers)
    if now is None:
        current = datetime.now(JAKARTA)
    try:
        result = research_overnight(bars, now=current)
        coverage = result["symbols_with_signal_bar"] / len(tickers)
        result["universe_coverage_pct"] = round(coverage * 100, 1)
        if coverage < 0.9:
            result["status"] = "partial_data"
            result["signals"] = []
    except (ValueError, FloatingPointError) as error:
        result = {"status": "insufficient_data", "message": str(error), "signals": []}
    payload = {
        "generated_at": current.isoformat(), "universe_size": len(tickers),
        "stored_rows": len(bars), "new_rows": sum(ingested.values()),
        "result": result,
        "data_note": "Yahoo 5m backfill bukan arsip point-in-time. Sinyal hanya boleh lolos setelah hari validasi dan holdout diamati sebelum waktu sinyal; eksekusi harga open bar adalah asumsi dengan slippage, bukan jaminan fill.",
    }
    publish_json(report_path, payload)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Riset overnight IDX 14:45 WIB")
    parser.add_argument("--tickers", help="Kode ticker dipisahkan koma")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--no-download", action="store_true")
    args = parser.parse_args()
    symbols = validate_symbols(args.tickers.split(",")) if args.tickers else load_universe()
    try:
        report = run_pipeline(symbols, db_path=args.db, report_path=args.report,
                              download=not args.no_download)
    except Exception as error:
        parser.exit(1, f"Pipeline overnight gagal: {error}\n")
    print(json.dumps({
        "generated_at": report["generated_at"], "stored_rows": report["stored_rows"],
        "new_rows": report["new_rows"], "status": report["result"]["status"],
        "signals": len(report["result"]["signals"]),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
