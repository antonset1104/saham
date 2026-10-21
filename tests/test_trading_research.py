import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from market_history_store import connect_store, download_and_store, insert_daily_bars, read_daily_bars
from trading_research import (
    FEATURES, _fit_model, build_research_panel, evaluate_nonoverlap,
    net_trade_return, research_signals, signal_is_actionable, split_rebalance_dates,
)


JAKARTA = ZoneInfo("Asia/Jakarta")


def sample_bars(days: int = 370, symbols: int = 6) -> pd.DataFrame:
    rng = np.random.default_rng(23)
    dates = pd.bdate_range("2024-01-02", periods=days)
    frames = []
    for number in range(symbols):
        daily = rng.normal(0.0004, 0.012, days)
        close = (1_000 + 100 * number) * np.exp(np.cumsum(daily))
        opening = close * (1 + rng.normal(0, 0.003, days))
        frames.append(pd.DataFrame({
            "ticker": f"T{number:02}", "trade_date": dates,
            "open": opening, "high": np.maximum(opening, close) * 1.01,
            "low": np.minimum(opening, close) * 0.99, "close": close,
            "volume": np.full(days, 3_000_000),
        }))
    return pd.concat(frames, ignore_index=True)


class MarketHistoryTest(unittest.TestCase):
    def test_store_preserves_first_observation_and_excludes_live_bar(self):
        with tempfile.TemporaryDirectory() as directory:
            connection = connect_store(Path(directory) / "market.sqlite3")
            dates = pd.to_datetime(["2026-10-12", "2026-10-13"])
            raw = pd.DataFrame({
                "Open": [100, 110], "High": [110, 120], "Low": [90, 100],
                "Close": [105, 115], "Volume": [1000, 1000],
            }, index=dates)
            morning = datetime(2026, 10, 13, 10, tzinfo=JAKARTA)
            self.assertEqual(insert_daily_bars(connection, "BBCA", raw, now=morning), 1)
            evening = datetime(2026, 10, 13, 18, tzinfo=JAKARTA)
            self.assertEqual(insert_daily_bars(connection, "BBCA", raw, now=evening), 1)
            revised = raw.copy()
            revised.loc[dates[0], "Close"] = 999
            self.assertEqual(insert_daily_bars(connection, "BBCA", revised, now=evening), 0)
            stored = read_daily_bars(connection, ["BBCA"])
            self.assertEqual(len(stored), 2)
            self.assertEqual(stored.iloc[0]["close"], 105)
            connection.close()

    def test_incremental_download_uses_recent_period(self):
        with tempfile.TemporaryDirectory() as directory:
            connection = connect_store(Path(directory) / "market.sqlite3")
            raw = pd.DataFrame({
                "Open": [100.0], "High": [110.0], "Low": [90.0],
                "Close": [105.0], "Volume": [1000],
            }, index=pd.to_datetime(["2026-10-13"]))
            now = datetime(2026, 10, 14, 18, tzinfo=JAKARTA)
            insert_daily_bars(connection, "BBCA", raw, now=now)
            yahoo_frame = pd.concat({"BBCA.JK": raw}, axis=1)
            with patch("yfinance.download", return_value=yahoo_frame) as mocked:
                added = download_and_store(connection, ["BBCA"], now=now)
            self.assertEqual(added["BBCA"], 0)
            self.assertEqual(mocked.call_args.kwargs["period"], "1mo")
            connection.close()


