try:
    import truststore
    truststore.inject_into_ssl()
except Exception:
    pass

import yfinance as yf
import pandas as pd
import numpy as np
import warnings
from datetime import datetime, timedelta

warnings.filterwarnings("ignore")

def build_forecast_features(df: pd.DataFrame, lookback: int = 10) -> pd.DataFrame:
    """Membentuk feature engineering dari data OHLCV historis."""
    data = df[["Close", "High", "Low", "Volume"]].copy()
    close = data["Close"]

    # 1. Lags harga penutupan
    for lag in range(1, lookback + 1):
        data[f"lag_{lag}"] = close.shift(lag)

    # 2. Moving Average & Volatilitas
    for w in [5, 10, 20]:
        data[f"ma_{w}"] = close.rolling(w).mean()
        data[f"std_{w}"] = close.rolling(w).std()
        data[f"ret_{w}"] = close.pct_change(w)
        data[f"ma_ratio_{w}"] = close / data[f"ma_{w}"].replace(0, np.nan)

    # 3. High-Low Spread & Trend
    data["hl_pct"] = (data["High"] - data["Low"]) / close.replace(0, np.nan)
    data["trend_5"] = (close - close.shift(5)) / close.shift(5).replace(0, np.nan)

    # 4. Volume Features
    vol_ma10 = data["Volume"].rolling(10).mean()
    data["vol_ratio"] = data["Volume"] / vol_ma10.replace(0, np.nan)

    return data

def run_stock_forecast(ticker: str, periods: int = 30, history_period: str = "1y") -> dict:
    """
    Menjalankan estimasi harga saham masa depan menggunakan XGBoost Regressor.
    Returns dict:
      - status: 'success' atau 'error'
      - ticker: kode saham
      - current_price: harga terakhir
      - predicted_price: estimasi harga di akhir horizon
      - expected_return_pct: estimasi persentase kenaikan/penurunan
      - mape: estimasi error akurasi (%)
      - history_df: DataFrame data historis aktual (ds, y)
      - forecast_df: DataFrame data proyeksi masa depan (ds, yhat, yhat_lower, yhat_upper)
      - feature_importance: dict skor pengaruh fitur
    """
    symbol = ticker.strip().upper()
    if not symbol.endswith(".JK") and len(symbol) <= 4 and symbol.isalpha():
        # Asumsikan ticker IHSG jika 4 huruf tanpa ekstensi
        yf_symbol = f"{symbol}.JK"
    else:
        yf_symbol = symbol

    try:
        raw_df = yf.download(yf_symbol, period=history_period, progress=False, interval="1d")
        if raw_df.empty or len(raw_df) < 50:
            return {"status": "error", "message": f"Data historis {ticker} terlalu sedikit atau tidak ditemukan."}

        # Flatten multi-index jika ada
        if isinstance(raw_df.columns, pd.MultiIndex):
            raw_df.columns = [col[0] for col in raw_df.columns]

        data = build_forecast_features(raw_df)
        data["target"] = data["Close"].shift(-1)
        data = data.dropna()

        if len(data) < 40:
            return {"status": "error", "message": "Data fitur valid terlalu sedikit setelah pembersihan."}

        feature_cols = [c for c in data.columns if c not in ["target", "Close", "High", "Low", "Volume"]]
        X = data[feature_cols].values
        y = data["target"].values

        # Split 80% train, 20% test (maks 20 hari test)
        test_size = min(25, max(10, int(len(X) * 0.15)))
        split_idx = len(X) - test_size
        X_train, X_test = X[:split_idx], X[split_idx:]
        y_train, y_test = y[:split_idx], y[split_idx:]

        # Menggunakan XGBoost jika runtime libomp tersedia, jika tidak gunakan GradientBoostingRegressor bawaan sklearn
        try:
            from xgboost import XGBRegressor
            model = XGBRegressor(
                n_estimators=150,
                learning_rate=0.05,
                max_depth=4,
                subsample=0.85,
                colsample_bytree=0.85,
                random_state=42,
                verbosity=0
            )
        except Exception as e:
            from sklearn.ensemble import GradientBoostingRegressor
            model = GradientBoostingRegressor(
                n_estimators=120,
                learning_rate=0.05,
                max_depth=4,
                random_state=42
            )

        model.fit(X_train, y_train)

        # Evaluasi akurasi pada test set
        y_pred_test = model.predict(X_test)
        mae = float(np.mean(np.abs(y_test - y_pred_test)))
        mape = float(np.mean(np.abs((y_test - y_pred_test) / np.where(y_test == 0, 1, y_test))) * 100)

        # Multi-step iterative forward forecast
        current_df = raw_df[["Close", "High", "Low", "Volume"]].copy()
        forecast_prices = []
        last_close = float(raw_df["Close"].iloc[-1])

        for step in range(periods):
            feat = build_forecast_features(current_df)
            feat = feat.dropna()
            if feat.empty:
                break
            latest_row = feat[feature_cols].iloc[-1:].values
            next_pred = float(model.predict(latest_row)[0])
            # Batasan realistis volatilitas harian (maks ±10% per langkah)
            prev_price = forecast_prices[-1] if forecast_prices else last_close
            next_pred = max(prev_price * 0.85, min(prev_price * 1.15, next_pred))
            forecast_prices.append(next_pred)

            next_date = current_df.index[-1] + timedelta(days=1)
            new_record = pd.DataFrame({
                "Close": [next_pred],
                "High": [next_pred * 1.01],
                "Low": [next_pred * 0.99],
                "Volume": [float(current_df["Volume"].tail(10).mean())]
            }, index=[next_date])
            current_df = pd.concat([current_df, new_record])

        # Kalender hari kerja ke depan
        last_date = raw_df.index[-1]
        future_bdays = pd.bdate_range(start=last_date + timedelta(days=1), periods=len(forecast_prices))

        # Rentang ketidakpastian (confidence band) meningkat seiring horizon
        daily_std = float(raw_df["Close"].pct_change().std()) or 0.02
        bands_lower = []
        bands_upper = []
        for i, price in enumerate(forecast_prices, 1):
            uncertainty = daily_std * np.sqrt(i) * 1.25 * price
            bands_lower.append(max(0, price - uncertainty))
            bands_upper.append(price + uncertainty)

        forecast_df = pd.DataFrame({
            "ds": future_bdays,
            "yhat": forecast_prices,
            "yhat_lower": bands_lower,
            "yhat_upper": bands_upper
        })

        # Data historis untuk plotting
        history_tail = raw_df.tail(60).copy()
        history_df = pd.DataFrame({
            "ds": history_tail.index,
            "y": history_tail["Close"].values
        })

        # Feature Importance
        importances = getattr(model, "feature_importances_", None)
        feat_dict = {}
        if importances is not None and len(importances) == len(feature_cols):
            pairs = sorted(zip(feature_cols, importances), key=lambda x: x[1], reverse=True)
            feat_dict = {k: round(float(v) * 100, 2) for k, v in pairs[:6]}

        final_pred = forecast_prices[-1] if forecast_prices else last_close
        ret_pct = ((final_pred - last_close) / last_close) * 100

        return {
            "status": "success",
            "ticker": ticker.upper(),
            "periods": periods,
            "current_price": round(last_close, 2),
            "predicted_price": round(final_pred, 2),
            "expected_return_pct": round(ret_pct, 2),
            "mae": round(mae, 2),
            "mape": round(mape, 2),
            "history_df": history_df,
            "forecast_df": forecast_df,
            "feature_importance": feat_dict
        }

    except Exception as e:
        return {"status": "error", "message": f"Terjadi kesalahan pemodelan: {str(e)}"}
