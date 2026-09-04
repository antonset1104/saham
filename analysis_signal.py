import pandas as pd
import numpy as np

def calculate_signal_score(df: pd.DataFrame) -> dict:
    """
    Menghitung skor multi-faktor kuantitatif dan merangkum alasan teknikal.
    Input df: DataFrame OHLCV yang sudah memiliki kolom indikator dasar.
    Returns: dict berisi skor akhir (-5.0 s/d +5.0), kategori sinyal, dan narasi alasan.
    """
    if df.empty or len(df) < 20:
        return {"score": 0.0, "signal": "HOLD", "reasons": ["Data historis terbatas"]}

    # Ambil baris terakhir
    row = df.iloc[-1]
    close = float(row.get("Close", 0))
    rsi = float(row.get("RSI (14D)", row.get("RSI", 50)) or 50)
    ma20 = float(row.get("MA20", 0) or 0)
    ma50 = float(row.get("MA50", 0) or 0)
    vol_ratio = float(row.get("Rasio Vol H-1", row.get("Volume_ratio", 1.0)) or 1.0)

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
    posisi_vwap = str(row.get("Posisi VWAP", ""))
    if "Di Atas VWAP" in posisi_vwap:
        score += 1.0
        reasons.append("Harga di atas VWAP Intraday")
    elif "Di Bawah VWAP" in posisi_vwap:
        score -= 1.0
        reasons.append("Harga di bawah VWAP Intraday")

    # 4. Status Bollinger Bands Squeeze (Bobot 1.0)
    status_bb = str(row.get("Status BB", ""))
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
