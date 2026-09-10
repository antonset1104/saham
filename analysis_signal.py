import pandas as pd
import numpy as np

def calculate_signal_score(df: pd.DataFrame, indikator: dict = None) -> dict:
    """
    Menghitung skor multi-faktor kuantitatif dan merangkum alasan teknikal.
    Input:
      - df: DataFrame OHLCV
      - indikator: (Opsional) Dict hasil kalkulasi hitung_semua_indikator
    Returns: dict berisi skor akhir (-5.0 s/d +5.0), kategori sinyal, dan narasi alasan.
    """
    if df.empty or len(df) < 20:
        return {"score": 0.0, "signal": "HOLD", "reasons": ["Data historis terbatas"]}

    if isinstance(df.columns, pd.MultiIndex):
        df = df.copy()
        df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]

    # Ambil baris terakhir
    row = df.iloc[-1]
    ind = indikator or {}

    close_val = row.get("Close", 0)
    close = float(close_val.iloc[0] if hasattr(close_val, "iloc") else close_val)
    rsi_val = ind.get("RSI (14D)", row.get("RSI (14D)", row.get("RSI", 50)))
    rsi = float(rsi_val.iloc[0] if hasattr(rsi_val, "iloc") else rsi_val) if rsi_val is not None else 50.0

    # MA20 & MA50: Ambil dari indikator, baris df, atau hitung langsung dari series Close
    ma20 = float(ind.get("Harga MA20", row.get("MA20", 0)) or 0)
    if ma20 == 0 and "Close" in df.columns and len(df) >= 20:
        ma20 = float(df["Close"].rolling(20).mean().iloc[-1])

    ma50 = float(ind.get("MA50", row.get("MA50", 0)) or 0)
    if ma50 == 0 and "Close" in df.columns and len(df) >= 50:
        ma50 = float(df["Close"].rolling(50).mean().iloc[-1])
    elif ma50 == 0:
        ma50 = ma20

    # Volume ratio: dari indikator atau hitung dari series Volume
    vol_ratio = float(row.get("Rasio Vol H-1", row.get("Volume_ratio", 0)) or 0)
    if vol_ratio == 0 and "Volume" in df.columns and len(df) >= 20:
        vol_ma20 = float(df["Volume"].rolling(20).mean().iloc[-1])
        vol_today = float(df["Volume"].iloc[-1])
        vol_ratio = (vol_today / vol_ma20) if vol_ma20 > 0 else 1.0
    elif vol_ratio == 0:
        vol_ratio = 1.0

    score = 0.0
    reasons = []

    # 1. MA Trend (Bobot 1.5)
    if ma20 > 0 and ma50 > 0:
        if ma20 > ma50:
            score += 1.5
            reasons.append("MA20 di atas MA50 (Uptrend)")
        else:
            score -= 1.5
            reasons.append("MA20 di bawah MA50 (Downtrend)")

    # 2. RSI Level (Bobot s/d 2.0)
    if rsi < 30:
        score += 2.0
        reasons.append(f"RSI Oversold Kuat ({rsi:.1f})")
    elif 30 <= rsi < 45:
        score += 0.5
        reasons.append(f"RSI Rebound Area Murah ({rsi:.1f})")
    elif 55 < rsi <= 70:
        score -= 0.5
        reasons.append(f"RSI Mendekati Jenuh Beli ({rsi:.1f})")
    elif rsi > 70:
        score -= 2.0
        reasons.append(f"RSI Overbought Pucuk ({rsi:.1f})")

    # 3. Posisi VWAP (Bobot 1.0)
    posisi_vwap = str(ind.get("Posisi VWAP", row.get("Posisi VWAP", "")))
    if "Di Atas VWAP" in posisi_vwap:
        score += 1.0
        reasons.append("Harga di atas VWAP Intraday")
    elif "Di Bawah VWAP" in posisi_vwap:
        score -= 1.0
        reasons.append("Harga di bawah VWAP Intraday")

    # 4. Status Bollinger Bands Squeeze (Bobot 1.0)
    status_bb = str(ind.get("Status BB", row.get("Status BB", "")))
    if "Squeeze" in status_bb:
        score += 1.0
        reasons.append("Volatilitas Bollinger Squeeze (Siap Meledak)")

    # 5. Amplifikasi Volume Lonjakan
    if vol_ratio >= 1.5:
        score *= 1.2
        reasons.append(f"Volume Lonjak {vol_ratio:.1f}x MA20")

    # Kategori Sinyal
    if score >= 3.0:
        kategori = "STRONG BUY"
    elif score >= 1.5:
        kategori = "BUY"
    elif score <= -3.0:
        kategori = "STRONG SELL"
    elif score <= -1.5:
        kategori = "SELL"
    else:
        kategori = "HOLD / NEUTRAL"

    return {
        "score": round(score, 2),
        "signal": kategori,
        "reasons": reasons,
        "reason_str": " | ".join(reasons) if reasons else "Kondisi pasar normal"
    }
