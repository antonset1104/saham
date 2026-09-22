import os
import sys
import time
import json
import html
import requests
import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv

load_dotenv()

FILE_SAHAM = "Konfigurasi/saham.txt"
FILE_HASIL_CSV = "Database/hasil_screener_fundamental_jumat.csv"
FILE_HASIL_JSON = "Database/hasil_screener_fundamental_jumat.json"
FILE_LAST_SENT = "Database/last_sent_jumat_2000.json"

def get_usd_idr_rate():
    """Mengambil nilai tukar USD/IDR terkini untuk normalisasi laporan keuangan berdenominasi USD."""
    try:
        usd_rate = yf.Ticker("USDIDR=X").fast_info.get("last_price")
        if usd_rate and usd_rate > 10000:
            return float(usd_rate)
    except Exception:
        pass
    return 16000.0

def muat_daftar_saham(limit=None):
    """Memuat daftar kode saham IDX dari file Konfigurasi/saham.txt."""
    if not os.path.exists(FILE_SAHAM):
        print(f"❌ File konfigurasi '{FILE_SAHAM}' tidak ditemukan.")
        return []
    with open(FILE_SAHAM, "r") as f:
        tickers = [line.strip().upper() for line in f if line.strip() and not line.startswith("#")]
    if limit:
        tickers = tickers[:limit]
    return tickers

def evaluasi_fundamental_emiten(ticker, usd_rate=16000.0):
    """
    Mengevaluasi 1 emiten berdasarkan 12 Kriteria Screener Stockbit:
    1. Current Price to Book Value <= 2
    2. Current Price to Book Value > 0
    3. Current PE Ratio (TTM) <= 15
    4. Current PE Ratio (TTM) > 0
    5. Current PE Ratio (Annualised) <= 15
    6. Current PE Ratio (Annualised) > 0
    7. Debt to Equity Ratio (Quarter) <= 0.5
    8. Net Debt (Quarter) <= 0 (Net Cash)
    9. Net Income (Growth: YTD YoY) > 0
    10. Net Income (Growth: Annual YoY) > 0
    11. Return on Assets (TTM) >= 10%
    12. Return on Equity (TTM) >= 15%
    """
    sym = f"{ticker}.JK"
    try:
        t = yf.Ticker(sym)
        info = t.info
        if not info:
            return None
            
        price = info.get("currentPrice") or info.get("regularMarketPrice")
        if not price or price <= 0:
            return None

        curr = info.get("currency", "IDR")
        fin_curr = info.get("financialCurrency", curr)
        book_val = info.get("bookValue") or 0.0

        # Normalisasi PBV jika laporan keuangan dalam mata uang USD
        if curr == "IDR" and fin_curr == "USD" and book_val > 0:
            pbv = price / (book_val * usd_rate)
        else:
            pbv = info.get("priceToBook")
            if pbv is None and book_val > 0:
                pbv = price / book_val

        if pbv is None:
            pbv = 0.0

        # PER TTM & Annualised
        per_ttm = info.get("trailingPE") or 0.0
        per_ann = info.get("forwardPE")
        if per_ann is None or per_ann <= 0:
            per_ann = per_ttm

        # Debt to Equity Ratio (Quarter)
        de = info.get("debtToEquity") or 0.0
        # yfinance sering mengembalikan nilai dalam persen (misal 11.78 = 11.78% = 0.1178)
        der_ratio = (de / 100.0) if de > 2.0 else de

        # Total Debt & Total Cash (Net Debt = Total Debt - Total Cash)
        tot_debt = info.get("totalDebt") or 0.0
        tot_cash = info.get("totalCash") or 0.0
        net_debt = tot_debt - tot_cash

        # Pertumbuhan Laba Bersih
        eg_quarterly = info.get("earningsQuarterlyGrowth")
        eg_earnings = info.get("earningsGrowth")
        growth_ytd_yoy = eg_quarterly if eg_quarterly is not None else (eg_earnings or 0.0)
        growth_ann_yoy = eg_earnings if eg_earnings is not None else (eg_quarterly or 0.0)

        # ROA & ROE (persentase %)
        roa_dec = info.get("returnOnAssets") or 0.0
        roe_dec = info.get("returnOnEquity") or 0.0
        roa = roa_dec * 100.0 if roa_dec <= 1.0 else roa_dec
        roe = roe_dec * 100.0 if roe_dec <= 1.0 else roe_dec

        # --- VALIDASI 12 KRITERIA SCREENER ---
        c1 = (0 < pbv <= 2.0)
        c2 = (0 < per_ttm <= 15.0)
        c3 = (0 < per_ann <= 15.0)
        c4 = (der_ratio <= 0.5)
        c5 = (net_debt <= 0) # Net cash
        c6 = (growth_ytd_yoy > 0)
        c7 = (growth_ann_yoy > 0)
        c8 = (roa >= 10.0)
        c9 = (roe >= 15.0)

        memenuhi = all([c1, c2, c3, c4, c5, c6, c7, c8, c9])

        emiten_data = {
            "Ticker": ticker,
            "Nama": info.get("shortName") or info.get("longName") or ticker,
            "Sektor": info.get("sector") or "-",
            "Industri": info.get("industry") or "-",
            "Harga (Rp)": float(price),
            "PBV": round(float(pbv), 2),
            "PER TTM": round(float(per_ttm), 2),
            "PER Annualised": round(float(per_ann), 2),
            "DER": round(float(der_ratio), 2),
            "Net Debt (Rp)": float(net_debt),
            "Posisi Kas": "Net Cash (Bebas Utang)" if net_debt <= 0 else "Net Debt",
            "Growth YTD YoY (%)": round(float(growth_ytd_yoy * 100.0), 2),
            "Growth Annual YoY (%)": round(float(growth_ann_yoy * 100.0), 2),
            "ROA (%)": round(float(roa), 2),
            "ROE (%)": round(float(roe), 2),
            "Market Cap (Rp)": float(info.get("marketCap") or 0.0),
            "Lolos Screener": memenuhi,
            "Waktu Evaluasi": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        return emiten_data
    except Exception:
        return None

def jalankan_screener_fundamental(limit=None, max_workers=15):
    """
    Menjalankan proses screening fundamental untuk seluruh saham yang listing di BEI.
    Menyimpan hasil ke file Database/hasil_screener_fundamental_jumat.csv dan JSON.
    """
    tickers = muat_daftar_saham(limit=limit)
    if not tickers:
        print("⚠️ Tidak ada emiten untuk dievaluasi.")
        return pd.DataFrame()

    os.makedirs("Database", exist_ok=True)
    usd_rate = get_usd_idr_rate()
    print(f"🚀 [Jumat Malam 20:00 WIB] Memulai analisa fundamental seluruh bursa ({len(tickers)} emiten)...")
    print(f"💵 Kurs USD/IDR Acuan: Rp {usd_rate:,.0f}")

    start_time = time.time()
    hasil_semua = []

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(evaluasi_fundamental_emiten, tkr, usd_rate): tkr for tkr in tickers}
        for future in as_completed(futures):
            res = future.result()
            if res:
                hasil_semua.append(res)

    df_semua = pd.DataFrame(hasil_semua)
    if df_semua.empty:
        print("⚠️ Tidak ada data emiten yang berhasil diambil.")
        return pd.DataFrame()

    df_lolos = df_semua[df_semua["Lolos Screener"] == True].copy()
    
    # Urutkan berdasarkan ROE tertinggi lalu PER terendah
    if not df_lolos.empty:
        df_lolos = df_lolos.sort_values(by=["ROE (%)", "PER TTM"], ascending=[False, True]).reset_index(drop=True)

    # Simpan ke CSV & JSON
    df_lolos.to_csv(FILE_HASIL_CSV, index=False)
    with open(FILE_HASIL_JSON, "w") as f:
        json.dump(df_lolos.to_dict(orient="records"), f, indent=2)

    durasi = time.time() - start_time
    print(f"✅ Selesai dalam {durasi:.1f} detik. Total dievaluasi: {len(df_semua)}, Lolos Kriteria: {len(df_lolos)} emiten.")
    return df_lolos

