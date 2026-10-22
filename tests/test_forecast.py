import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from mesin_forecast import (
    _extend_with_verified_eod, _time_windows, _validation_folds,
    build_forecast_features, forecast_from_history,
    run_stock_forecast,
)


def sample_history(length=340):
    rng = np.random.default_rng(17)
    dates = pd.bdate_range("2024-01-02", periods=length)
    close = 1000 * np.exp(np.cumsum(rng.normal(0.0002, 0.015, length)))
    return pd.DataFrame({
        "Close": close,
        "High": close * 1.015,
        "Low": close * 0.985,
        "Volume": rng.integers(1_000_000, 3_000_000, length),
    }, index=dates)


def predictable_history(length=400):
    rng = np.random.default_rng(9)
    returns = np.zeros(length)
    for index in range(1, length):
        returns[index] = 0.8 * returns[index - 1] + rng.normal(0, 0.004)
    close = 1000 * np.cumprod(1 + returns)
    dates = pd.bdate_range("2024-01-02", periods=length)
    return pd.DataFrame({
        "Close": close, "High": close * 1.01, "Low": close * 0.99,
        "Volume": np.full(length, 1_000_000),
    }, index=dates)


class ForecastTest(unittest.TestCase):
    def test_verified_eod_fills_lagging_adjusted_feed_on_same_scale(self):
        stored = sample_history()
        adjusted = stored.iloc[:-1].copy()
        adjusted[["Close", "High", "Low"]] *= 0.9
        combined, supplemented = _extend_with_verified_eod(adjusted, stored)
        self.assertTrue(supplemented)
        self.assertEqual(len(combined), len(stored))
        self.assertAlmostEqual(combined["Close"].iloc[-1], stored["Close"].iloc[-1] * 0.9)

    def test_verified_eod_rejects_inconsistent_scale_or_price_jump(self):
        stored = sample_history()
        adjusted = stored.iloc[:-1].copy()
        adjusted[["Close", "High", "Low"]] *= 0.9
        adjusted.iloc[-1, adjusted.columns.get_loc("Close")] *= 1.1
        result, supplemented = _extend_with_verified_eod(adjusted, stored)
        self.assertFalse(supplemented)
        pd.testing.assert_frame_equal(result, adjusted)

        adjusted = stored.iloc[:-1].copy()
        stored.iloc[-1, stored.columns.get_loc("Close")] *= 2
        result, supplemented = _extend_with_verified_eod(adjusted, stored)
        self.assertFalse(supplemented)
        pd.testing.assert_frame_equal(result, adjusted)

    def test_features_do_not_read_future_bars(self):
        original = sample_history()
        changed = original.copy()
        changed.iloc[-1, changed.columns.get_loc("Close")] *= 4
        before = build_forecast_features(original).iloc[-2]
        after = build_forecast_features(changed).iloc[-2]
        pd.testing.assert_series_equal(before, after)

    def test_split_purges_labels_crossing_boundaries(self):
        horizon = 10
        windows = _time_windows(300, horizon)
        self.assertLessEqual(windows.train.stop + horizon, windows.validation.start)
        self.assertLessEqual(windows.validation.stop + horizon, windows.gate.start)
        self.assertLessEqual(windows.gate_train.stop + horizon, windows.gate.start)
        self.assertLessEqual(windows.gate.stop + horizon, windows.test.start)
        self.assertLessEqual(windows.test_train.stop + horizon, windows.test.start)
        folds = _validation_folds(windows.validation, horizon)
        self.assertEqual(len(folds), 2)
        for fold_train, fold_validation in folds:
            self.assertLessEqual(fold_train.stop + horizon, fold_validation.start)
        self.assertEqual(folds[0][1].start, windows.validation.start)
        self.assertEqual(folds[-1][1].stop, windows.validation.stop)

    def test_direct_horizon_matches_output_and_baseline(self):
        history = sample_history()
        next_day = history.index[-1] + pd.Timedelta(days=1)
        as_of = datetime(next_day.year, next_day.month, next_day.day,
                         tzinfo=ZoneInfo("Asia/Jakarta"))
        for horizon in (1, 5, 10):
            with self.subTest(horizon=horizon):
                result = forecast_from_history(history, "BBCA", horizon, as_of=as_of)
                self.assertEqual(result["status"], "success")
                self.assertEqual(result["test_samples"], 40)
                self.assertIn(result["model_name"], ("Harga tetap", "Ridge"))
                self.assertGreaterEqual(result["return_mae_pct"], 0)
                self.assertGreaterEqual(result["baseline_mae_pct"], 0)
                self.assertLess(result["estimated_net_return_pct"], result["expected_return_pct"])
                self.assertEqual(len(result["forecast_df"]), 1)
                self.assertLessEqual(result["forecast_df"]["yhat_lower"].iloc[0], result["predicted_price"] + 0.01)
                self.assertGreaterEqual(result["forecast_df"]["yhat_upper"].iloc[0], result["predicted_price"] - 0.01)

    def test_unfinished_daily_candle_is_excluded(self):
        history = sample_history()
        today = history.index[-1]
        history.iloc[-1, history.columns.get_loc("Close")] *= 3
        as_of = datetime(today.year, today.month, today.day, 10, 0,
                         tzinfo=ZoneInfo("Asia/Jakarta"))
        result = forecast_from_history(history, "BBCA", 1, as_of=as_of)
        self.assertEqual(result["data_asof"], history.index[-2].strftime("%Y-%m-%d"))
        self.assertAlmostEqual(result["current_price"], round(history["Close"].iloc[-2], 2))

    def test_old_data_is_rejected(self):
        history = sample_history()
        late = history.index[-1] + pd.Timedelta(days=20)
        as_of = datetime(late.year, late.month, late.day,
                         tzinfo=ZoneInfo("Asia/Jakarta"))
        with self.assertRaisesRegex(ValueError, "terlambat"):
            forecast_from_history(history, "BBCA", 5, as_of=as_of)

    def test_flat_prices_use_baseline_without_direction_metric(self):
        history = sample_history()
        history["Close"] = 1000.0
        history["High"] = 1010.0
        history["Low"] = 990.0
        next_day = history.index[-1] + pd.Timedelta(days=1)
        as_of = datetime(next_day.year, next_day.month, next_day.day,
                         tzinfo=ZoneInfo("Asia/Jakarta"))
        result = forecast_from_history(history, "BBCA", 5, as_of=as_of)
        self.assertEqual(result["model_name"], "Harga tetap")
        self.assertIsNone(result["direction_accuracy_pct"])
        self.assertEqual(result["expected_return_pct"], 0.0)

    def test_invalid_ticker_is_rejected_before_download(self):
        result = run_stock_forecast("BBCA; unsafe")
        self.assertEqual(result["status"], "error")
        self.assertIn("tidak valid", result["message"])

    def test_ridge_is_selected_when_pattern_is_predictable(self):
        history = predictable_history()
        next_day = history.index[-1] + pd.Timedelta(days=1)
        as_of = datetime(next_day.year, next_day.month, next_day.day,
                         tzinfo=ZoneInfo("Asia/Jakarta"))
        result = forecast_from_history(history, "TEST", 1, as_of=as_of)
        self.assertEqual(result["model_name"], "Ridge")
        self.assertTrue(result["beats_baseline"])


if __name__ == "__main__":
    unittest.main()
