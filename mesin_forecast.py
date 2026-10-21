"""Prediksi harga penutupan EOD untuk horizon trading harian dan mingguan.

Setiap fitur hanya memakai bar yang sudah tersedia pada tanggal prediksi. Target
dibentuk langsung pada horizon yang diminta, tanpa membuat OHLCV sintetis.
"""

try:
    import truststore
    truststore.inject_into_ssl()
except Exception:
    pass

from market_tls import configure_yahoo_tls

configure_yahoo_tls()

from datetime import datetime, time
import re
from typing import Any, NamedTuple
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler


MIN_TRAIN = 90
FORECAST_VERSION = "direct-horizon-v5"
VALIDATION_SIZE = 80
VALIDATION_FOLD_SIZE = 40
GATE_SIZE = 40
TEST_SIZE = 40
BUY_FEE = 0.0015
SELL_FEE = 0.0025
FEATURE_COLUMNS = [
    "lag_1", "lag_2", "lag_3", "lag_5", "lag_10",
    "ma_5", "ma_10", "ma_20", "std_5", "std_10", "std_20",
    "ret_5", "ret_10", "ret_20", "hl_pct", "close_position",
    "vol_ratio", "vol_change_5",
]


def build_forecast_features(df: pd.DataFrame, lookback: int = 10) -> pd.DataFrame:
    """Fitur skala relatif; nilai bar t tidak mengandung informasi setelah t."""
    data = df[["Close", "High", "Low", "Volume"]].astype(float).copy()
    close = data["Close"]
    returns = close.pct_change(fill_method=None)
    for lag in range(1, lookback + 1):
        data[f"lag_{lag}"] = close.pct_change(lag, fill_method=None)
    for window in (5, 10, 20):
        average = close.rolling(window).mean()
        data[f"ma_{window}"] = close / average.replace(0, np.nan) - 1
        data[f"std_{window}"] = returns.rolling(window).std()
        data[f"ret_{window}"] = close.pct_change(window, fill_method=None)
    data["hl_pct"] = (data["High"] - data["Low"]) / close.replace(0, np.nan)
    day_range = (data["High"] - data["Low"]).replace(0, np.nan)
    data["close_position"] = ((close - data["Low"]) / day_range).fillna(0.5)
    volume_average = data["Volume"].rolling(10).mean()
    data["vol_ratio"] = (data["Volume"] / volume_average.replace(0, np.nan)).fillna(0)
    data["vol_change_5"] = (data["Volume"] / data["Volume"].rolling(5).mean().replace(0, np.nan)).fillna(0)
    # Nama lama dipertahankan agar pemanggil fitur yang sudah ada tetap bekerja.
    data["trend_5"] = data["ret_5"]
    return data.replace([np.inf, -np.inf], np.nan)


def _clean_history(raw_df: pd.DataFrame, as_of: datetime | None = None) -> pd.DataFrame:
    data = raw_df.copy()
    if isinstance(data.columns, pd.MultiIndex):
        data.columns = data.columns.get_level_values(0)
    required = ["Close", "High", "Low", "Volume"]
    if any(column not in data for column in required):
        raise ValueError("Data OHLCV tidak lengkap.")
    data = data[required].apply(pd.to_numeric, errors="coerce")
    data.index = pd.to_datetime(data.index).tz_localize(None)
    data = data.sort_index()
    data = data[~data.index.duplicated(keep="last")].replace([np.inf, -np.inf], np.nan).dropna()
    data = data[(data["Close"] > 0) & (data["High"] > 0) & (data["Low"] > 0) & (data["Volume"] >= 0)]
    now = as_of or datetime.now(ZoneInfo("Asia/Jakarta"))
    if now.tzinfo is not None:
        now = now.astimezone(ZoneInfo("Asia/Jakarta"))
    # Yahoo dapat memberikan candle harian yang masih berubah saat bursa buka.
    if len(data) and data.index[-1].date() == now.date() and now.time() < time(17, 0):
        data = data.iloc[:-1]
    if len(data) and (now.date() - data.index[-1].date()).days > 14:
        raise ValueError("Harga terakhir lebih dari 14 hari lalu; sumber data mungkin terlambat.")
    return data


class ForecastWindows(NamedTuple):
    train: slice
    validation: slice
    gate_train: slice
    gate: slice
    test_train: slice
    test: slice