class TradingResearchTest(unittest.TestCase):
    def test_costs_and_next_open_label(self):
        bars = sample_bars()
        panel = build_research_panel(bars, 5)
        first = panel.iloc[0]
        ticker = bars[bars["ticker"] == first["ticker"]].set_index("trade_date")
        date_position = ticker.index.get_loc(first["trade_date"])
        self.assertAlmostEqual(first["entry_open"], ticker.iloc[date_position + 1]["open"])
        self.assertAlmostEqual(first["exit_close"], ticker.iloc[date_position + 5]["close"])
        manual = first["exit_close"] * (1 - 0.0025 - 0.001) / (first["entry_open"] * (1 + 0.0015 + 0.001)) - 1
        self.assertAlmostEqual(first["net_return"], manual)
        self.assertLess(float(net_trade_return(pd.Series([100.0]), pd.Series([100.0])).iloc[0]), 0)

    def test_features_and_training_cannot_see_future(self):
        bars = sample_bars()
        panel = build_research_panel(bars, 1)
        cutoff = pd.Timestamp("2024-12-31")
        before, _ = _fit_model(panel, cutoff)
        target = panel.loc[panel["trade_date"] == cutoff, FEATURES].head(3).to_numpy()
        prior_scores = before.predict_proba(target)
        changed = panel.copy()
        changed.loc[changed["exit_date"] > cutoff, "positive"] = 1 - changed.loc[
            changed["exit_date"] > cutoff, "positive"
        ]
        after, _ = _fit_model(changed, cutoff)
        np.testing.assert_allclose(prior_scores, after.predict_proba(target))

    def test_missing_exit_is_penalized_in_backtest(self):
        dates = pd.to_datetime(["2025-01-02", "2025-01-03"])
        scored = pd.DataFrame({
            "trade_date": dates, "ticker": ["AAA", "AAA"],
            "probability": [0.9, 0.9], "prior_probability": [0.5, 0.5],
            "momentum_5": [0.1, 0.1], "entry_open": [100.0, 100.0],
            "net_return": [0.1, np.nan], "positive": [1, 0],
        })
        result = evaluate_nonoverlap(scored, 1)
        self.assertEqual(result.trade_cohorts, 2)
        self.assertEqual(result.total_return_pct, -100.0)

    def test_matched_benchmark_uses_same_trade_dates_and_position_count(self):
        dates = pd.to_datetime(["2025-01-02", "2025-01-03"])
        scored = pd.DataFrame({
            "trade_date": [dates[0], dates[0], dates[1], dates[1]],
            "ticker": ["AAA", "BBB", "AAA", "BBB"],
            "probability": [0.9, 0.1, 0.1, 0.1],
            "prior_probability": [0.5] * 4,
            "momentum_5": [0.1, 0.2, 0.1, 0.2],
            "entry_open": [100.0] * 4,
            "net_return": [0.1, 0.02, 0.0, -0.5],
            "positive": [1, 1, 0, 0],
        })
        result = evaluate_nonoverlap(scored, 1, top_k=1)
        self.assertEqual(result.trade_cohorts, 1)
        self.assertEqual(result.total_return_pct, 10.0)
        self.assertEqual(result.matched_benchmark_return_pct, 2.0)
        self.assertEqual(result.benchmark_return_pct, -49.0)

    def test_research_returns_gated_signal_schema(self):
        result = research_signals(sample_bars(), 1)
        self.assertIn(result["status"], ("ready", "no_edge"))
        self.assertEqual(result["symbols_with_latest_bar"], 6)
        self.assertEqual(result["holdout"]["tested_cohorts"] > 0, True)
        if not result["approved"]:
            self.assertEqual(result["signals"], [])

    def test_signal_expires_at_next_weekday_open(self):
        self.assertTrue(signal_is_actionable(
            "2026-10-09", datetime(2026, 10, 12, 8, 59, tzinfo=JAKARTA)
        ))
        self.assertFalse(signal_is_actionable(
            "2026-10-09", datetime(2026, 10, 12, 9, 0, tzinfo=JAKARTA)
        ))
        self.assertFalse(signal_is_actionable(
            "2026-10-13", datetime(2026, 10, 13, 10, 0, tzinfo=JAKARTA)
        ))
        self.assertTrue(signal_is_actionable(
            "2026-10-13", datetime(2026, 10, 13, 18, 0, tzinfo=JAKARTA)
        ))

    def test_weekly_rebalances_keep_same_phase_across_holdout(self):
        dates = pd.bdate_range("2026-01-05", periods=21)
        scored = pd.DataFrame({"trade_date": dates})
        validation, holdout = split_rebalance_dates(scored, 5, dates[11])
        self.assertEqual(list(validation), [dates[0], dates[5]])
        self.assertEqual(list(holdout), [dates[15], dates[20]])
        self.assertLess(dates[10], dates[11])


if __name__ == "__main__":
    unittest.main()
