import sys
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

try:
    import truststore
    truststore.inject_into_ssl()
except Exception:
    pass

import yfinance as yf
import pandas as pd
import numpy as np
import os
import time
import requests
import xml.etree.ElementTree as ET # <-- Modul untuk membaca berita RSS
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from datetime import datetime
from dotenv import load_dotenv
from analysis_signal import calculate_signal_score
from notifikasi_telegram import kirim_alert_bsjp, is_telegram_configured

load_dotenv()

# ==========================================
# SECTION 1: KONFIGURASI & TOKEN CURIAN BROKSUM
# ==========================================
FILE_SAHAM = "Konfigurasi/saham.txt"
FILE_HASIL = "Database/hasil_screener.csv"
LOCK_FILE = "sedang_update.lock"
DIR_ARSIP = "Arsip_Data_Harian"

# --- KONFIGURASI STOCKBIT DARI .ENV ATAU FILE TERPISAH ---
TOKEN_CURIAN = os.getenv("STOCKBIT_TOKEN", "").strip()
if not TOKEN_CURIAN:
    try:
        with open("token_stockbit.txt", "r") as file:
            for baris in file:
                baris_clean = baris.strip()
                if baris_clean and not baris_clean.startswith("#") and "PASTE_TOKEN" not in baris_clean:
                    TOKEN_CURIAN = baris_clean
                    break
    except FileNotFoundError:
        TOKEN_CURIAN = ""

if not os.path.exists(DIR_ARSIP):
    os.makedirs(DIR_ARSIP)