def format_pesan_telegram_fundamental(df_lolos):
    """
    Menyusun teks pesan HTML Telegram yang rapi dan informatif untuk hasil screening fundamental.
    """
    waktu_str = datetime.now().strftime("%d/%m/%Y %H:%M WIB")
    lines = [
        "💎 <b>RADAR VALUE INVESTING — JUMAT MALAM</b>",
        f"📅 <i>{waktu_str}</i>",
        "🎯 <b>Filter Screener Fundamental Super Ketat (Stockbit):</b>",
        "  • <i>PBV: 0 &lt; PBV &le; 2.0</i>",
        "  • <i>PER TTM &amp; Ann: 0 &lt; PER &le; 15.0</i>",
        "  • <i>DER &le; 0.5 &amp; Net Debt &le; 0 (Kas Melimpah)</i>",
        "  • <i>Net Income Growth YoY &gt; 0% (Bertumbuh)</i>",
        "  • <i>ROA &ge; 10% &amp; ROE &ge; 15%</i>",
        "━━━━━━━━━━━━━━━━━━━━"
    ]

    if df_lolos.empty:
        lines.append("\n⚠️ <i>Tidak ada emiten di bursa yang memenuhi seluruh 12 kriteria super ketat pada evaluasi minggu ini.</i>")
        lines.append("💡 Pasar sedang berada di valuasi premium atau pertumbuhan laba tertekan.")
    else:
        lines.append(f"\n🌟 <b>Ditemukan {len(df_lolos)} Emiten Pilihan Terbaik:</b>\n")
        for idx, row in df_lolos.iterrows():
            tkr = html.escape(str(row["Ticker"]))
            nama = html.escape(str(row["Nama"]))
            harga = row["Harga (Rp)"]
            pbv = row["PBV"]
            per_ttm = row["PER TTM"]
            der = row["DER"]
            net_debt = row["Net Debt (Rp)"]
            cash_pos = f"Net Cash Rp {abs(net_debt)/1e9:.1f} M" if net_debt <= 0 else f"Net Debt Rp {net_debt/1e9:.1f} M"
            growth = row["Growth YTD YoY (%)"]
            roa = row["ROA (%)"]
            roe = row["ROE (%)"]

            lines.append(f"<b>{idx+1}. #{tkr} — {nama}</b>")
            lines.append(f"   💰 <b>Harga:</b> Rp {harga:,.0f}")
            lines.append(f"   📊 <b>Valuasi:</b> PBV {pbv:.2f}x | PER {per_ttm:.1f}x")
            lines.append(f"   🛡️ <b>Kesehatan Keuangan:</b> DER {der:.2f}x | {cash_pos}")
            lines.append(f"   📈 <b>Profitabilitas:</b> ROA {roa:.1f}% | ROE {roe:.1f}%")
            lines.append(f"   🚀 <b>Pertumbuhan Laba:</b> +{growth:.1f}% YoY")
            lines.append("")

    lines.append("━━━━━━━━━━━━━━━━━━━━")
    lines.append("💡 <i>Saham yang lolos memiliki fundamental istimewa: valuasi diskon (murah), kas bersih aman dari risiko kebangkrutan, serta efisiensi modal dan laba bertumbuh konsisten.</i>")
    lines.append("⚠️ <i>Bukan ajakan beli/jual resmi. Lakukan analisa mandiri (DYOR) sebelum berinvestasi.</i>")
    return "\n".join(lines)

