import sqlite3
import tempfile
import unittest
from contextlib import closing
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from paper_trading import load_summary, read_summary, reconcile_orders, record_decisions


JAKARTA = ZoneInfo("Asia/Jakarta")
SIGNAL_TIME = datetime(2026, 10, 19, 18, 30, tzinfo=JAKARTA)
NEXT_EOD = datetime(2026, 10, 20, 18, 30, tzinfo=JAKARTA)


def report() -> dict:
    return {
        "generated_at": SIGNAL_TIME.isoformat(),
        "results": {
            "1": {
                "version": "paper-test-v1", "status": "ready", "actionable": True,
                "universe_coverage_pct": 100.0, "data_asof": "2026-10-19",
                "signals": [{"ticker": "AAA", "probability_pct": 70.0, "last_close": 100.0}],
            },
            "5": {
                "version": "paper-test-v1", "status": "no_edge", "actionable": True,
                "universe_coverage_pct": 100.0, "data_asof": "2026-10-19", "signals": [],
            },
        },
    }


def bars(*, include_next: bool, entry_seen: str = "2026-10-20T18:00:00+07:00") -> pd.DataFrame:
    dates = ["2026-10-19"] + (["2026-10-20"] if include_next else [])
    records = []
    for date in dates:
        for ticker in ("AAA", "BBB"):
            records.append({
                "ticker": ticker, "trade_date": date,
                "open": 110.0 if date == "2026-10-20" else 100.0,
                "close": 120.0 if date == "2026-10-20" else 100.0,
                "first_seen_at": (entry_seen if date == "2026-10-20"
                                  else "2026-10-19T18:00:00+07:00"),
            })
    return pd.DataFrame(records)


class PaperTradingTest(unittest.TestCase):
    def test_decisions_are_immutable_and_forward_trade_settles_after_next_eod(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "market.sqlite3"
            with closing(sqlite3.connect(path)) as connection:
                self.assertEqual(record_decisions(connection, report(), now=SIGNAL_TIME), 2)
                self.assertEqual(reconcile_orders(
                    connection, bars(include_next=False), now=SIGNAL_TIME, universe_size=2,
                ), 0)
                initial = read_summary(connection)
                self.assertEqual(initial["no_signal_runs"], 1)
                self.assertEqual(initial["order_counts"]["pending_entry"], 1)

                changed = report()
                changed["results"]["1"]["signals"][0]["ticker"] = "BBB"
                self.assertEqual(record_decisions(connection, changed, now=SIGNAL_TIME), 0)
                self.assertEqual(reconcile_orders(
                    connection, bars(include_next=True), now=NEXT_EOD, universe_size=2,
                ), 2)
                settled = read_summary(connection)
                self.assertEqual(settled["orders"][0]["ticker"], "AAA")
                self.assertEqual(settled["orders"][0]["status"], "closed")
                self.assertEqual(settled["orders"][0]["entry_open"], 110.0)
                self.assertEqual(settled["orders"][0]["exit_close"], 120.0)
                self.assertGreater(settled["closed_pnl_idr"], 0)
                self.assertEqual(reconcile_orders(
                    connection, bars(include_next=True), now=NEXT_EOD, universe_size=2,
                ), 0)
            self.assertEqual(load_summary(path)["recorded_runs"], 2)

    def test_stale_or_partial_report_is_not_recorded(self):
        with closing(sqlite3.connect(":memory:")) as connection:
            stale = report()
            stale["results"]["1"]["actionable"] = False
            stale["results"]["5"]["universe_coverage_pct"] = 80.0
            self.assertEqual(record_decisions(connection, stale, now=SIGNAL_TIME), 0)
            self.assertEqual(record_decisions(
                connection, report(),
                now=datetime(2026, 10, 20, 9, tzinfo=JAKARTA),
            ), 0)
            self.assertEqual(read_summary(connection)["recorded_runs"], 0)

    def test_preexisting_entry_bar_cannot_be_used_as_forward_fill(self):
        with closing(sqlite3.connect(":memory:")) as connection:
            record_decisions(connection, report(), now=SIGNAL_TIME)
            reconcile_orders(
                connection, bars(include_next=True,
                                 entry_seen="2026-10-19T18:00:00+07:00"),
                now=NEXT_EOD, universe_size=2,
            )
            order = read_summary(connection)["orders"][0]
            self.assertEqual(order["status"], "unverified_entry")
            self.assertIsNone(order["net_return_pct"])


if __name__ == "__main__":
    unittest.main()
