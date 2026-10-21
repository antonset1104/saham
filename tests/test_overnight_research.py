import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from intraday_history_store import insert_intraday_bars, read_intraday_bars
from market_history_store import connect_store
from overnight_research import (
    FEATURES, build_overnight_panel, fit_overnight_model, overnight_net_return,
    research_overnight,
)


JAKARTA = ZoneInfo("Asia/Jakarta")


def sample_intraday() -> pd.DataFrame:
    rows = []
    for date, close in (("2026-10-14", 103.0), ("2026-10-15", 106.0)):
        for clock in pd.date_range(f"{date} 09:00", periods=35, freq="5min"):
            rows.append((clock, 100.0, 101.0, 99.0, 100.0, 400_000))
        for hour, opening, closing in (("14:00", 102.0, 102.0),
                                       ("14:30", close, close), ("15:15", close + 1, close + 1)):
            rows.append((pd.Timestamp(f"{date} {hour}"), opening, opening + 1, opening - 1,
                         closing, 400_000))
    data = pd.DataFrame(rows, columns=["bar_time", "open", "high", "low", "close", "volume"])
    data["bar_time"] = data["bar_time"].dt.tz_localize(JAKARTA)
    data["ticker"] = "BBCA"
    data["first_seen_at"] = "2026-10-18T18:00:00+07:00"
    return data


class OvernightResearchTest(unittest.TestCase):
    def test_label_uses_future_execution_bars_and_costs(self):
        data = sample_intraday()
        panel = build_overnight_panel(data)
        first = panel.iloc[0]
        self.assertEqual(first["entry_open"], 104.0)
        self.assertEqual(first["exit_open"], 100.0)
        self.assertAlmostEqual(first["net_return"], overnight_net_return(104.0, 100.0))
        self.assertFalse(first["observed_before_signal"])

        amended = data.copy()
        amended.loc[amended["bar_time"].dt.strftime("%H:%M") == "15:15", "close"] = 500.0
        amended.loc[amended["bar_time"].dt.strftime("%H:%M") == "15:15", "high"] = 501.0
        after = build_overnight_panel(amended)
        for name in ("day_return", "recent_return", "range_pct", "close_position", "log_turnover"):
            self.assertAlmostEqual(first[name], after.iloc[0][name])

    def test_missing_exit_is_unlabeled(self):
        data = sample_intraday()
        data = data[~((data["bar_time"].dt.date.astype(str) == "2026-10-15")
                      & (data["bar_time"].dt.strftime("%H:%M") == "09:05"))]
        panel = build_overnight_panel(data)
        self.assertTrue(np.isnan(panel.iloc[0]["net_return"]))

    def test_model_cannot_learn_labels_after_signal_date(self):
        rng = np.random.default_rng(17)
        dates = pd.bdate_range("2026-01-02", periods=28)
        rows = []
        for index, date in enumerate(dates):
            for ticker in range(6):
                features = rng.normal(size=len(FEATURES))
                rows.append({
                    "trade_date": date, "exit_date": dates[min(index + 1, len(dates) - 1)],
                    "ticker": f"S{ticker}", "net_return": float(features[0] * 0.01),
                    "positive": int(features[0] > 0),
                    **dict(zip(FEATURES, features)),
                })
        panel = pd.DataFrame(rows)
        cutoff = dates[24]
        original, _ = fit_overnight_model(panel, cutoff)
        target = panel.loc[panel["trade_date"] == cutoff, FEATURES].to_numpy(dtype=float)
        revised = panel.copy()
        revised.loc[revised["exit_date"] >= cutoff, "positive"] = 1 - revised.loc[
            revised["exit_date"] >= cutoff, "positive"
        ]
        after, _ = fit_overnight_model(revised, cutoff)
        np.testing.assert_allclose(original.predict_proba(target), after.predict_proba(target))

    def test_backfill_only_cannot_approve_overnight_signal(self):
        rng = np.random.default_rng(19)
        dates = pd.bdate_range("2026-01-02", periods=50)
        rows = []
        for index, date in enumerate(dates):
            for ticker in range(6):
                features = rng.normal(size=len(FEATURES))
                outcome = float(features[0] * 0.01 - 0.006)
                rows.append({
                    "trade_date": date,
                    "exit_date": dates[index + 1] if index + 1 < len(dates) else pd.NaT,
                    "ticker": f"S{ticker}", "signal_close": 1_000.0,
                    "entry_open": 1_000.0 if index + 1 < len(dates) else np.nan,
                    "exit_open": 1_000.0 * (1 + outcome) if index + 1 < len(dates) else np.nan,
                    "net_return": outcome if index + 1 < len(dates) else np.nan,
                    "positive": int(outcome > 0), "observed_before_signal": False,
                    **dict(zip(FEATURES, features)),
                })
        with patch("overnight_research.build_overnight_panel", return_value=pd.DataFrame(rows)):
            result = research_overnight(pd.DataFrame(),
                                        now=datetime(2026, 3, 12, 14, 50, tzinfo=JAKARTA))
        self.assertEqual(result["status"], "collecting_point_in_time")
        self.assertFalse(result["approved"])
        self.assertEqual(result["signals"], [])
        self.assertIsNone(result["timely_validation"])

    def test_store_keeps_first_observation_and_complete_regular_bars(self):
        with tempfile.TemporaryDirectory() as directory:
            connection = connect_store(Path(directory) / "history.sqlite3")
            index = pd.DatetimeIndex(["2026-10-14 14:30", "2026-10-14 14:35",
                                      "2026-10-14 16:05"]).tz_localize(JAKARTA)
            raw = pd.DataFrame({"Open": [100.0] * 3, "High": [101.0] * 3,
                                "Low": [99.0] * 3, "Close": [100.0] * 3,
                                "Volume": [100] * 3}, index=index)
            now = datetime(2026, 10, 14, 14, 37, tzinfo=JAKARTA)
            self.assertEqual(insert_intraday_bars(connection, "BBCA", raw, now=now), 1)
            revised = raw.copy()
            revised.iloc[0, revised.columns.get_loc("Close")] = 101.0
            self.assertEqual(insert_intraday_bars(connection, "BBCA", revised,
                                                   now=datetime(2026, 10, 14, 18, tzinfo=JAKARTA)), 1)
            stored = read_intraday_bars(connection, ["BBCA"])
            self.assertEqual(len(stored), 2)
            self.assertEqual(stored.iloc[0]["close"], 100.0)
            connection.close()


if __name__ == "__main__":
    unittest.main()