def kirim_hasil_ke_telegram(df_lolos=None, force=False):
    """
    Mengirimkan laporan hasil screener fundamental ke Telegram jika bot terkonfigurasi.
    """
    from notifikasi_telegram import is_telegram_configured, kirim_pesan_telegram

    if not is_telegram_configured():
        return False, "Bot Telegram belum terkonfigurasi (Token / Chat ID kosong)."

    today_str = datetime.now().strftime("%Y-%m-%d")
    
    # Cek duplikasi jika bukan dipaksa (force=False)
    if not force and os.path.exists(FILE_LAST_SENT):
        try:
            with open(FILE_LAST_SENT, "r") as f:
                data = json.load(f)
                if data.get("last_sent_date") == today_str:
                    return False, f"Laporan fundamental Jumat malam sudah pernah dikirim hari ini ({today_str})."
        except Exception:
            pass

    if df_lolos is None or df_lolos.empty:
        if os.path.exists(FILE_HASIL_CSV):
            try:
                df_lolos = pd.read_csv(FILE_HASIL_CSV)
            except Exception:
                df_lolos = pd.DataFrame()
                
    if df_lolos is None or df_lolos.empty:
        # Jalankan screening baru
        df_lolos = jalankan_screener_fundamental()

    pesan = format_pesan_telegram_fundamental(df_lolos)
    berhasil = kirim_pesan_telegram(pesan)

    if berhasil:
        try:
            os.makedirs(os.path.dirname(FILE_LAST_SENT), exist_ok=True)
            with open(FILE_LAST_SENT, "w") as f:
                json.dump({
                    "last_sent_date": today_str,
                    "waktu": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "total_saham_lolos": len(df_lolos) if df_lolos is not None else 0
                }, f, indent=2)
        except Exception:
            pass
        return True, f"Laporan screener fundamental berhasil dikirim ke Telegram ({len(df_lolos)} saham)."
    else:
        return False, "Gagal mengirim pesan ke Telegram API."

if __name__ == "__main__":
    limit_arg = None
    if "--limit" in sys.argv:
        idx = sys.argv.index("--limit")
        if idx + 1 < len(sys.argv):
            limit_arg = int(sys.argv[idx + 1])

    if "--kirim-telegram" in sys.argv:
        df = jalankan_screener_fundamental(limit=limit_arg)
        sukses, msg = kirim_hasil_ke_telegram(df, force=True)
        print("Hasil kirim Telegram:", msg)
    else:
        df = jalankan_screener_fundamental(limit=limit_arg)
        print("\nHasil Screener Lolos Kriteria:")
        if not df.empty:
            print(df[["Ticker", "Nama", "Harga (Rp)", "PBV", "PER TTM", "DER", "ROA (%)", "ROE (%)"]])
        else:
            print("Tidak ada saham yang lolos.")
