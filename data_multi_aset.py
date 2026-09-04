import os
import json
import yfinance as yf
import pandas as pd
from datetime import datetime

PORTFOLIO_FILE = "Database/portofolio_multi_aset.json"
TROY_OZ_TO_GRAM = 31.1034768

ASSET_CLASS_LABELS = {
    "idx": "🇮🇩 Saham IHSG",
    "gold": "🥇 Emas (Antam / World)",
    "crypto": "🪙 Cryptocurrency",
    "us_stock": "🇺🇸 Saham Amerika (US)",
}

def get_usd_idr_rate() -> float:
    """Mengambil kurs tukar USD ke IDR terkini via Yahoo Finance."""
    try:
        data = yf.download("IDR=X", period="5d", progress=False, interval="1d")
        if not data.empty:
            close_val = data["Close"].dropna().iloc[-1]
            return float(close_val.iloc[0] if hasattr(close_val, "iloc") else close_val)
    except Exception as e:
        print(f"⚠️ Gagal fetch USD/IDR: {e}")
    return 16350.0  # Estimasi nilai wajar fallback

def get_gold_price_idr(usd_idr: float = None) -> dict:
    """Mengambil harga emas dunia (GC=F) dan mengonversinya ke Rupiah per gram."""
    rate = usd_idr or get_usd_idr_rate()
    try:
        data = yf.download("GC=F", period="5d", progress=False, interval="1d")
        if not data.empty:
            close_usd = data["Close"].dropna().iloc[-1]
            usd_per_oz = float(close_usd.iloc[0] if hasattr(close_usd, "iloc") else close_usd)
            idr_per_gram = (usd_per_oz / TROY_OZ_TO_GRAM) * rate
            return {
                "usd_per_oz": usd_per_oz,
                "idr_per_gram": idr_per_gram,
                "rate": rate,
                "waktu": datetime.now().strftime("%d/%m/%Y %H:%M")
            }
    except Exception as e:
        print(f"⚠️ Gagal fetch Emas GC=F: {e}")
    return {
        "usd_per_oz": 2850.0,
        "idr_per_gram": (2850.0 / TROY_OZ_TO_GRAM) * rate,
        "rate": rate,
        "waktu": datetime.now().strftime("%d/%m/%Y %H:%M")
    }

def get_asset_live_price(ticker: str, asset_class: str, usd_idr: float) -> float:
    """Mengambil harga pasar live dalam IDR untuk kelas aset apa pun."""
    ticker = ticker.strip().upper()
    try:
        if asset_class == "idx":
            # Saham Indonesia (e.g. BBCA -> BBCA.JK)
            symbol = f"{ticker}.JK" if not ticker.endswith(".JK") else ticker
            df = yf.download(symbol, period="5d", progress=False, interval="1d")
            if not df.empty:
                val = df["Close"].dropna().iloc[-1]
                return float(val.iloc[0] if hasattr(val, "iloc") else val)

        elif asset_class == "gold":
            gold_info = get_gold_price_idr(usd_idr)
            return gold_info["idr_per_gram"]

        elif asset_class == "crypto":
            # Crypto (e.g. BTC -> BTC-USD)
            symbol = f"{ticker}-USD" if not ticker.endswith("-USD") else ticker
            df = yf.download(symbol, period="5d", progress=False, interval="1d")
            if not df.empty:
                val = df["Close"].dropna().iloc[-1]
                usd_val = float(val.iloc[0] if hasattr(val, "iloc") else val)
                return usd_val * usd_idr

        elif asset_class == "us_stock":
            # US Stocks (e.g. AAPL, NVDA)
            df = yf.download(ticker, period="5d", progress=False, interval="1d")
            if not df.empty:
                val = df["Close"].dropna().iloc[-1]
                usd_val = float(val.iloc[0] if hasattr(val, "iloc") else val)
                return usd_val * usd_idr

    except Exception as e:
        print(f"⚠️ Gagal fetch harga live {ticker} ({asset_class}): {e}")

    return 0.0