def get_safe_session():
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    })
    retry = Retry(connect=5, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
    adapter = HTTPAdapter(max_retries=retry)
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    return session

def load_tickers():
    if not os.path.exists(FILE_SAHAM):
        print(f"❌ Error: File '{FILE_SAHAM}' tidak ditemukan!")
        return []
    with open(FILE_SAHAM, "r") as file:
        return [baris.strip().upper() for baris in file if baris.strip()]

# ==========================================
# SECTION 2: FUNDAMENTAL, SENTIMEN & BROKSUM
# ==========================================
def get_fundamental(ticker_jk):
    try:
        ticker_obj = yf.Ticker(ticker_jk)
        info_data = ticker_obj.info
        mcap = info_data.get('marketCap', 0)
        per = info_data.get('trailingPE', 0)
        pbv = info_data.get('priceToBook', 0)
    except:
        mcap, per, pbv = 0, 0, 0

    if mcap > 10000000000000: kategori_saham = "Big Cap (Lapis 1)"
    elif mcap > 1000000000000: kategori_saham = "Mid Cap (Lapis 2)"
    elif mcap > 0: kategori_saham = "Small Cap (Lapis 3)"
    else: kategori_saham = "Tidak Diketahui"
    
    return kategori_saham, per, pbv

# FUNGSI PENYADAP BROKSUM STOCKBIT (AMAN DARI CRASH)
def get_broksum_aman(ticker):
    url = f"https://exodus.stockbit.com/marketdetectors/{ticker}?transaction_type=TRANSACTION_TYPE_NET&market_board=MARKET_BOARD_REGULER&investor_type=INVESTOR_TYPE_ALL&limit=25"
    headers = {
        "Authorization": f"Bearer {TOKEN_CURIAN}",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Origin": "https://stockbit.com",
        "Referer": f"https://stockbit.com/symbol/{ticker}"
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=3)
        if response.status_code == 200:
            data = response.json().get('data', {})
            
            # Mengambil Top 3 Buyer
            buy = data.get('broker_summary', {}).get('brokers_buy', [])
            top_buy = [b['netbs_broker_code'] for b in buy[:3]]
            
            # Mengambil Top 3 Seller
            sell = data.get('broker_summary', {}).get('brokers_sell', [])
            top_sell = [s['netbs_broker_code'] for s in sell[:3]]
            
            # Mengambil Status Akumulasi/Distribusi Bandar
            status_acc = data.get('bandar_detector', {}).get('broker_accdist', 'Neutral')
            
            return f"B: {', '.join(top_buy) if top_buy else '-'} | S: {', '.join(top_sell) if top_sell else '-'} | ({status_acc})"
        
        elif response.status_code in [401, 403]:
            return "Token Mati (Perlu Update)"
        else:
            return f"Error HTTP {response.status_code}"
    except requests.exceptions.Timeout:
        return "Timeout Broksum"
    except Exception:
        return "Gagal Load Broksum"

# PENYADAP SENTIMEN BERITA GOOGLE NEWS
def cek_sentimen_berita(ticker, session):
    # TAMBAHKAN BARIS INI: Mesin akan langsung pulang tanpa ngecek Google
    return "Netral / Sepi Berita" 
    
    # === KODE DI BAWAH INI TIDAK AKAN DIEKSEKUSI LAGI ===
    url = f"https://news.google.com/rss/search?q={ticker}+saham&hl=id&gl=ID&ceid=ID:id"
    try:
        resp = session.get(url, timeout=3)
        if resp.status_code == 200:
            root = ET.fromstring(resp.text)
            titles = [item.find('title').text for item in root.findall('.//item')][:5] 
            
            pos_words = ['laba', 'meroket', 'akuisisi', 'dividen', 'tumbuh', 'lonjak', 'rekomendasi beli', 'prospek', 'borong', 'triliun', 'untung', 'merger']
            neg_words = ['rugi', 'anjlok', 'suspend', 'gugat', 'turun', 'merosot', 'jual', 'hancur', 'bengkok', 'utang', 'pailit', 'kasus']
            
            score = 0
            for t in titles:
                t_lower = t.lower()
                if any(w in t_lower for w in pos_words): score += 1
                if any(w in t_lower for w in neg_words): score -= 1
                
            if score > 0: return "Sentimen Positif 📰"
            elif score < 0: return "Sentimen Negatif ⚠️"
            else: return "Netral / Sepi Berita"
        return "Netral / Sepi Berita"
    except:
        return "Netral / Sepi Berita"

# ==========================================
# SECTION 3: KALKULASI TEKNIKAL & BANDARMOLOGI
# ==========================================
def hitung_semua_indikator(df_saham, ticker, aman_session):
    df_saham = df_saham.copy()
    if isinstance(df_saham.columns, pd.MultiIndex):
        df_saham.columns = [c[0] if isinstance(c, tuple) else c for c in df_saham.columns]

    close_today = float(df_saham['Close'].iloc[-1])
    close_yest = float(df_saham['Close'].iloc[-2])
    open_today = float(df_saham['Open'].iloc[-1])
    high_today = float(df_saham['High'].iloc[-1])
    low_today = float(df_saham['Low'].iloc[-1])
    vol_today = int(df_saham['Volume'].iloc[-1].item()) if not pd.isna(df_saham['Volume'].iloc[-1].item()) else 0
    
    change_rp = close_today - close_yest
    change_pct = (change_rp / close_yest) * 100
    momentum = "Positif" if change_rp > 0 else "Negatif"
    
    if vol_today > 0 and close_today >= 50:
        status_sentimen = cek_sentimen_berita(ticker, aman_session)
    else:
        status_sentimen = "Netral / Sepi Berita"
    
    gap_pct = ((open_today - close_yest) / close_yest) * 100
    if gap_pct >= 2.0: status_gap = f"Gap Up (+{gap_pct:.1f}%)"
    elif gap_pct <= -2.0: status_gap = f"Gap Down ({gap_pct:.1f}%)"
    else: status_gap = "Normal"
    
    range_today = high_today - low_today
    if range_today > 0:
        buying_power = (close_today - low_today) / range_today
        if buying_power > 0.7: tekanan = "Dominan Beli (Hajar Kanan)"
        elif buying_power < 0.3: tekanan = "Dominan Jual (Guyur)"
        else: tekanan = "Seimbang / Adu Mekanik"
    else:
        tekanan = "Tidak Ada Transaksi"

    body_candle = abs(close_today - open_today)
    upper_shadow = high_today - max(open_today, close_today)
    lower_shadow = min(open_today, close_today) - low_today
    
    if body_candle <= (range_today * 0.1): pola_candle = "Doji (Ragu-ragu)"
    elif lower_shadow > (body_candle * 2) and upper_shadow < (body_candle * 0.2): pola_candle = "Hammer (Potensi Reversal)"
    elif body_candle > (range_today * 0.8) and close_today > open_today: pola_candle = "Marubozu (Strong Bullish)"
    else: pola_candle = "Normal"

    ma_20 = df_saham['Close'].rolling(window=20).mean().iloc[-1].item()
    ma_50 = df_saham['Close'].rolling(window=50).mean().iloc[-1].item() if len(df_saham) >= 50 else ma_20
    vol_ma_20 = df_saham['Volume'].rolling(window=20).mean().iloc[-1].item()
    ma_signal = "Uptrend" if close_today > ma_20 else "Downtrend"
    vol_breakout = "Tembus MA20" if vol_today > vol_ma_20 else "Normal"
    
    ma_5 = df_saham['Close'].rolling(window=5).mean().iloc[-1].item()
    ma_5_prev = df_saham['Close'].rolling(window=5).mean().iloc[-2].item()
    ma_20_prev = df_saham['Close'].rolling(window=20).mean().iloc[-2].item()
    
    if ma_5 > ma_20 and ma_5_prev <= ma_20_prev: ma_cross = "Golden Cross"
    elif ma_5 < ma_20 and ma_5_prev >= ma_20_prev: ma_cross = "Death Cross"
    elif ma_5 > ma_20: ma_cross = "Bullish"
    else: ma_cross = "Bearish"

    if ma_5 > ma_20 and ma_20 > ma_50: trend_ma_gabungan = "Perfect Uptrend (5>20>50)"
    elif ma_5 > ma_20 and ma_20 <= ma_50: trend_ma_gabungan = "Awal Reversal (5>20)"
    elif ma_5 < ma_20 and ma_20 < ma_50: trend_ma_gabungan = "Strong Downtrend (5<20<50)"
    else: trend_ma_gabungan = "Konsolidasi / Transisi"

    ema_12 = df_saham['Close'].ewm(span=12, adjust=False).mean()
    ema_26 = df_saham['Close'].ewm(span=26, adjust=False).mean()
    macd_line = ema_12 - ema_26
    signal_line = macd_line.ewm(span=9, adjust=False).mean()
    macd_val = macd_line.iloc[-1].item()
    sig_val = signal_line.iloc[-1].item()
    
    if macd_val > sig_val and macd_val > 0: status_macd = "Strong Bullish"
    elif macd_val > sig_val: status_macd = "Bullish MACD"
    elif macd_val < sig_val and macd_val < 0: status_macd = "Strong Bearish"
    else: status_macd = "Bearish MACD"
    
    if vol_today > (vol_ma_20 * 2):
        if close_today > open_today: status_bandar = "Akumulasi Kuat"
        elif close_today < open_today: status_bandar = "Distribusi Kuat"
        else: status_bandar = "Normal"
    else:
        status_bandar = "Normal"

    diff_close = df_saham['Close'].diff().fillna(0)
    obv_direction = np.where(diff_close > 0, 1, np.where(diff_close < 0, -1, 0))
    df_saham['OBV'] = (obv_direction * df_saham['Volume']).cumsum()
    
    obv_sekarang = float(df_saham['OBV'].iloc[-1])
    obv_5_hari_lalu = float(df_saham['OBV'].iloc[-6]) if len(df_saham['OBV']) >= 6 else obv_sekarang
    if obv_sekarang > obv_5_hari_lalu: obv_trend = "Akumulasi (Naik)"
    elif obv_sekarang < obv_5_hari_lalu: obv_trend = "Distribusi (Turun)"
    else: obv_trend = "Netral"
    
    std_20 = df_saham['Close'].rolling(window=20).std().iloc[-1].item()
    upper_bb = ma_20 + (std_20 * 2)
    lower_bb = ma_20 - (std_20 * 2)
    bandwidth = ((upper_bb - lower_bb) / ma_20) * 100 if ma_20 != 0 else 0
        
    if bandwidth < 8.0: status_bb = "Squeeze"
    elif close_today > upper_bb: status_bb = "Breakout Upper"
    elif close_today > lower_bb and (abs(close_today - lower_bb) / lower_bb) < 0.02: status_bb = "Bottom Rebound"
    else: status_bb = "Normal"

    support_20 = df_saham['Low'].rolling(window=20).min().iloc[-1].item()
    resist_20 = df_saham['High'].rolling(window=20).max().iloc[-1].item()

    jarak_support = ((close_today - support_20) / support_20) * 100 if support_20 > 0 else 0
    if jarak_support <= 3.0: posisi_entry = "Dekat Support (Low Risk)"
    elif jarak_support >= 10.0: posisi_entry = "Rawan Pucuk (High Risk)"
    else: posisi_entry = "Area Tengah"

    if bandwidth > 15.0: risiko = "Tinggi"
    elif bandwidth > 8.0: risiko = "Sedang"
    else: risiko = "Rendah"
    
    delta = df_saham['Close'].diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    avg_gain = gain.ewm(alpha=1/14, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/14, adjust=False).mean()
    rs = avg_gain / avg_loss
    rsi_raw = (100 - (100 / (1 + rs))).iloc[-1].item()
    rsi = int(round(rsi_raw)) if not pd.isna(rsi_raw) else 0

    typical_price = (df_saham['High'] + df_saham['Low'] + df_saham['Close']) / 3
    vwap_5 = (typical_price * df_saham['Volume']).rolling(window=5).sum() / (df_saham['Volume'].rolling(window=5).sum() + 1)
    vwap_val = vwap_5.iloc[-1].item()
    if close_today > (vwap_val * 1.01): posisi_vwap = "Di Atas VWAP (Kuat)"
    elif close_today < (vwap_val * 0.99): posisi_vwap = "Di Bawah VWAP (Lemah)"
    else: posisi_vwap = "Persis di VWAP"

    penyebut_ad = df_saham['High'] - df_saham['Low']
    penyebut_ad = penyebut_ad.replace(0, 0.0001) 
    mfm = ((df_saham['Close'] - df_saham['Low']) - (df_saham['High'] - df_saham['Close'])) / penyebut_ad
    mfv = mfm * df_saham['Volume']
    ad_line = mfv.cumsum()
    ad_sekarang = ad_line.iloc[-1].item()
    ad_5_hari_lalu = ad_line.iloc[-6].item() if len(ad_line) >= 6 else ad_sekarang
    
    if ad_sekarang > ad_5_hari_lalu: smart_money = "Akumulasi Pro (Smart Money)"
    elif ad_sekarang < ad_5_hari_lalu: smart_money = "Distribusi Pro (Guyuran)"
    else: smart_money = "Netral"

    vol_5_avg = df_saham['Volume'].rolling(window=5).mean().iloc[-1].item()
    val_transaksi = vol_5_avg * close_today
    if val_transaksi > 50_000_000_000: kelas_transaksi = "Sultan (> 50M/hari)"
    elif val_transaksi > 5_000_000_000: kelas_transaksi = "Ritel Aktif (5M - 50M)"
    else: kelas_transaksi = "Gorengan Sepi (< 5M)"

    vol_avg_10 = df_saham['Volume'].rolling(window=10).mean().iloc[-1].item()
    if vol_avg_10 > 0:
        rvol_pct = (vol_today / vol_avg_10) * 100
        if rvol_pct > 300: rvol_status = "Ledakan Ekstrem (> 300%)"
        elif rvol_pct > 150: rvol_status = "Anomali Tinggi (150-300%)"
        elif rvol_pct < 50: rvol_status = "Sepi (< 50%)"
        else: rvol_status = "Normal (50-150%)"
    else:
        rvol_status = "Normal (50-150%)"
        
    if close_today > ma_20 and ma_20 > ma_50: siklus = "Mark-Up (Fase Pesta)"
    elif close_today < ma_20 and ma_20 < ma_50: siklus = "Mark-Down (Fase Runtuh)"
    elif close_today > ma_20 and ma_20 <= ma_50: siklus = "Accumulation (Kumpul Barang)"
    elif close_today < ma_20 and ma_20 >= ma_50: siklus = "Distribution (Fase Jualan)"
    else: siklus = "Sideways"

    df_20 = df_saham.tail(20)
    range_harian = df_20['High'] - df_20['Low'] + 0.0001
    ekor_atas = df_20['High'] - df_20[['Open', 'Close']].max(axis=1)
    rasio_ekor = ekor_atas / range_harian
    tiang_jemuran = (rasio_ekor > 0.5).sum()
    
    if tiang_jemuran >= 4: karakter_bandar = "Spesialis Tiang Jemuran (Banting Pucuk)"
    elif tiang_jemuran == 0: karakter_bandar = "Solid (Jarang Dibanting)"
    else: karakter_bandar = "Normal"

    df_saham['H-L'] = df_saham['High'] - df_saham['Low']
    df_saham['H-PC'] = abs(df_saham['High'] - df_saham['Close'].shift(1))
    df_saham['L-PC'] = abs(df_saham['Low'] - df_saham['Close'].shift(1))
    df_saham['TR'] = df_saham[['H-L', 'H-PC', 'L-PC']].max(axis=1)
    atr_14 = df_saham['TR'].rolling(window=14).mean().iloc[-1].item()
    if pd.isna(atr_14) or atr_14 == 0: atr_14 = range_today if range_today > 0 else 1

    target_tp = int(close_today + (atr_14 * 1.5))
    target_cl = int(close_today - atr_14)
    auto_plan = f"TP: {target_tp} | CL: {target_cl}"

    if lower_shadow > (body_candle * 2) and lower_shadow > (range_today * 0.5): 
        deteksi_shakeout = "Jarum Bawah (Sinyal Pantulan Kuat)"
    else: 
        deteksi_shakeout = "Normal"

    streak_count = 0
    arah_streak = 0
    for i in range(1, min(10, len(df_saham))):
        c_curr = df_saham['Close'].iloc[-i].item()
        c_prev = df_saham['Close'].iloc[-(i+1)].item()
        if i == 1:
            if c_curr > c_prev: arah_streak = 1
            elif c_curr < c_prev: arah_streak = -1
            else: break
            streak_count = 1
        else:
            if arah_streak == 1 and c_curr > c_prev: streak_count += 1
            elif arah_streak == -1 and c_curr < c_prev: streak_count += 1
            else: break
            
    if arah_streak == 1 and streak_count >= 1: info_streak = f"Naik {streak_count} Hari Beruntun"
    elif arah_streak == -1 and streak_count >= 1: info_streak = f"Turun {streak_count} Hari Beruntun"
    else: info_streak = "Sideways / Stagnan"

    if open_today == low_today and close_today > open_today: status_open = "Open = Low (Bullish Kuat)"
    elif open_today == high_today and close_today < open_today: status_open = "Open = High (Tekanan Jual)"
    else: status_open = "Normal"

    potensi_upside = ((resist_20 - close_today) / close_today) * 100 if close_today > 0 else 0
    risiko_downside = ((close_today - support_20) / close_today) * 100 if close_today > 0 else 0
    if risiko_downside > 0:
        rrr_val = potensi_upside / risiko_downside
        if rrr_val >= 3: status_rrr = "Sangat Menarik (> 1:3)"
        elif rrr_val >= 1.5: status_rrr = "Ideal (1:2)"
        elif rrr_val < 1: status_rrr = "Tidak Ideal (< 1:1)"
        else: status_rrr = "Menengah (1:1)"
    else:
        status_rrr = "Di Area Support"

    low_14 = df_saham['Low'].rolling(window=14).min()
    high_14 = df_saham['High'].rolling(window=14).max()
    denominator = high_14 - low_14
    denominator = denominator.replace(0, 0.0001) 
    
    df_saham['%K'] = 100 * ((df_saham['Close'] - low_14) / denominator)
    df_saham['%D'] = df_saham['%K'].rolling(window=3).mean()
    
    try:
        k_val = df_saham['%K'].iloc[-1].item()
        d_val = df_saham['%D'].iloc[-1].item()
        
        if pd.isna(k_val) or pd.isna(d_val): status_stoch = "Netral / Sideways"
        elif k_val < 20 and d_val < 20: status_stoch = "Oversold (Jenuh Jual - Peluang)"
        elif k_val > 80 and d_val > 80: status_stoch = "Overbought (Jenuh Beli - Rawan)"
        elif k_val > d_val and k_val < 50: status_stoch = "Golden Cross (Awal Bullish)"
        elif k_val < d_val and k_val > 50: status_stoch = "Death Cross (Awal Bearish)"
        else: status_stoch = "Netral / Sideways"
    except:
        status_stoch = "Netral / Sideways"

    try:
        vol_3_avg = df_saham['Volume'].rolling(window=3).mean().iloc[-1].item()
        if vol_ma_20 > 0:
            rasio_kering = vol_3_avg / vol_ma_20
            if rasio_kering < 0.40 and bandwidth < 12.0:  
                status_supply = "Supply Kering (Siap Pump) 🏜️"
            elif rasio_kering > 2.0 and close_today < open_today:
                status_supply = "Supply Banjir (Distribusi) 🌊"
            else:
                status_supply = "Normal / Sedang Transisi"
        else:
            status_supply = "Normal / Sedang Transisi"
    except:
        status_supply = "Normal / Sedang Transisi"

    # ==========================================
    # RUMUS BARU: FIBONACCI RETRACEMENT (Otomatis)
    # ==========================================
    try:
        swing_high = df_saham['High'].max()
        swing_low = df_saham['Low'].min()
        selisih = swing_high - swing_low
        
        if selisih > 0:
            f_236 = swing_high - (0.236 * selisih)
            f_382 = swing_high - (0.382 * selisih)
            f_500 = swing_high - (0.500 * selisih)
            f_618 = swing_high - (0.618 * selisih) # Golden Ratio
            f_786 = swing_high - (0.786 * selisih)
            
            if close_today >= f_236:
                support_fibo = f_236
                nama_fibo = "23.6%"
            elif close_today >= f_382:
                support_fibo = f_382
                nama_fibo = "38.2%"
            elif close_today >= f_500:
                support_fibo = f_500
                nama_fibo = "50.0%"
            elif close_today >= f_618:
                support_fibo = f_618
                nama_fibo = "61.8% (Golden Ratio)"
            elif close_today >= f_786:
                support_fibo = f_786
                nama_fibo = "78.6%"
            else:
                support_fibo = swing_low
                nama_fibo = "Bottom / 100%"

            jarak_ke_fibo = ((close_today - support_fibo) / support_fibo) * 100
            
            # KOMBINASI (CONFLUENCE): Fibo + Supply Kering / Oversold / Hammer
            if jarak_ke_fibo <= 2.5: # Toleransi jarak 2.5% dari garis Support
                if "Oversold" in status_stoch or "Kering" in status_supply or "Jarum Bawah" in deteksi_shakeout:
                    status_fibo = f"Golden Rebound Fibo {nama_fibo} 🎯"
                else:
                    status_fibo = f"Dekat Support Fibo {nama_fibo}"
            elif jarak_ke_fibo <= 6.0:
                status_fibo = f"Mendekati Fibo {nama_fibo}"
            else:
                status_fibo = "Mengambang (Jauh dari Fibo)"
        else:
            status_fibo = "Normal / Sideways"
    except:
        status_fibo = "Normal / Sideways"

    return {
        "Open": open_today, "High": high_today, "Low": low_today,
        "Harga (Rp)": close_today, "Harga MA20": int(ma_20), "Support": int(support_20), "Resistance": int(resist_20),
        "Change (%)": change_pct, "Volume": vol_today, "Vol Breakout": vol_breakout, "RSI (14D)": rsi,
        "Momentum": momentum, "MA Signal": ma_signal, "MA Cross": ma_cross, "MACD": status_macd,
        "Trend MA (5,20,50)": trend_ma_gabungan,
        "Status Bandar": status_bandar, "OBV Trend": obv_trend, "Status Gap": status_gap, "Tekanan Bandar": tekanan, 
        "Status BB": status_bb, "Risiko": risiko,
        "Pola Candle": pola_candle, "Posisi Entry": posisi_entry,
        "Likuiditas": "> 1 Miliar" if (close_today * vol_today) > 1000000000 else "< 1 Miliar",
        "Posisi VWAP": posisi_vwap, "Kekuatan A/D": smart_money, "Kelas Transaksi": kelas_transaksi,
        "RVOL (Anomali Vol)": rvol_status, "Fase Siklus Bandar": siklus, "Karakter Gorengan": karakter_bandar,
        "Sinyal Cuci Barang": deteksi_shakeout, "Streak Harian": info_streak, "Auto Trading Plan": auto_plan,
        "Status Open": status_open, "Risk/Reward Ratio": status_rrr,
        "Status Stochastic": status_stoch,
        "Status Sentimen": status_sentimen,
        "Kondisi Supply": status_supply,
        "Status Fibonacci": status_fibo
    }

import argparse

# ==========================================
# SECTION 4: EKSEKUSI UTAMA (MULTITHREADING AMAN)
# ==========================================
def parse_args():
    parser = argparse.ArgumentParser(description="AlgoTrade Screener IHSG - Data Ingestion & Technical Engine")
    parser.add_argument("--limit", type=int, default=None, help="Batasi jumlah saham yang diproses (untuk pengujian cepat)")
    parser.add_argument("--tickers", type=str, default=None, help="Daftar ticker tertentu yang diproses (pisahkan koma, contoh: BBCA,TLKM,ASII)")
    parser.add_argument("--dry-run", action="store_true", help="Jalankan kalkulasi tanpa menyimpan hasil ke disk")
    return parser.parse_args()

def main():
    args = parse_args()

    if os.path.exists(LOCK_FILE): os.remove(LOCK_FILE)
    with open(LOCK_FILE, "w") as f: f.write("SEDANG PROSES")

    try:
        now = datetime.now()
        tanggal_hari_ini = now.strftime("%Y-%m-%d")
        waktu_sekarang = now.strftime("%H:%M")
        jam_sekarang = now.hour 
        file_arsip_harian = os.path.join(DIR_ARSIP, f"screener_{tanggal_hari_ini}.csv")

        print("⏳ Memulai pembaruan data saham (Ultimate Diagnostic Mode)...")
        if args.tickers:
            daftar_saham = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
            print(f"🎯 Target spesifik ({len(daftar_saham)} emiten): {', '.join(daftar_saham)}")
        else:
            daftar_saham = load_tickers()
            
        if not daftar_saham:
            print("⚠️ Tidak ada daftar saham untuk diproses.")
            return

        if args.limit and args.limit > 0:
            daftar_saham = daftar_saham[:args.limit]
            print(f"🔬 Mode Uji Coba Cepat (Limit: {args.limit} emiten)...")
        
        tickers_jk = [f"{t}.JK" for t in daftar_saham]
        tickers_str = " ".join(tickers_jk)
        aman_session = get_safe_session()
        
        print(f"📥 Mengunduh {len(daftar_saham)} data saham secara bersamaan (Maks 8 jalur)...")
        data_mentah = yf.download(
            tickers_str, period="3mo", interval="1d", group_by='ticker', threads=8, session=aman_session, progress=False
        )
        
        if data_mentah.empty:
            print("❌ ERROR FATAL: Yahoo Finance menolak permintaan data.")
            return

        import concurrent.futures
        import random

        print("⚡ Memproses teknikal, fundamental, berita & broksum secara Paralel (Safe Mode)...")
        
        def proses_saham(ticker):
            # HAPUS time.sleep dari sini agar mesin bisa ngebut maksimal!
            try:
                t_jk = f"{ticker}.JK"
                if t_jk in data_mentah:
                    df_saham = data_mentah[t_jk].dropna(subset=['Open', 'Close', 'Volume', 'High', 'Low'])
                    if len(df_saham) >= 50:
                        
                        # --- 1. FILTER SAHAM ZOMBIE (Trik Super Cepat) ---
                        vol_today = int(df_saham['Volume'].iloc[-1].item())
                        harga_today = df_saham['Close'].iloc[-1].item()
                        
                        # Jika hari ini tidak ada transaksi sama sekali, LANGSUNG SKIP (Hemat 70% waktu!)
                        if vol_today == 0:
                            return None

                        ind = hitung_semua_indikator(df_saham, ticker, aman_session)
                        kat, per, pbv = get_fundamental(t_jk)
                        
                        # --- 2. FILTER BROKSUM PINTAR ---
                        # Hanya curi data bandar jika transaksinya lebih dari Rp 1 Miliar hari ini
                        val_transaksi = vol_today * harga_today
                        if val_transaksi > 1000000000:
                            time.sleep(random.uniform(0.1, 0.2)) # Jeda tipis khusus saham aktif agar Stockbit aman
                            broksum_info = get_broksum_aman(ticker)
                        else:
                            broksum_info = "Transaksi Sepi (Skip Broksum)"
                        
                        score = 0
                        if ind["Vol Breakout"] == "Tembus MA20": score += 1
                        if ind["RSI (14D)"] > 50: score += 1
                        if ind["Momentum"] == "Positif": score += 1
                        if ind["MA Signal"] == "Uptrend": score += 1
                        if ind["MA Cross"] in ["Golden Cross", "Bullish"]: score += 1
                        if ind["MACD"] in ["Strong Bullish", "Bullish MACD"]: score += 1
                        if ind["Status Bandar"] == "Akumulasi Kuat": score += 1  
                        if ind["OBV Trend"] == "Akumulasi (Naik)": score += 1   
                        if ind["Tekanan Bandar"] == "Dominan Beli (Hajar Kanan)": score += 1
                        if "Gap Up" in ind["Status Gap"]: score += 1
                        if ind.get("Status Sentimen") == "Sentimen Positif 📰": score += 1

                        rekomendasi = "BELI" if score >= 7 else "WAIT & SEE"
                        
                        if per > 0 and per < 15 and pbv > 0 and pbv < 1.5: valuasi = "Undervalued (Murah)"
                        elif per > 25 or pbv > 3.0: valuasi = "Overvalued (Mahal)"
                        else: valuasi = "Fair Value (Wajar)"
                        
                        data_akhir = {
                            "Waktu Update": waktu_sekarang, 
                            "Ticker": ticker, 
                            "Broksum": broksum_info,
                            "Kategori": kat, 
                            "Valuasi": valuasi, 
                            "PER (x)": per, 
                            "PBV (x)": pbv
                        }
                        data_akhir.update(ind)
                        sig_res = calculate_signal_score(df_saham, indikator=ind)
                        data_akhir.update({
                            "Total Score": score, 
                            "Rekomendasi": rekomendasi, 
                            "Signal Quant": sig_res["signal"],
                            "Score Quant": sig_res["score"],
                            "Alasan Sinyal": sig_res["reason_str"],
                            "Status Akuisisi": "TIDAK ADA", 
                            "Terakhir Update": now.strftime("%Y-%m-%d %H:%M:%S")
                        })
                        return data_akhir
            except Exception as e:
                pass
            return None

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            hasil_paralel = list(executor.map(proses_saham, daftar_saham))
            
        hasil = [h for h in hasil_paralel if h is not None]

        if hasil:
            df_hasil = pd.DataFrame(hasil)
            
            print("🧠 Menjalankan Algoritma Machine Learning (Mendeteksi Anomali Bandar)...")
            try:
                from sklearn.ensemble import IsolationForest
                
                fitur_ml = ['Change (%)', 'Volume', 'RSI (14D)', 'Total Score']
                df_fitur = df_hasil[fitur_ml].fillna(0)
                
                model = IsolationForest(contamination=0.05, random_state=42)
                df_hasil['ML_Outlier'] = model.fit_predict(df_fitur)
                
                status_ml = []
                for _, row in df_hasil.iterrows():
                    if row['ML_Outlier'] == -1 and row['Change (%)'] <= 5.0 and row['Volume'] > 0:
                        status_ml.append("🔥 ANOMALI BANDAR (Siap Ledakan)")
                    elif row['ML_Outlier'] == -1 and row['Change (%)'] > 5.0:
                        status_ml.append("⚠️ Anomali (Sudah Terbang)")
                    else:
                        status_ml.append("Biasa / Mengikuti Pasar")
                        
                df_hasil['Prediksi Machine Learning'] = status_ml
                df_hasil.drop(columns=['ML_Outlier'], inplace=True)
                print("✅ Machine Learning selesai mendeteksi anomali!")
                
            except ImportError:
                print("⚠️ Library 'scikit-learn' belum diinstal. Lewati Machine Learning.")
                df_hasil['Prediksi Machine Learning'] = "Library ML Belum Diinstal"
            except Exception as e:
                print(f"⚠️ Machine Learning Error: {e}")
                df_hasil['Prediksi Machine Learning'] = "Biasa / Mengikuti Pasar"

            if args.dry_run:
                print(f"🔬 [Dry-Run] Kalkulasi sukses untuk {len(df_hasil)} saham! (Mode simulasi: data tidak disimpan).")
                return

            # 1. SELALU Simpan Data Utama secara Atomik (Mencegah Corrupt saat dibaca Web)
            os.makedirs(os.path.dirname(FILE_HASIL), exist_ok=True)
            tmp_hasil = f"{FILE_HASIL}.tmp"
            df_hasil.to_csv(tmp_hasil, index=False)
            os.replace(tmp_hasil, FILE_HASIL)
            
            # Pemicu Tracker Evaluasi Akurasi Prediksi AI 9 Rumus
            try:
                import tracker_ai
                tot_baru = tracker_ai.catat_rekomendasi_per_jam(df_hasil, timestamp=now)
                tot_eval = tracker_ai.evaluasi_akurasi_rekomendasi(df_hasil)
                print(f"🎯 [Tracker AI] Berhasil mencatat {tot_baru} rekomendasi baru & mengevaluasi {tot_eval} saham T+1.")
            except Exception as e_track:
                print(f"⚠️ Gagal memperbarui Tracker AI: {e_track}")
            
            # 2. LOGIKA JAM & HARI PINTAR (DENGAN DEDUPLIKASI TIMESTAMP)
            hari_ini = now.weekday() # 0 = Senin, 1=Selasa ... 4=Jumat
            
            # Jika hari kerja (Senin-Jumat) DAN antara jam 09:00 - 17:00
            if hari_ini < 5 and 9 <= jam_sekarang < 17:
                # Simpan Backup Harian dengan deduplikasi agar file tidak membengkak puluhan MB
                if os.path.isfile(file_arsip_harian):
                    try:
                        df_lama = pd.read_csv(file_arsip_harian)
                        df_gabung = pd.concat([df_lama, df_hasil], ignore_index=True)
                        if "Ticker" in df_gabung.columns and "Waktu Update" in df_gabung.columns:
                            df_gabung = df_gabung.drop_duplicates(subset=["Ticker", "Waktu Update"], keep="last")
                    except Exception:
                        df_gabung = df_hasil
                else:
                    df_gabung = df_hasil
                    
                tmp_arsip = f"{file_arsip_harian}.tmp"
                df_gabung.to_csv(tmp_arsip, index=False)
                os.replace(tmp_arsip, file_arsip_harian)
                
                print(f"✅ Selesai! Data Web diperbarui & Diarsipkan ke {file_arsip_harian} (Dedup Mode).")
                
            # Jika hari Sabtu atau Minggu
            elif hari_ini >= 5:
                print(f"✅ Selesai! Data Web diperbarui. (Mode Akhir Pekan 🏖️: Pengarsipan Dimatikan).")
            # Jika di luar jam bursa
            else:
                print(f"✅ Selesai! Data Web diperbarui. (Mode Malam 🌙: Pengarsipan dinonaktifkan).")
    finally:
        if os.path.exists(LOCK_FILE): os.remove(LOCK_FILE)
        
        # --- ROBOT PEMBERSIH ARSIP OTOMATIS ---
        import glob
        try:
            arsip_files = glob.glob(os.path.join(DIR_ARSIP, "screener_*.csv"))
            if len(arsip_files) > 5: # <-- UBAH JADI 5 (Maksimal 5 hari)
                # Urutkan dari yang paling baru ke paling lama
                arsip_files.sort(reverse=True)
                # Ambil file ke-6 dan seterusnya untuk dihapus
                file_usang = arsip_files[5:] # <-- UBAH JADI 5
                for f in file_usang:
                    os.remove(f)
                    print(f"🗑️ Membersihkan arsip lama: {f}")
        except Exception as e:
            pass

if __name__ == "__main__":
    main()