def _time_windows(length: int, horizon: int) -> ForecastWindows:
    """Pisahkan origin waktu dan purge h bar agar label tak melewati batas split."""
    test_start = length - TEST_SIZE
    gate_end = test_start - horizon
    gate_start = gate_end - GATE_SIZE
    validation_end = gate_start - horizon
    validation_start = validation_end - VALIDATION_SIZE
    train_end = validation_start - horizon
    if train_end < MIN_TRAIN:
        raise ValueError("Butuh histori lebih panjang untuk validasi waktu pada horizon ini.")
    return ForecastWindows(
        train=slice(0, train_end),
        validation=slice(validation_start, validation_end),
        gate_train=slice(0, gate_start - horizon),
        gate=slice(gate_start, gate_end),
        test_train=slice(0, test_start - horizon),
        test=slice(test_start, length),
    )


def _validation_folds(validation_window: slice, horizon: int) -> list[tuple[slice, slice]]:
    """Setiap blok validasi dilatih ulang hanya dari label yang sudah tersedia."""
    return [
        (slice(0, start - horizon), slice(start, start + VALIDATION_FOLD_SIZE))
        for start in range(validation_window.start, validation_window.stop, VALIDATION_FOLD_SIZE)
    ]


def _new_model(name: str) -> Any:
    if name == "Ridge":
        return make_pipeline(StandardScaler(), Ridge(alpha=20.0))
    raise ValueError(f"Model tidak dikenal: {name}")


def _mae(actual: np.ndarray, predicted: np.ndarray) -> float:
    return float(np.mean(np.abs(actual - predicted)))


def _importance(model: Any, name: str) -> dict[str, float]:
    if name == "Ridge":
        weights = np.abs(model.named_steps["ridge"].coef_)
    else:
        return {}
    total = float(np.sum(weights))
    if total <= 0:
        return {}
    ranked = sorted(zip(FEATURE_COLUMNS, weights), key=lambda item: item[1], reverse=True)
    return {feature: round(float(weight / total * 100), 1) for feature, weight in ranked[:6]}