def load_multi_asset_portfolio() -> list:
    """Memuat daftar aset yang dimiliki dari file JSON."""
    os.makedirs(os.path.dirname(PORTFOLIO_FILE), exist_ok=True)
    if os.path.exists(PORTFOLIO_FILE):
        try:
            with open(PORTFOLIO_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return [x for x in data if not x.get("_keterangan")]
        except Exception as e:
            print(f"⚠️ Gagal baca {PORTFOLIO_FILE}: {e}")
    
    # Portfolio contoh awal jika belum ada file
    initial_demo = [
        {"ticker": "BBCA", "nama": "Bank Central Asia", "asset_class": "idx", "quantity": 1000, "avg_buy_price_idr": 9800, "catatan": "Core Banking"},
        {"ticker": "GOLD", "nama": "Emas Fisik/Digital", "asset_class": "gold", "quantity": 10.0, "avg_buy_price_idr": 1350000, "catatan": "Hedging Inflasi"},
        {"ticker": "BTC", "nama": "Bitcoin", "asset_class": "crypto", "quantity": 0.015, "avg_buy_price_idr": 1050000000, "catatan": "Aset Digital"},
        {"ticker": "NVDA", "nama": "NVIDIA Corp", "asset_class": "us_stock", "quantity": 2, "avg_buy_price_idr": 2000000, "catatan": "AI Sector"}
    ]
    save_multi_asset_portfolio(initial_demo)
    return initial_demo

def save_multi_asset_portfolio(holdings: list):
    """Menyimpan daftar aset ke file JSON secara atomik."""
    os.makedirs(os.path.dirname(PORTFOLIO_FILE), exist_ok=True)
    tmp_file = f"{PORTFOLIO_FILE}.tmp"
    with open(tmp_file, "w", encoding="utf-8") as f:
        json.dump(holdings, f, indent=2, ensure_ascii=False)
    os.replace(tmp_file, PORTFOLIO_FILE)

def calculate_multi_asset_summary(usd_idr: float = None) -> dict:
    """Menghitung ringkasan valuasi dan keuntungan seluruh kelas aset."""
    rate = usd_idr or get_usd_idr_rate()
    holdings = load_multi_asset_portfolio()

    total_modal = 0.0
    total_nilai = 0.0
    asset_details = []

    for item in holdings:
        ac = item.get("asset_class", "idx")
        ticker = item.get("ticker", "")
        qty = float(item.get("quantity", 0))
        avg_buy = float(item.get("avg_buy_price_idr", 0))
        
        current_price = get_asset_live_price(ticker, ac, rate)
        # Fallback jika offline/timeout
        if current_price <= 0:
            current_price = avg_buy

        modal = qty * avg_buy
        nilai = qty * current_price
        pl_rp = nilai - modal
        pl_pct = (pl_rp / modal * 100) if modal > 0 else 0.0

        total_modal += modal
        total_nilai += nilai

        asset_details.append({
            "Ticker": ticker,
            "Nama": item.get("nama", ticker),
            "Kelas Aset": ASSET_CLASS_LABELS.get(ac, ac),
            "asset_class": ac,
            "Jumlah": qty,
            "Harga Rata-rata Beli (Rp)": avg_buy,
            "Harga Saat Ini (Rp)": current_price,
            "Total Modal (Rp)": modal,
            "Nilai Pasar (Rp)": nilai,
            "Floating P/L (Rp)": pl_rp,
            "Floating P/L (%)": pl_pct,
            "Catatan": item.get("catatan", "")
        })

    total_pl_rp = total_nilai - total_modal
    total_pl_pct = (total_pl_rp / total_modal * 100) if total_modal > 0 else 0.0

    return {
        "usd_idr": rate,
        "total_modal": total_modal,
        "total_nilai": total_nilai,
        "total_pl_rp": total_pl_rp,
        "total_pl_pct": total_pl_pct,
        "assets": asset_details
    }