def forecast_from_history(raw_df: pd.DataFrame, ticker: str, periods: int = 5,
                          as_of: datetime | None = None) -> dict[str, Any]:
    """Latih, pilih model di validasi, lalu ukur sekali di holdout terbaru."""
    horizon = int(periods)
    if horizon not in (1, 5, 10):
        raise ValueError("Horizon harus 1, 5, atau 10 hari bursa.")
    history = _clean_history(raw_df, as_of=as_of)
    if len(history) < 330:
        raise ValueError("Data historis kurang dari 330 hari bursa untuk evaluasi ini.")
    if (history["Volume"].tail(20) > 0).sum() < 10:
        raise ValueError("Volume perdagangan terlalu jarang dalam 20 hari terakhir.")

    features = build_forecast_features(history)
    target = history["Close"].shift(-horizon) / history["Close"] - 1
    valid_features = features[FEATURE_COLUMNS].replace([np.inf, -np.inf], np.nan)
    labeled = valid_features.assign(target=target).dropna()
    windows = _time_windows(len(labeled), horizon)
    x = labeled[FEATURE_COLUMNS].to_numpy(dtype=float)
    y = labeled["target"].to_numpy(dtype=float)

    validation_actual = y[windows.validation]
    baseline_validation_mae = _mae(validation_actual, np.zeros_like(validation_actual))
    validation_scores = {"Harga tetap": baseline_validation_mae}
    fold_scores: dict[str, list[tuple[float, float]]] = {}
    for name in ("Ridge",):
        predictions = []
        fold_scores[name] = []
        for fold_train, fold_validation in _validation_folds(windows.validation, horizon):
            candidate = _new_model(name)
            candidate.fit(x[fold_train], y[fold_train])
            actual = y[fold_validation]
            predicted = candidate.predict(x[fold_validation])
            predictions.append(predicted)
            fold_scores[name].append((_mae(actual, predicted), _mae(actual, np.zeros_like(actual))))
        validation_scores[name] = _mae(validation_actual, np.concatenate(predictions))
    selected = min(validation_scores, key=validation_scores.get)
    if selected != "Harga tetap":
        material_gain = validation_scores[selected] < baseline_validation_mae * 0.95
        consistent_gain = all(model_mae < baseline_mae for model_mae, baseline_mae in fold_scores[selected])
        if not (material_gain and consistent_gain):
            selected = "Harga tetap"
    if selected != "Harga tetap":
        gate_model = _new_model(selected)
        gate_model.fit(x[windows.gate_train], y[windows.gate_train])
        gate_actual = y[windows.gate]
        gate_mae = _mae(gate_actual, gate_model.predict(x[windows.gate]))
        gate_baseline_mae = _mae(gate_actual, np.zeros_like(gate_actual))
        if gate_mae >= gate_baseline_mae * 0.98:
            selected = "Harga tetap"

    test_actual = y[windows.test]
    baseline_mae_pct = _mae(test_actual, np.zeros_like(test_actual)) * 100
    if selected == "Harga tetap":
        test_predictions = np.zeros_like(test_actual)
        future_return = 0.0
        importance = {}
    else:
        evaluation_model = _new_model(selected)
        evaluation_model.fit(x[windows.test_train], y[windows.test_train])
        test_predictions = evaluation_model.predict(x[windows.test])
        final_model = _new_model(selected)
        final_model.fit(x, y)
        importance = _importance(final_model, selected)
        latest_features = valid_features.iloc[-1]
        if latest_features.isna().any():
            raise ValueError("Fitur pada candle terbaru tidak lengkap.")
        future_return = max(-1.0, float(final_model.predict(latest_features.to_numpy(dtype=float).reshape(1, -1))[0]))
    test_mae_pct = _mae(test_actual, test_predictions) * 100
    improvement_pct = (baseline_mae_pct - test_mae_pct) / baseline_mae_pct * 100 if baseline_mae_pct > 0 else 0.0
    origin_prices = history.loc[labeled.index, "Close"].to_numpy(dtype=float)[windows.test]
    test_mae_price = float(np.mean(np.abs(test_actual - test_predictions) * origin_prices))
    target_mape = float(np.mean(np.abs(test_actual - test_predictions) / (1 + test_actual)) * 100)
    direction_accuracy = (float(np.mean(np.sign(test_actual) == np.sign(test_predictions)) * 100)
                          if selected != "Harga tetap" else None)
    residual_pct = np.abs(test_actual - test_predictions) * 100
    historical_error_pct = float(np.quantile(residual_pct, 0.90))

    current_price = float(history["Close"].iloc[-1])
    predicted_price = max(0.0, current_price * (1 + future_return))
    estimated_net_return_pct = ((1 + future_return) * (1 - SELL_FEE) / (1 + BUY_FEE) - 1) * 100
    lower = max(0.0, current_price * (1 + future_return - historical_error_pct / 100))
    upper = max(0.0, current_price * (1 + future_return + historical_error_pct / 100))
    future_date = history.index[-1] + pd.offsets.BDay(horizon)
    forecast_df = pd.DataFrame({"ds": [future_date], "yhat": [predicted_price],
                                "yhat_lower": [lower], "yhat_upper": [upper]})
    history_tail = history["Close"].tail(60)
    history_df = pd.DataFrame({"ds": history_tail.index, "y": history_tail.to_numpy()})
    return {
        "status": "success", "ticker": ticker.upper(), "periods": horizon,
        "data_asof": history.index[-1].strftime("%Y-%m-%d"),
        "current_price": round(current_price, 2),
        "predicted_price": round(predicted_price, 2),
        "expected_return_pct": round(future_return * 100, 2),
        "estimated_net_return_pct": round(estimated_net_return_pct, 2),
        "mae": round(test_mae_price, 2),
        "mape": round(target_mape, 2),
        "return_mae_pct": round(test_mae_pct, 2),
        "baseline_mae_pct": round(baseline_mae_pct, 2),
        "improvement_vs_baseline_pct": round(improvement_pct, 1),
        "direction_accuracy_pct": round(direction_accuracy, 1) if direction_accuracy is not None else None,
        "historical_error_pct": round(historical_error_pct, 2),
        "test_samples": len(test_actual), "model_name": selected,
        "test_from": labeled.index[windows.test.start].strftime("%Y-%m-%d"),
        "test_to": labeled.index[-1].strftime("%Y-%m-%d"),
        "beats_baseline": bool(improvement_pct >= 2.0),
        "history_df": history_df, "forecast_df": forecast_df,
        "feature_importance": importance,
    }


def run_stock_forecast(ticker: str, periods: int = 5, history_period: str = "2y") -> dict[str, Any]:
    """Unduh OHLCV tersesuaikan dan jalankan prediksi setelah candle EOD tersedia."""
    if not isinstance(ticker, str):
        return {"status": "error", "message": "Ticker harus berupa teks."}
    symbol = ticker.strip().upper()
    if not re.fullmatch(r"[A-Z0-9^=._-]{1,20}", symbol):
        return {"status": "error", "message": "Format ticker tidak valid."}
    yf_symbol = f"{symbol}.JK" if symbol.isalpha() and len(symbol) <= 4 else symbol
    try:
        import yfinance as yf

        raw = yf.download(yf_symbol, period=history_period, interval="1d", progress=False,
                          auto_adjust=True, timeout=15)
        if raw is None or raw.empty:
            raise ValueError(f"Data historis {ticker} tidak ditemukan.")
        return forecast_from_history(raw, ticker, periods=periods)
    except Exception as error:
        return {"status": "error", "message": f"Prediksi gagal: {error}"}
