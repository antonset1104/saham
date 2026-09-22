try:
    import truststore
    truststore.inject_into_ssl()
except Exception:
    pass

import io
import sys
import subprocess
import streamlit as st
import pandas as pd
import numpy as np
import os
import json
import glob
import time
import re
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# IMPORT UNTUK AI OPENROUTER & GOOGLE
from openai import OpenAI
import google.generativeai as genai
from mesin_ai import get_historical_summary, get_forensic_data
import plotly.graph_objects as go
from data_multi_aset import (
    calculate_multi_asset_summary, load_multi_asset_portfolio,
    save_multi_asset_portfolio, get_usd_idr_rate, get_gold_price_idr,
    ASSET_CLASS_LABELS
)
from mesin_forecast import run_stock_forecast
from notifikasi_telegram import is_telegram_configured, kirim_pesan_telegram, kirim_ringkasan_pasar
import tracker_ai
import scheduler_per_jam

# ==========================================
# 🔑 HELPER PENGAMBIL SECRET / API KEY FLEKSIBEL
# ==========================================
def get_secret(key_name, default=None):
    """Mengambil API key/secret secara aman dari session state, st.secrets, os.environ, atau .env"""
    # 1. Coba dari session state jika diinput via UI
    if f"custom_{key_name}" in st.session_state and st.session_state[f"custom_{key_name}"]:
        return str(st.session_state[f"custom_{key_name}"]).strip()

    # 2. Coba dari st.secrets (defensif terhadap StreamlitSecretNotFoundError)
    try:
        if hasattr(st, "secrets"):
            val = st.secrets.get(key_name)
            if val:
                return str(val).strip()
    except Exception:
        pass

    # 3. Coba dari Environment Variable / file .env
    env_val = os.getenv(key_name) or os.environ.get(key_name)
    if env_val:
        return str(env_val).strip()

    return default

# ==========================================
# 🧠 FUNGSI HAKIM AI (KLASEMEN GLOBAL DENGAN RADAR & MODE JSON)
# ==========================================
def ai_hakim_klasemen(data_top15, api_key):
    import google.generativeai as genai
    import time
    genai.configure(api_key=api_key)
    
    # Prompt kita buat jauh lebih sederhana karena AI sudah dipaksa jadi mesin JSON
    prompt = f"""
    Select EXACTLY 5 Tickers that have the highest combination of 'Score' and 'Volume' from the data below.
    Calculate 'Target_TP' (+5% from Harga) and 'Target_CL' (-3% from Harga).
    
    DATA:
    {data_top15}
    
    Output a JSON array containing objects with EXACTLY 3 keys: "Ticker", "Target_TP", "Target_CL".
    """
    
    daftar_model_aktif = []
    try:
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                nama_bersih = m.name.replace("models/", "")
                # Prioritaskan model gemini-1.5 karena mendukung fitur JSON murni
                if "1.5" in nama_bersih:
                    daftar_model_aktif.insert(0, nama_bersih)
                else:
                    daftar_model_aktif.append(nama_bersih)
    except Exception as e:
        return f"Error_AI (Gagal menyalakan radar): {e}"

    if not daftar_model_aktif:
        return "Error_AI: Tidak ada satupun model Gemini yang online untuk API Key ini."

    pesan_error_terakhir = ""
    for nama_model in daftar_model_aktif:
        try:
            # ========================================================
            # 🔇 FITUR LAKBAN: Memaksa AI HANYA membalas JSON murni
            # ========================================================
            model = genai.GenerativeModel(
                nama_model,
                generation_config=genai.types.GenerationConfig(
                    temperature=0.0, 
                    response_mime_type="application/json" # <--- INI FITUR AJAIBNYA!
                )
            )
            response = model.generate_content(prompt)
            return response.text
        except Exception as e:
            pesan_error_terakhir = str(e)
            time.sleep(1) 
            continue 
            
    return f"Error_AI (Semua model aktif gagal eksekusi): {pesan_error_terakhir}"

# ==========================================
# 🤖 OTAK KECERDASAN BUATAN (OPENROUTER)
# ==========================================

# AI BANDAR (V6)
def analisa_bandar_ai_multisaham(data_saham_dict, pilihan_ai):
    OPENROUTER_API_KEY = get_secret("OPENROUTER_API_KEY")
    if not OPENROUTER_API_KEY: return "❌ Kunci API OpenRouter belum dipasang!"

    model_andalan = "openrouter/free" 

    try:
        client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=OPENROUTER_API_KEY)
        
        payload_text = ""
        for ticker, data in data_saham_dict.items():
            payload_text += f"\n--- STOCK: {ticker} ---\n"
            payload_text += f"Current Price: Rp {data['harga']}\n"
            payload_text += f"Today's Change: {data['change']}%\n"
            payload_text += f"Broker Summary: {data['broksum']}\n"
            payload_text += f"Wyckoff Phase: {data['status']}\n"
            payload_text += f"Technical Score: {data['skor']}/10\n"
            payload_text += f"Historical Trace (Daily):\n{data['histori']}\n"

        prompt = f"""
        You are the mastermind of an elite Indonesian stock market syndicate (Mega Bandar). 
        Your specialty is 'Gorengan' (highly volatile) stocks. You DO NOT buy stocks that have already pumped today. You look for "Stealth Accumulation"—stocks that are currently sideways or slightly up (Change is <= 5%), but have massive hidden accumulation in the historical intraday data, indicating they are ready to EXPLODE to top gainers tomorrow.

        I have filtered and provided {len(data_saham_dict)} candidate stocks that haven't pumped yet today.

        YOUR TASK:
        Analyze the 'Historical Trace' and 'Broker Summary' carefully. Select ONLY THE TOP 5 STOCKS that have completed their stealth accumulation phase today (by 15:00) and are 100% ready for a massive Mark-Up tomorrow morning (BSJP strategy).

        STOCK DATA TO ANALYZE:
        {payload_text}

        STRICT RULES:
        1. OUTPUT LANGUAGE: MUST be in Indonesian.
        2. DO NOT list all stocks. ONLY output your Top 5 selections.
        3. Create a Markdown table: [Peringkat, Ticker, Skor Ledakan (0-100%), Status Saat Ini].
        4. Below the table, provide a brutally analytical explanation for each stock. Prove why the pump is imminent by citing specific anomalies from the 'Historical Trace' and 'Broker Summary'.
        5. Provide a realistic Trading Plan (Buy Area near Current Price, Target Price for a massive pump >10%, and a tight Cut Loss). 
        6. Act like a ruthless market maker. No pleasantries. Start immediately with the table.
        """
        completion = client.chat.completions.create(
            model=model_andalan, messages=[{"role": "user", "content": prompt}],
            temperature=0.3, max_tokens=3000, top_p=1, stream=False,
        )
        
        hasil_mentah = completion.choices[0].message.content
        model_terpakai = completion.model
        
        if not hasil_mentah:
            return f"⚠️ Server AI (Model: {model_terpakai}) gagal memberikan jawaban. Silakan coba lagi."
            
        return hasil_mentah + f"\n\n---\n⚡ *Dianalisa otomatis menggunakan mesin: **{model_terpakai}** via OpenRouter*"
    except Exception as e: return f"❌ Gagal memproses data dengan OpenRouter menggunakan auto-model. Error: {e}"

# AI FORENSIK BANDAR (V7)
def analisa_forensik_ai(data_saham_dict, master_filters_keys):
    OPENROUTER_API_KEY = get_secret("OPENROUTER_API_KEY")
    if not OPENROUTER_API_KEY: return "❌ Kunci API OpenRouter belum dipasang!"

    model_andalan = "openrouter/free" 

    try:
        client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=OPENROUTER_API_KEY)
        payload_text = ""
        for ticker, data in data_saham_dict.items():
            payload_text += f"\n--- STOCK: {ticker} ---\n"
            payload_text += f"Broker Summary (Hari H): {data['broksum']}\n"
            payload_text += f"{data['histori']}\n"

        prompt = f"""
        You are a legendary Quantitative Analyst and Stock Market Forensic Expert in Indonesia.
        I am giving you the historical data of {len(data_saham_dict)} stocks from EXACTLY 1 TO 3 DAYS BEFORE they skyrocketed to Top Gainers / ARA (>10%). This is their condition BEFORE the pump.

        YOUR OBJECTIVE:
        1. Reverse engineer the 'Bandar' strategy. Find the exact common "DNA" or hidden patterns that occurred in these stocks during the 3 days BEFORE they exploded, including their Broker Summary activity.
        2. Cross-reference your findings with the EXISTING WEB FILTERS in my application.
        3. Suggest new metrics if my existing filters are missing the secret sauce.

        DATA STOCKS (H-3 to H-1 before pump):
        {payload_text}

        MY EXISTING WEB FILTERS (Categories you can use):
        {master_filters_keys}

        STRICT RULES:
        1. OUTPUT LANGUAGE: MUST be in Indonesian.
        2. Format your response into 3 sections using Markdown:
           - "### 🧬 DNA & Pola Tersembunyi Sebelum Ledakan": Explain exactly what similarities these stocks shared (e.g., "Ketiga saham ini mengalami penurunan harga, namun OBV terus naik dan volume ditahan...").
           - "### 🎛️ Resep Filter Web Saat Ini": Tell me EXACTLY how to set my existing filters (based on the provided list) to catch this pattern tomorrow.
           - "### 💡 Rekomendasi Rumus/Kategori Baru": If there is a pattern not covered by my filters, explicitly suggest what new filter/indicator I should code into my web application.
        3. Be highly analytical, specific, and brutally honest. Do not hallucinate.
        """
        completion = client.chat.completions.create(
            model=model_andalan, messages=[{"role": "user", "content": prompt}],
            temperature=0.2, max_tokens=3000, top_p=1, stream=False,
        )
        
        hasil_mentah = completion.choices[0].message.content
        model_terpakai = completion.model
        
        if not hasil_mentah:
            return f"⚠️ Server AI (Model: {model_terpakai}) gagal memberikan jawaban. Silakan coba lagi."
            
        return hasil_mentah + f"\n\n---\n🔬 *Lab Forensik AI menggunakan: **{model_terpakai}** via OpenRouter*"
    except Exception as e: return f"❌ Gagal memproses data dengan OpenRouter. Error: {e}"

def ai_penyisihan_turnamen(data_grup_dict, api_key):
    saham_grup_ini = list(data_grup_dict.keys())
    daftar_model_estafet = [
        'gemini-2.0-flash', 
        'gemini-1.5-flash',
        'gemini-1.5-flash-8b',
        'gemini-1.5-pro'
    ]
    genai.configure(api_key=api_key)
    payload_text = ""
    for ticker, data in data_grup_dict.items():
        payload_text += f"\n- {ticker}: Harga {data['harga']}, Vol {data['volume']}, Tekanan {data['tekanan_bandar']}, Supply {data['supply']}"
        
    prompt = f"""
    Act as a simple data sorter for a mathematical simulation.
    Here is a list of items and their stats:
    {payload_text}
    
    Your ONLY task is to pick the 3 best items based on Volume and Tekanan. 
    Even if all data is bad, you MUST pick exactly 3.
    Output ONLY a comma-separated list of the 3 items (e.g., BBCA,GOTO,PANI).
    DO NOT add any conversational text or markdown.
    """
    
    for nama_model in daftar_model_estafet:
        try:
            model = genai.GenerativeModel(nama_model)
            response = model.generate_content(prompt)
            raw_content = response.text.upper()
            
            semua_kata = re.findall(r'[A-Z]+', raw_content)
            lolos = []
            for kata in semua_kata:
                if kata in saham_grup_ini and kata not in lolos:
                    lolos.append(kata)
            
            if len(lolos) == 0:
                lolos = saham_grup_ini[:3]
                
            lolos_final = lolos[:3]
            return ",".join(lolos_final)
            
        except Exception as e:
            time.sleep(2)
            continue
            
    return ",".join(saham_grup_ini[:3])


def ai_grand_final_top5(data_saham_dict, api_key):
    import json
    daftar_model_estafet = [
        'gemini-2.0-flash', 
        'gemini-1.5-flash',
        'gemini-1.5-flash-8b',
        'gemini-1.5-pro'
    ]
    genai.configure(api_key=api_key)
    
    payload_text = ""
    for ticker, data in data_saham_dict.items():
        payload_text += f"\n--- {ticker} ---\n Harga: {data['harga']} | Vol: {data['volume']} | Broksum: {data['broksum']} | Tekanan: {data['tekanan_bandar']} | Supply: {data['supply']} | OBV: {data['obv']} | Fibo: {data['fibo']} | VWAP: {data['vwap']} | Candle: {data['pola_candle']}\n"

    prompt = f"""
    Act as an objective data formatting tool for a hypothetical academic simulation. THIS DOES NOT CONSTITUTE FINANCIAL ADVICE.
    Evaluate these fictionalized mathematical metrics:
    
    {payload_text}
    
    MISSION: Select EXACTLY 5 items that show the strongest theoretical accumulation score. Provide a theoretical 'Target_TP' and 'Target_CL' purely for simulation testing.
    
    CRITICAL INSTRUCTION: You are an automated JSON API endpoint. 
    You MUST output ONLY a raw, valid JSON array.
    DO NOT output any safety warnings, disclaimers, explanations, or conversational text.
    DO NOT wrap your response in markdown code blocks (DO NOT use ```json or ```).
    Your response must start exactly with '[' and end exactly with ']'.
    
    VERY IMPORTANT: The text inside the "Alasan" key MUST be written in fluent Bahasa Indonesia.
    
    Format EXACTLY like this:
    [
      {{"Peringkat": 1, "Ticker": "GOTO", "Alasan": "Akumulasi volume sangat tinggi dengan tekanan beli dominan", "Target_TP": 60, "Target_CL": 50}}
    ]
    """
    
    for nama_model in daftar_model_estafet:
        try:
            model = genai.GenerativeModel(nama_model)
            response = model.generate_content(prompt)
            raw_content = response.text or ""
            
            clean_content = raw_content.replace('```json', '').replace('```', '').strip()
            return clean_content, nama_model
            
        except Exception as e:
            time.sleep(3)
            continue
            
    raise Exception("🚨 KRITIS: Semua 7 model AI Gemini sedang mengalami limit maksimal atau server sibuk. Mohon jeda turnamen 1-2 menit sebelum mencoba lagi.")

# ==========================================
# PENGATURAN UI/UX & API
# ==========================================
st.set_page_config(page_title="Screener Saham IHSG", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800&display=swap');
    html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
    .stDataFrame { border-radius: 12px; overflow: hidden; box-shadow: 0 4px 10px rgba(0,0,0,0.15); }
    h1 { font-weight: 800; background: -webkit-linear-gradient(#38bdf8, #3b82f6); -webkit-background-clip: text; -webkit-text-fill-color: transparent; padding-bottom: 10px; }
    .metric-container { border-radius: 10px; padding: 15px; text-align: center; border: 1px solid #334155; background-color: #1e293b; color: #f8fafc; margin-bottom: 20px; }
    .bandar-box { border-left: 5px solid #ef4444; background-color: #2a1111; padding: 15px; border-radius: 8px; margin-bottom: 15px; }
    .bandar-box-green { border-left: 5px solid #22c55e; background-color: #0f291e; padding: 15px; border-radius: 8px; margin-bottom: 15px; }
    .stTabs [data-baseweb="tab-list"] { gap: 24px; }
    .stTabs [data-baseweb="tab"] { height: 50px; font-weight: 600; }
    .view-mode-container { background-color: #0f172a; padding: 10px 20px; border-radius: 8px; margin-bottom: 15px; border: 1px solid #334155; }
    @keyframes pulse-radar {
        0% { box-shadow: 0 0 0 0 rgba(6, 182, 212, 0.7); border-color: #06b6d4; }
        50% { box-shadow: 0 0 0 12px rgba(6, 182, 212, 0); border-color: #38bdf8; }
        100% { box-shadow: 0 0 0 0 rgba(6, 182, 212, 0); border-color: #06b6d4; }
    }
    @keyframes spin-slow {
        0% { transform: rotate(0deg); }
        100% { transform: rotate(360deg); }
    }
    .update-anim-box {
        border: 2px solid #06b6d4;
        background: linear-gradient(135deg, #082f49 0%, #0f172a 100%);
        border-radius: 10px;
        padding: 16px;
        margin-bottom: 15px;
        text-align: center;
        animation: pulse-radar 2s infinite;
    }
    .radar-icon {
        display: inline-block;
        font-size: 28px;
        animation: spin-slow 3s linear infinite;
        margin-bottom: 6px;
    }
    </style>
""", unsafe_allow_html=True)

# ==========================================
# LOAD KONFIGURASI JSON
# ==========================================
FILE_CONFIG = "config_web.json"
FILE_PRESET = "preset_kustom.json"
FILE_HASIL = "Database/hasil_screener.csv"
FILE_AKUISISI = "Database/data_akuisisi.csv"

DEFAULT_CONFIG = {
    "MASTER_FILTERS": {
        "Kategori": {"label": "🏢 Kategori Saham", "options": ["Semua", "Big Cap (Lapis 1)", "Mid Cap (Lapis 2)", "Small Cap (Lapis 3)", "Mid Cap (Lapis 2) + Small Cap (Lapis 3)"]},
        "Status Open": {"label": "🌅 Sinyal Open", "options": ["Semua", "Open = Low (Bullish Kuat)", "Open = High (Tekanan Jual)", "Normal"]},
        "Risk/Reward Ratio": {"label": "⚖️ Risk/Reward", "options": ["Semua", "Sangat Menarik (> 1:3)", "Ideal (1:2)", "Menengah (1:1)", "Tidak Ideal (< 1:1)", "Di Area Support"]},
        "Kelas Transaksi": {"label": "💸 Kelas Transaksi", "options": ["Semua", "Sultan (> 50M/hari)", "Ritel Aktif (5M - 50M)", "Gorengan Sepi (< 5M)"]},
        "Sinyal Cuci Barang": {"label": "🧹 Sinyal Shakeout", "options": ["Semua", "Jarum Bawah (Sinyal Pantulan Kuat)", "Normal"]},
        "Valuasi": {"label": "💎 Valuasi Fundamental", "options": ["Semua", "Undervalued (Murah)", "Fair Value (Wajar)", "Overvalued (Mahal)"]},
        "Posisi VWAP": {"label": "⚖️ Posisi thd VWAP", "options": ["Semua", "Di Atas VWAP (Kuat)", "Di Bawah VWAP (Lemah)", "Persis di VWAP"]},
        "Fase Siklus Bandar": {"label": "🔄 Siklus Wyckoff", "options": ["Semua", "Accumulation (Kumpul Barang)", "Mark-Up (Fase Pesta)", "Distribution (Fase Jualan)", "Mark-Down (Fase Runtuh)", "Sideways"]},
        "RVOL (Anomali Vol)": {"label": "🌋 Ledakan Volume", "options": ["Semua", "Ledakan Ekstrem (> 300%)", "Anomali Tinggi (150-300%)", "Normal (50-150%)", "Sepi (< 50%)"]},
        "Karakter Gorengan": {"label": "🕵️ Karakter Saham", "options": ["Semua", "Spesialis Tiang Jemuran (Banting Pucuk)", "Solid (Jarang Dibanting)", "Normal"]},
        "Status Bandar": {"label": "🕵️ Status Bandar", "options": ["Semua", "Akumulasi Kuat", "Distribusi Kuat", "Normal"]},
        "Tekanan Bandar": {"label": "⚔️ Tekanan Harian", "options": ["Semua", "Dominan Beli (Hajar Kanan)", "Dominan Jual (Guyur)", "Seimbang / Adu Mekanik"]},
        "Kekuatan A/D": {"label": "🧠 Smart Money (A/D)", "options": ["Semua", "Akumulasi Pro (Smart Money)", "Distribusi Pro (Guyuran)", "Netral"]},
        "OBV Trend": {"label": "🌊 Tren Uang (OBV)", "options": ["Semua", "Akumulasi (Naik)", "Distribusi (Turun)", "Netral"]},
        "Pola Candle": {"label": "🕯️ Price Action", "options": ["Semua", "Marubozu (Strong Bullish)", "Hammer (Potensi Reversal)", "Doji (Ragu-ragu)", "Normal"]},
        "Posisi Entry": {"label": "🎯 Jarak ke Support", "options": ["Semua", "Dekat Support (Low Risk)", "Area Tengah", "Rawan Pucuk (High Risk)"]},
        "Vol Breakout": {"label": "🔊 Volume", "options": ["Semua", "Tembus MA20", "Normal"]},
        "RSI (14D)": {"label": "📊 RSI (14D)", "options": ["Semua", "> 50 (Bullish)", "<= 50 (Bearish)"]},
        "MA Signal": {"label": "📈 Tren (MA20)", "options": ["Semua", "Uptrend", "Downtrend"]},
        "Momentum": {"label": "⚡ Momentum", "options": ["Semua", "Positif", "Negatif"]},
        "Total Score": {"label": "⭐ Total Score", "options": ["Semua", 10, 9, 8, 7, 6, 5, 4, 3, 2, 1, 0]},
        "Rekomendasi": {"label": "🎯 Rekomendasi", "options": ["Semua", "BELI", "WAIT & SEE"]},
        "Likuiditas": {"label": "💧 Likuiditas", "options": ["Semua", "> 1 Miliar", "< 1 Miliar"]},
        "Status BB": {"label": "🌐 Bollinger Bands", "options": ["Semua", "Squeeze", "Bottom Rebound", "Breakout Upper", "Normal"]},
        "MA Cross": {"label": "🔀 MA Cross (5/20)", "options": ["Semua", "Golden Cross", "Bullish", "Death Cross", "Bearish"]},
        "Risiko": {"label": "⚠️ Risiko Volatilitas", "options": ["Semua", "Tinggi", "Sedang", "Rendah"]},
        "Status Akuisisi": {"label": "🤝 Sentimen Akuisisi", "options": ["Semua", "TIDAK ADA", "RENCANA AKUISISI", "DALAM AKUISISI"]},
        "MACD": {"label": "📈 MACD", "options": ["Semua", "Strong Bullish", "Bullish MACD", "Strong Bearish", "Bearish MACD"]},
        "Status Stochastic": {"label": "🌊 Stochastic", "options": ["Semua", "Oversold (Jenuh Jual - Peluang)", "Golden Cross (Awal Bullish)", "Overbought (Jenuh Beli - Rawan)", "Death Cross (Awal Bearish)", "Netral / Sideways"]},
        "Status Sentimen": {"label": "📰 Sentimen Berita", "options": ["Semua", "Sentimen Positif 📰", "Sentimen Negatif ⚠️", "Netral / Sepi Berita"]},
        "Prediksi Machine Learning": {"label": "🧠 AI Machine Learning", "options": ["Semua", "🔥 ANOMALI BANDAR (Siap Ledakan)", "⚠️ Anomali (Sudah Terbang)", "Biasa / Mengikuti Pasar"]},
        "Kondisi Supply": {"label": "🏜️ Supply & Demand", "options": ["Semua", "Supply Kering (Siap Pump) 🏜️", "Supply Banjir (Distribusi) 🌊", "Normal / Sedang Transisi"]},
        "Status Fibonacci": {"label": "📏 Level Fibonacci", "options": ["Semua", "Golden Rebound Fibo 61.8% (Golden Ratio) 🎯", "Dekat Support Fibo 61.8% (Golden Ratio)", "Golden Rebound Fibo 50.0% 🎯", "Golden Rebound Fibo 38.2% 🎯", "Mengambang (Jauh dari Fibo)"]}
    }
}

if not os.path.exists(FILE_CONFIG):
    with open(FILE_CONFIG, "w") as f: json.dump(DEFAULT_CONFIG, f, indent=4)
else:
    with open(FILE_CONFIG, "r") as f: cek_config = json.load(f)
    if "Status Fibonacci" not in cek_config.get("MASTER_FILTERS", {}):
        with open(FILE_CONFIG, "w") as f: json.dump(DEFAULT_CONFIG, f, indent=4)

with open(FILE_CONFIG, "r") as f: WEB_CONFIG = json.load(f)

# Auto-patch
if "Mid Cap (Lapis 2) + Small Cap (Lapis 3)" not in WEB_CONFIG["MASTER_FILTERS"]["Kategori"]["options"]:
    WEB_CONFIG["MASTER_FILTERS"]["Kategori"]["options"] = ["Semua", "Big Cap (Lapis 1)", "Mid Cap (Lapis 2)", "Small Cap (Lapis 3)", "Mid Cap (Lapis 2) + Small Cap (Lapis 3)"]
    with open(FILE_CONFIG, "w") as f: json.dump(WEB_CONFIG, f, indent=4)

MASTER_FILTERS = WEB_CONFIG["MASTER_FILTERS"]

# ==========================================
# DATABASE PRESET & LOAD DATA
# ==========================================
def muat_preset():
    preset_bawaan = {
        "🌙 BSJP (Beli Sore 15:30)": {k: "Semua" for k in MASTER_FILTERS},
        "⚡ HAKA Sesi Pagi (Open=Low)": {k: "Semua" for k in MASTER_FILTERS},
        "🚀 Gorengan Aktif (High Risk)": {k: "Semua" for k in MASTER_FILTERS},
        "🎣 Pantulan Reversal Emas": {k: "Semua" for k in MASTER_FILTERS},
        "🔥 Bluechip Terakumulasi": {k: "Semua" for k in MASTER_FILTERS}
    }
    preset_bawaan["🌙 BSJP (Beli Sore 15:30)"].update({"Tekanan Bandar": "Dominan Beli (Hajar Kanan)", "Karakter Gorengan": "Solid (Jarang Dibanting)", "Status Bandar": "Akumulasi Kuat", "MA Signal": "Uptrend", "Rekomendasi": "BELI"})
    preset_bawaan["⚡ HAKA Sesi Pagi (Open=Low)"].update({"Status Open": "Open = Low (Bullish Kuat)", "Risk/Reward Ratio": "Sangat Menarik (> 1:3)"})
    preset_bawaan["🚀 Gorengan Aktif (High Risk)"].update({"Kategori": "Small Cap (Lapis 3)", "RVOL (Anomali Vol)": "Ledakan Ekstrem (> 300%)", "Posisi VWAP": "Di Atas VWAP (Kuat)"})
    preset_bawaan["🎣 Pantulan Reversal Emas"].update({"Sinyal Cuci Barang": "Jarum Bawah (Sinyal Pantulan Kuat)", "Kekuatan A/D": "Akumulasi Pro (Smart Money)"})
    preset_bawaan["🔥 Bluechip Terakumulasi"].update({"Status Bandar": "Akumulasi Kuat", "Kategori": "Big Cap (Lapis 1)", "MA Signal": "Uptrend"})

    if os.path.exists(FILE_PRESET):
        try:
            with open(FILE_PRESET, "r") as f: preset_bawaan.update(json.load(f))
        except: pass
    return preset_bawaan

daftar_preset_aktif = muat_preset()
if "preset_selector" not in st.session_state: st.session_state.preset_selector = "Matikan Preset (Manual)"

def apply_preset():
    if st.session_state.preset_selector != "Matikan Preset (Manual)":
        for k, v in daftar_preset_aktif[st.session_state.preset_selector].items():
            if k in MASTER_FILTERS: st.session_state[f"main_{k}"] = v

def manual_override(): st.session_state.preset_selector = "Matikan Preset (Manual)"

@st.cache_data(ttl=10)
def load_data_saham():
    if not os.path.exists(FILE_HASIL): return pd.DataFrame()
    try:
        df = pd.read_csv(FILE_HASIL)
    except Exception:
        return pd.DataFrame()
        
    if os.path.exists(FILE_AKUISISI):
        try:
            df_akuisisi = pd.read_csv(FILE_AKUISISI)
            if "Status Akuisisi" in df.columns: df = df.drop(columns=["Status Akuisisi"])
            df = pd.merge(df, df_akuisisi, on="Ticker", how="left")
            df["Status Akuisisi"] = df["Status Akuisisi"].fillna("TIDAK ADA")
        except Exception:
            df["Status Akuisisi"] = "TIDAK ADA"
    else: df["Status Akuisisi"] = "TIDAK ADA"
    return df

df_hasil = load_data_saham()

# --- TAMBAHAN KALKULASI VALUE TRANSAKSI OTOMATIS ---
if not df_hasil.empty and 'Volume' in df_hasil.columns and 'Harga (Rp)' in df_hasil.columns:
    # Volume dari Yahoo Finance untuk IDX sudah dalam satuan lembar saham
    df_hasil['Value Transaksi'] = df_hasil['Harga (Rp)'] * df_hasil['Volume']

# ==========================================
# HEADER & SIDEBAR
# ==========================================
if not df_hasil.empty and "Terakhir Update" in df_hasil.columns:
    waktu_update = str(df_hasil["Terakhir Update"].iloc[0]) + " WIB"
    st.sidebar.markdown(f"""
        <div style="border: 2px solid #06b6d4; padding: 10px; border-radius: 4px; text-align: center; margin-bottom: 15px; background-color: #0f172a; box-shadow: 0 4px 6px rgba(0,0,0,0.3);">
            <span style="font-size: 12px; color: #94a3b8; font-weight: 600;">Waktu Terakhir Update:</span><br>
            <strong style="color: #06b6d4; font-size: 14px;">{waktu_update}</strong>
        </div>
    """, unsafe_allow_html=True)

LOCK_UPDATE_FILE = "sedang_update.lock"
is_updating = os.path.exists(LOCK_UPDATE_FILE)

# Deteksi transisi: sebelumnya update aktif tapi lock file sudah dihapus -> BERHASIL SELESAI
if st.session_state.get("is_updating_saham") and not is_updating:
    st.session_state["is_updating_saham"] = False
    st.session_state["just_completed_update"] = True
    st.cache_data.clear()

if is_updating:
    st.session_state["is_updating_saham"] = True
    st.session_state["just_completed_update"] = False

# --- AUTO-TRIGGER KETIKA GANTI HARI & JAM BURSA AKTIF ---
now_dt = datetime.now()
tgl_sekarang_str = now_dt.strftime("%Y-%m-%d")
is_hari_bursa = now_dt.weekday() < 5 # Senin-Jumat (0-4)
is_jam_bursa = (now_dt.hour >= 9) and (now_dt.hour <= 16)

tgl_data_terakhir = None
if not df_hasil.empty and "Terakhir Update" in df_hasil.columns:
    try:
        raw_tgl = str(df_hasil["Terakhir Update"].iloc[0]).split()[0]
        tgl_data_terakhir = raw_tgl
    except:
        pass

perlu_update_hari_baru = (
    is_hari_bursa and 
    is_jam_bursa and 
    tgl_data_terakhir is not None and 
    tgl_data_terakhir < tgl_sekarang_str and 
    not is_updating and
    not st.session_state.get("auto_triggered_today")
)

if perlu_update_hari_baru:
    st.session_state["auto_triggered_today"] = True
    py_bin = sys.executable or "./.venv/bin/python"
    try:
        subprocess.Popen(
            [py_bin, "update_data.py"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True
        )
        st.session_state["is_updating_saham"] = True
        st.session_state["just_completed_update"] = False
        st.toast("🌅 Hari baru terdeteksi! Memulai sinkronisasi data IHSG hari ini...", icon="🚀")
        time.sleep(1)
        st.rerun()
    except Exception as err_auto:
        pass

# --- AUTO-SYNC MONITOR DATA BARU DI WEB (SETIAP 15 DETIK) ---
@st.fragment(run_every="15s")
def sync_otomatis_data_web():
    current_mtime = os.path.getmtime(FILE_HASIL) if os.path.exists(FILE_HASIL) else 0
    if "cached_file_mtime" not in st.session_state:
        st.session_state["cached_file_mtime"] = current_mtime
    elif current_mtime > st.session_state["cached_file_mtime"]:
        st.session_state["cached_file_mtime"] = current_mtime
        st.cache_data.clear()
        st.rerun(scope="app")

    # Pemicu otomatis kirim alert Telegram jika jam bursa (Pagi 10:00 & Sore 15:30)
    try:
        from notifikasi_telegram import is_telegram_configured, cek_dan_kirim_jadwal_1530, cek_dan_kirim_jadwal_1000
        if is_telegram_configured() and not df_hasil.empty:
            cek_dan_kirim_jadwal_1530(df_screener=df_hasil)
            cek_dan_kirim_jadwal_1000(df_screener=df_hasil)
    except Exception:
        pass

sync_otomatis_data_web()

with st.sidebar.expander("⚡ Update Data Pasar (Stockbit & Yahoo)", expanded=True):
    if is_updating:
        st.markdown("""
            <div class="update-anim-box">
                <div class="radar-icon">📡</div>
                <h4 style="margin:0; color:#38bdf8; font-size:14px; font-weight:700;">PROSES SEDANG BERJALAN</h4>
                <p style="margin:6px 0 0 0; color:#94a3b8; font-size:11px;">Menyedot data Stockbit, menghitung 45+ indikator, dan machine learning...</p>
            </div>
        """, unsafe_allow_html=True)
        st.caption("🔄 Halaman akan refresh otomatis hingga data selesai diproses.")
        
        # Reset darurat jika lock file tertinggal > 10 menit
        if os.path.exists(LOCK_UPDATE_FILE):
            lock_age = time.time() - os.path.getmtime(LOCK_UPDATE_FILE)
            if lock_age > 600:
                if st.button("⚠️ Batalkan / Hapus Kunci", use_container_width=True):
                    try: os.remove(LOCK_UPDATE_FILE)
                    except: pass
                    st.session_state["is_updating_saham"] = False
                    st.rerun()
    else:
        if st.session_state.get("just_completed_update"):
            st.success("✅ **Data Saham Selesai Diperbarui!**")
            
        mode_opsi = st.radio(
            "Cakupan Update:",
            ["Uji Cepat (15 Saham)", "Seluruh IHSG (900+ Saham)"],
            index=0,
            key="pilihan_mode_update"
        )

        with st.expander("🔑 Konfigurasi Token Stockbit", expanded=False):
            curr_sb_token = os.getenv("STOCKBIT_TOKEN", "")
            if not curr_sb_token and os.path.exists("token_stockbit.txt"):
                try:
                    with open("token_stockbit.txt", "r") as f:
                        curr_sb_token = f.read().strip()
                except Exception:
                    pass
            
            sb_token_input = st.text_input(
                "Stockbit Bearer Token:",
                value=curr_sb_token,
                type="password",
                placeholder="Paste token eyJhbGciOi...",
                help="Diambil dari Inspect Element (F12) -> Network -> Header Authorization di stockbit.com"
            )
            if st.button("💾 Simpan Token Stockbit", use_container_width=True, key="btn_save_sb_token"):
                clean_sb = sb_token_input.strip()
                if clean_sb.startswith("Bearer "):
                    clean_sb = clean_sb[7:].strip()
                
                try:
                    with open("token_stockbit.txt", "w") as f:
                        f.write(clean_sb)
                except Exception:
                    pass
                
                if os.path.exists(".env"):
                    try:
                        with open(".env", "r") as f:
                            env_lines = f.readlines()
                        new_env = []
                        sb_found = False
                        for l in env_lines:
                            if l.startswith("STOCKBIT_TOKEN="):
                                new_env.append(f"STOCKBIT_TOKEN={clean_sb}\n")
                                sb_found = True
                            else:
                                new_env.append(l)
                        if not sb_found:
                            new_env.append(f"STOCKBIT_TOKEN={clean_sb}\n")
                        with open(".env", "w") as f:
                            f.writelines(new_env)
                    except Exception:
                        pass
                
                os.environ["STOCKBIT_TOKEN"] = clean_sb
                st.success("Token Stockbit berhasil disimpan!")
                time.sleep(0.5)
                st.rerun()

        btn_run_update = st.button("🚀 Tarik Data Stockbit Sekarang", use_container_width=True, type="primary", key="btn_tarik_data_sb")
        if btn_run_update:
            py_bin = sys.executable or "./.venv/bin/python"
            cmd = [py_bin, "update_data.py"]
            if "15 Saham" in mode_opsi:
                cmd.extend(["--limit", "15"])
            
            try:
                # Jalankan skrip di background secara asinkron
                subprocess.Popen(
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True
                )
                st.session_state["is_updating_saham"] = True
                st.session_state["just_completed_update"] = False
                st.rerun()
            except Exception as err:
                st.error(f"Gagal memulai update: {err}")

col_sync1, col_sync2 = st.sidebar.columns(2)
with col_sync1:
    if st.button("🔄 Refresh Web", use_container_width=True, help="Bersihkan cache dan muat ulang database CSV lokal"):
        st.cache_data.clear()
        st.rerun()
with col_sync2:
    if st.button("🌐 Pull GitHub", use_container_width=True, help="Tarik perubahan data terbaru dari repository GitHub"):
        with st.spinner("Git pull..."):
            try:
                os.system("git pull origin main")
                time.sleep(1)
            except Exception as e:
                st.error(f"Error: {e}")
        st.cache_data.clear()
        st.rerun()

# --- KONTROL SCHEDULER OTOMATIS PER JAM ---
sched_status = scheduler_per_jam.get_scheduler_status()
is_sched_active = sched_status.get("is_running", False)

with st.sidebar.expander("🔁 Scheduler Otomatis Per Jam", expanded=is_sched_active):
    if is_sched_active:
        st.markdown("""
            <div style="background-color: #064e3b; border: 1px solid #10b981; border-radius: 6px; padding: 10px; text-align: center; margin-bottom: 10px;">
                <span style="color: #34d399; font-weight: 700; font-size: 13px;">🟢 STATUS: AKTIF BERJALAN</span><br>
                <span style="color: #a7f3d0; font-size: 11px;">Update seluruh IHSG otomatis setiap jam bursa</span>
            </div>
        """, unsafe_allow_html=True)
        st.caption(f"🕒 Terakhir Jalan: **{sched_status.get('last_run', '-')}**")
        st.caption(f"⏳ Jadwal Berikutnya: **{sched_status.get('next_run', '-')}**")
        st.caption(f"📝 Status: {sched_status.get('last_status', '-')}")
        if st.button("⏹️ Hentikan Scheduler", use_container_width=True, type="secondary", key="btn_stop_sched"):
            scheduler_per_jam.stop_scheduler_daemon()
            st.success("Scheduler dihentikan.")
            time.sleep(1)
            st.rerun()
    else:
        st.markdown("""
            <div style="background-color: #1e293b; border: 1px solid #475569; border-radius: 6px; padding: 10px; text-align: center; margin-bottom: 10px;">
                <span style="color: #94a3b8; font-weight: 700; font-size: 13px;">⚪ STATUS: NONAKTIF</span><br>
                <span style="color: #cbd5e1; font-size: 11px;">Otomatisasi per jam sedang mati</span>
            </div>
        """, unsafe_allow_html=True)
        st.caption("Pemicu pembaruan data seluruh IHSG setiap 1 jam pada jam perdagangan bursa IDX (09:00 - 16:00 WIB).")
        if st.button("▶️ Aktifkan Scheduler Per Jam", use_container_width=True, type="primary", key="btn_start_sched"):
            sukses, msg = scheduler_per_jam.start_scheduler_daemon()
            if sukses:
                st.success(msg)
            else:
                st.info(msg)
            time.sleep(1)
            st.rerun()

st.sidebar.title("⚙️ Preset Filter Cepat")
st.sidebar.info("Gunakan **'BSJP (Beli Sore 15:30)'** untuk mencari saham yang mantap dibeli sebelum penutupan bursa!")

opsi_preset = ["Matikan Preset (Manual)"] + list(daftar_preset_aktif.keys())
idx_default = opsi_preset.index(st.session_state.preset_selector) if st.session_state.preset_selector in opsi_preset else 0
st.sidebar.selectbox("📌 Pilih Preset Aktif:", opsi_preset, index=idx_default, key="preset_selector", on_change=apply_preset)

kustom_presets = {}
if os.path.exists(FILE_PRESET):
    try:
        with open(FILE_PRESET, "r") as f: kustom_presets = json.load(f)
    except: pass

with st.sidebar.expander("🛠️ Manajemen Preset Kustom"):
    tab_edit, tab_hapus = st.tabs(["📝 Buat/Edit", "🗑️ Hapus"])
    with tab_edit:
        opsi_edit = ["-- Buat Baru --"] + list(kustom_presets.keys())
        pilih_edit = st.selectbox("Pilih Preset:", opsi_edit, key="select_edit")
        if pilih_edit == "-- Buat Baru --":
            nama_preset_baru = st.text_input("Nama Preset Baru:", placeholder="Contoh: Strategi X", key="nama_baru")
            nilai_awal = {k: info['options'][0] for k, info in MASTER_FILTERS.items()}
        else:
            nama_preset_baru = st.text_input("Simpan sebagai:", value=pilih_edit, key="nama_edit")
            nilai_awal = kustom_presets[pilih_edit]

        kustom_input = {}
        for k, info in MASTER_FILTERS.items():
            val_awal = nilai_awal.get(k, info['options'][0])
            idx_awal = info['options'].index(val_awal) if val_awal in info['options'] else 0
            kustom_input[k] = st.selectbox(f"P-{info['label']}", info['options'], index=idx_awal, key=f"edit_{k}")

        if st.button("💾 Simpan Preset"):
            if nama_preset_baru.strip():
                if pilih_edit != "-- Buat Baru --" and pilih_edit != nama_preset_baru.strip(): del kustom_presets[pilih_edit]
                kustom_presets[nama_preset_baru.strip()] = kustom_input
                with open(FILE_PRESET, "w") as f: json.dump(kustom_presets, f, indent=4)
                st.session_state.preset_selector = nama_preset_baru.strip()
                st.success("Preset berhasil disimpan!")
                st.rerun()
    with tab_hapus:
        if kustom_presets:
            pilih_hapus = st.selectbox("Pilih Preset untuk Dihapus:", list(kustom_presets.keys()))
            if st.button("🗑️ Hapus Preset"):
                del kustom_presets[pilih_hapus]
                with open(FILE_PRESET, "w") as f: json.dump(kustom_presets, f, indent=4)
                if st.session_state.preset_selector == pilih_hapus: st.session_state.preset_selector = "Matikan Preset (Manual)"
                st.success("Preset dihapus!")
                st.rerun()
        else: st.info("Belum ada preset kustom.")

with st.sidebar.expander("📲 Notifikasi Telegram Bot"):
    from notifikasi_telegram import get_telegram_config, simpan_konfigurasi_telegram
    tok_curr, cid_curr = get_telegram_config()
    is_cfg = is_telegram_configured()
    
    if is_cfg:
        st.success("✅ Bot Telegram Terhubung")
    else:
        st.info("💡 Hubungkan Telegram untuk menerima alert real-time ke Android.")
        
    input_token = st.text_input("Bot Token:", value=tok_curr, type="password", placeholder="Contoh: 123456:ABC-DEF...", help="Dapatkan dari @BotFather di aplikasi Telegram Android")
    input_cid = st.text_input("Chat ID:", value=cid_curr, placeholder="Contoh: 123456789", help="Dapatkan dari @userinfobot di aplikasi Telegram Android")
    
    col_tg1, col_tg2 = st.columns(2)
    with col_tg1:
        if st.button("💾 Simpan", use_container_width=True, key="btn_save_tg_config"):
            if input_token.strip() and input_cid.strip():
                if simpan_konfigurasi_telegram(input_token.strip(), input_cid.strip()):
                    st.success("Tersimpan!")
                    time.sleep(0.5)
                    st.rerun()
                else:
                    st.error("Gagal simpan ke .env")
            else:
                st.warning("Isi Token & Chat ID!")
                
    with col_tg2:
        if st.button("🔔 Tes Kirim", use_container_width=True, key="btn_test_tg"):
            t_pakai = input_token.strip() or tok_curr
            c_pakai = input_cid.strip() or cid_curr
            if t_pakai and c_pakai:
                with st.spinner("Mengirim pesan tes..."):
                    berhasil = kirim_pesan_telegram(
                        "🔔 <b>Tes Notifikasi AlgoTrade Screener IHSG</b>\nKoneksi bot Telegram Anda aktif dan siap mengirim alert!",
                        token=t_pakai,
                        chat_id=c_pakai
                    )
                    if berhasil:
                        st.toast("Notifikasi Telegram terkirim ke Android!", icon="📲")
                        st.success("Pesan terkirim ke Telegram!")
                    else:
                        st.error("Gagal kirim. Pastikan sudah klik START di bot Anda.")
            else:
                st.warning("Konfigurasi belum lengkap.")
                
    if is_cfg:
        st.markdown("---")
        st.caption("⏰ **Jadwal BSJP Sore:** Otomatis dikirim ke Telegram setiap hari bursa pukul **15:30 WIB**.")
        from notifikasi_telegram import kirim_rekomendasi_rumus_2_dan_9, kirim_update_realtime_pagi_1000
        if st.button("🦅 Kirim Alert BSJP Sore Sekarang", use_container_width=True, key="btn_kirim_bsjp_manual"):
            with st.spinner("Menyaring saham Rumus 2 & 9..."):
                sukses_b, msg_b = kirim_rekomendasi_rumus_2_dan_9(df_screener=df_hasil, force=True)
                if sukses_b:
                    st.success("Rekomendasi terkirim ke Telegram!")
                    st.toast("Rekomendasi BSJP terkirim ke Telegram!", icon="🦅")
                else:
                    st.error(f"Gagal kirim: {msg_b}")

        st.caption("🌅 **Jadwal Evaluasi Pagi:** Otomatis dikirim ke Telegram setiap hari bursa pukul **10:00 WIB**.")
        if st.button("🌅 Kirim Update Realtime Pagi Sekarang", use_container_width=True, key="btn_kirim_pagi_manual"):
            with st.spinner("Memeriksa harga realtime saham BSJP..."):
                sukses_p, msg_p = kirim_update_realtime_pagi_1000(df_screener=df_hasil, force=True)
                if sukses_p:
                    st.success("Update realtime pagi terkirim ke Telegram!")
                    st.toast("Update realtime BSJP terkirim ke Telegram!", icon="🌅")
                else:
                    st.error(f"Gagal kirim: {msg_p}")

        st.caption("💎 **Jadwal Fundamental Super:** Otomatis dikirim ke Telegram setiap **Jumat pukul 20:00 WIB**.")
        from notifikasi_telegram import kirim_alert_screener_fundamental_jumat
        if st.button("💎 Analisa & Kirim Screener Jumat Sekarang", use_container_width=True, key="btn_kirim_jumat_manual"):
            with st.spinner("Menganalisis seluruh saham bursa dengan 12 kriteria fundamental Stockbit..."):
                sukses_j, msg_j = kirim_alert_screener_fundamental_jumat(force=True)
                if sukses_j:
                    st.success("Laporan fundamental Jumat terkirim ke Telegram!")
                    st.toast("Laporan Fundamental Jumat terkirim!", icon="💎")
                else:
                    st.error(f"Gagal: {msg_j}")

st.title("⚡ AlgoTrade Screener - IHSG Ultimate")
st.markdown("Detektor Jejak Bandar, Anomali Volume, & Strategi BSJP.")
st.markdown("---")

# ==========================================
# FUNGSI PEWARNAAN & FORMATTER TABEL
# ==========================================
def format_skor(s): return "⭐" * int(s) if pd.notna(s) and int(s) > 0 else "-"
def format_pct(v): return f"{'▲ ' if v > 0 else '▼ '}{v:+.2f}%" if pd.notna(v) and v != 0 else "0.00%"
def format_mom(v): return "▲ Positif" if v == "Positif" else ("▼ Negatif" if v == "Negatif" else v)
def format_desimal(v): return f"{v:.2f}" if pd.notna(v) and v != 0 else "-"
def format_angka(v): return f"{int(v):,}".replace(",", ".") if pd.notna(v) else "-"

def format_singkat_vol(v):
    if pd.isna(v): return "-"
    if v >= 1_000_000: return f"{v/1_000_000:.2f} M Lot"
    elif v >= 1_000: return f"{v/1_000:.2f} K Lot"
    return f"{v:.0f} Lot"

def format_singkat_rp(v):
    if pd.isna(v) or v == 0: return "-"
    if v >= 1_000_000_000_000: return f"🔥 Rp {v/1_000_000_000_000:.2f} T"
    elif v >= 1_000_000_000: return f"💰 Rp {v/1_000_000_000:.2f} M"
    elif v >= 1_000_000: return f"🪙 Rp {v/1_000_000:.2f} Jt"
    return f"Rp {v:,.0f}".replace(",", ".")

def warna_tabel(val):
    if isinstance(val, (int, float)): 
        return 'color: #22c55e; font-weight: 600;' if val > 0 else ('color: #ef4444; font-weight: 600;' if val < 0 else '')
    elif isinstance(val, str):
        if any(x in val for x in ["Positif", "Uptrend", "BELI", "Breakout Upper", "Bottom Rebound", "DALAM AKUISISI", "Rendah", "▲", "Golden Cross", "Bullish", "Tembus MA20", "Akumulasi", "Big Cap", "Gap Up", "Dominan Beli", "Undervalued", "Marubozu", "Dekat Support", "Hammer", "Di Atas VWAP", "Sultan", "Ledakan Ekstrem", "Solid", "Mark-Up", "Jarum Bawah", "Naik", "Open = Low", "Sangat Menarik", "Perfect Uptrend", "Awal Reversal", "Acc"]): return 'color: #22c55e; font-weight: 600;'
        elif any(x in val for x in ["Negatif", "Downtrend", "WAIT & SEE", "Tinggi", "▼", "Death Cross", "Bearish", "Distribusi", "Small Cap", "Gap Down", "Dominan Jual", "Overvalued", "Rawan Pucuk", "Di Bawah VWAP", "Gorengan Sepi", "Sepi", "Tiang Jemuran", "Mark-Down", "Turun", "Open = High", "Tidak Ideal", "Strong Downtrend", "Dist", "Token Mati", "Gagal", "Timeout"]): return 'color: #ef4444; font-weight: 600;'
        elif val == "> 1 Miliar": return 'color: #3b82f6; font-weight: 600;'
        elif any(x in val for x in ["Squeeze", "RENCANA AKUISISI", "Sedang", "Mid Cap", "Seimbang", "Fair Value", "Area Tengah", "Doji", "Ritel Aktif", "Anomali", "Accumulation", "Sideways", "Ideal", "Menengah", "Konsolidasi / Transisi", "Neutral"]): return 'color: #eab308; font-weight: 600;'
        elif "⭐" in val: return 'color: #22c55e;' if len(val) >= 6 else 'color: #ef4444;'
    return ''

def render_strategy_table(df_subset, file_name):
    if not df_subset.empty:
        sort_cols = [c for c in ['Total Score', 'Volume'] if c in df_subset.columns]
        if sort_cols: df_subset = df_subset.sort_values(by=sort_cols, ascending=[False, False]).reset_index(drop=True)
        if "Total Score" in df_subset.columns: df_subset["Total Score"] = df_subset["Total Score"].apply(format_skor)

        # KITA TAMBAHKAN "Value Transaksi" DI SINI:
        kolom_utama = ["Ticker", "Harga (Rp)", "Change (%)", "Value Transaksi", "Volume", "Total Score", "Auto Trading Plan"]
        kolom_tambahan = ["Kelas Transaksi", "Broksum", "Trend MA (5,20,50)", "RVOL (Anomali Vol)", "Tekanan Bandar", "Status Bandar", "Kekuatan A/D", "Sinyal Cuci Barang", "Status BB", "MA Signal"]
        kolom_tampil = [c for c in kolom_utama + kolom_tambahan if c in df_subset.columns]

        # KITA TAMBAHKAN FORMATTER UNTUK VALUE DI SINI:
        styler = df_subset[kolom_tampil].style.format({
            "Harga (Rp)": format_angka, 
            "Volume": format_angka, 
            "Change (%)": format_pct,
            "Value Transaksi": format_singkat_rp
        })
        subset_warna = [c for c in kolom_tampil if c not in ["Ticker", "Auto Trading Plan"]]
        tabel_jadi = styler.map(warna_tabel, subset=subset_warna) if hasattr(styler, 'map') else styler.applymap(warna_tabel, subset=subset_warna)

        st.dataframe(tabel_jadi, use_container_width=True, hide_index=True)

        c1, c2 = st.columns([1, 1])
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer: tabel_jadi.to_excel(writer, index=False, sheet_name='Screener')
        c1.download_button(label=f"📥 Download {file_name} (Excel)", data=buffer.getvalue(), file_name=f"{file_name}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key=f"dl_{file_name}")
        with c2:
            st.markdown("**📋 Salin Daftar Saham:**")
            st.code("\n".join(df_subset["Ticker"].tolist()), language="text")
            st.caption("Klik icon 'Copy' untuk paste ke Tab AI.")
    else: st.info("🔍 Belum ada pergerakan saham yang memenuhi kriteria strategi ini pada sesi saat ini.")

# ==============================================================================
# BANNER STATUS UPDATE AKTIF & NOTIFIKASI SELESAI
# ==============================================================================
if is_updating:
    st.markdown("""
        <div class="update-anim-box" style="margin-top: 10px; margin-bottom: 20px;">
            <div class="radar-icon">📡</div>
            <h3 style="margin: 0; color: #38bdf8; font-size: 17px; font-weight: 800;">PROSES SINKRONISASI DATA PASAR SEDANG BERJALAN</h3>
            <p style="margin: 8px 0 0 0; color: #94a3b8; font-size: 13px;">
                Mesin sedang menyedot data live dari <b>Stockbit & Yahoo Finance</b>, menganalisis bandarmologi, dan mendeteksi anomali volume.<br>
                <span style="color: #06b6d4; font-size: 12px; font-weight: 600;">🔄 Halaman web akan memuat ulang hasil secara otomatis begitu proses tuntas.</span>
            </p>
        </div>
    """, unsafe_allow_html=True)
elif st.session_state.get("just_completed_update"):
    c_notif1, c_notif2 = st.columns([5, 1])
    with c_notif1:
        st.balloons()
        st.success("🎉 **Pembaruan Data Pasar Berhasil Selesai!** Seluruh indikator teknikal, broker summary Stockbit, dan Machine Learning telah diperbarui.")
    with c_notif2:
        if st.button("Tutup ✕", key="btn_close_notif_done"):
            st.session_state["just_completed_update"] = False
            st.rerun()

# Polling loop otomatis saat update berjalan: jeda 2.5 detik lalu rerun
if is_updating:
    time.sleep(2.5)
    st.rerun()

# ==============================================================================
# RENDER 4 TABS UTAMA (VERSI BERSIH 100%)
# ==============================================================================
if not df_hasil.empty:
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📊 Market Overview", 
        "📌 Screener Utama", 
        "🤖 Asisten AI Spesial", 
        "💼 Portofolio Bot",
        "🌐 Multi-Aset & Forecast AI"
    ])
    
    # ==========================================================================
    # [TAB 1] MARKET OVERVIEW 
    # ==========================================================================
    with tab1:
        st.markdown("### 📊 Ringkasan Pasar IHSG")
        
        total_saham = len(df_hasil)
        saham_naik = len(df_hasil[df_hasil['Change (%)'] > 0]) if 'Change (%)' in df_hasil.columns else 0
        saham_turun = len(df_hasil[df_hasil['Change (%)'] < 0]) if 'Change (%)' in df_hasil.columns else 0
        saham_stagnan = total_saham - saham_naik - saham_turun
        
        if 'Turnover' not in df_hasil.columns:
            if 'Volume' in df_hasil.columns and 'Harga (Rp)' in df_hasil.columns:
                df_hasil['Turnover'] = df_hasil['Harga (Rp)'] * df_hasil['Volume']
            else:
                df_hasil['Turnover'] = 0

        if saham_naik > (saham_turun * 1.5): sentimen_teks, warna_sentimen = "🔥 Sangat Bullish", "#4ade80"
        elif saham_turun > (saham_naik * 1.5): sentimen_teks, warna_sentimen = "🩸 Sangat Bearish", "#f87171"
        else: sentimen_teks, warna_sentimen = "⚖️ Konsolidasi (Ragu)", "#facc15"
                
        m1, m2, m3, m4, m5 = st.columns(5)
        m1.markdown(f"<div class='metric-container'><h3>🔍 Total Saham</h3><h2>{total_saham}</h2></div>", unsafe_allow_html=True)
        m2.markdown(f"<div class='metric-container'><h3>🟢 Menguat</h3><h2 style='color: #4ade80;'>{saham_naik}</h2></div>", unsafe_allow_html=True)
        m3.markdown(f"<div class='metric-container'><h3>🔴 Melemah</h3><h2 style='color: #f87171;'>{saham_turun}</h2></div>", unsafe_allow_html=True)
        m4.markdown(f"<div class='metric-container'><h3>⚪ Stagnan</h3><h2 style='color: #94a3b8;'>{saham_stagnan}</h2></div>", unsafe_allow_html=True)
        m5.markdown(f"<div class='metric-container'><h3>🧭 Sentimen Pasar</h3><h3 style='color: {warna_sentimen}; margin-top:5px;'>{sentimen_teks}</h3></div>", unsafe_allow_html=True)
        
        st.markdown("---")
        
        c1, c2 = st.columns(2)
        c3, c4 = st.columns(2)

        def render_top_table(df_top, cols, format_dict):
            styler = df_top[cols].style.format(format_dict)
            tabel_warna = styler.map(warna_tabel, subset=['Change (%)']) if hasattr(styler, 'map') else styler.applymap(warna_tabel, subset=['Change (%)'])
            st.dataframe(tabel_warna, use_container_width=True, hide_index=True)

        with c1:
            st.markdown("#### 🔥 Top Gainers")
            if 'Change (%)' in df_hasil.columns:
                df_gainer = df_hasil.nlargest(10, 'Change (%)')
                render_top_table(df_gainer, ['Ticker', 'Harga (Rp)', 'Change (%)'], {'Harga (Rp)': format_angka, 'Change (%)': format_pct})
            
        with c2:
            st.markdown("#### 🩸 Top Losers")
            if 'Change (%)' in df_hasil.columns:
                df_loser = df_hasil.nsmallest(10, 'Change (%)')
                render_top_table(df_loser, ['Ticker', 'Harga (Rp)', 'Change (%)'], {'Harga (Rp)': format_angka, 'Change (%)': format_pct})
            
        st.markdown("<br>", unsafe_allow_html=True)
            
        with c3:
            st.markdown("#### 🌊 Top Volume")
            if 'Volume' in df_hasil.columns:
                df_vol = df_hasil.nlargest(10, 'Volume')
                render_top_table(df_vol, ['Ticker', 'Harga (Rp)', 'Volume', 'Change (%)'], {'Harga (Rp)': format_angka, 'Volume': format_singkat_vol, 'Change (%)': format_pct})
            
        with c4:
            st.markdown("#### 💰 Top Value (Turnover)")
            if 'Turnover' in df_hasil.columns:
                df_val = df_hasil.nlargest(10, 'Turnover')
                render_top_table(df_val, ['Ticker', 'Harga (Rp)', 'Turnover', 'Change (%)'], {'Harga (Rp)': format_angka, 'Turnover': format_singkat_rp, 'Change (%)': format_pct})

    # ==========================================================================
    # [TAB 2] SCREENER UTAMA
    # ==========================================================================
    with tab2:
        def reset_semua_filter():
            for k, info in MASTER_FILTERS.items():
                if f"main_{k}" in st.session_state:
                    st.session_state[f"main_{k}"] = info["options"][0]
            st.session_state["pencarian_ticker"] = ""
            st.session_state["pencarian_broker"] = ""
            st.session_state["batas_harga_min"] = 0
            st.session_state["batas_harga_max"] = 0

        with st.expander("🛠️ Buka Panel Filter Lengkap", expanded=False):
            st.button("🔄 Reset Semua Filter ke Bawaan (Semua)", on_click=reset_semua_filter, use_container_width=True)
            st.markdown("---")
            
            col_f1, col_f2, col_f3, col_f4 = st.columns(4)
            filter_terpilih = {}
            for idx, (db_key, info) in enumerate(MASTER_FILTERS.items()):
                target_col = col_f1 if idx % 4 == 0 else (col_f2 if idx % 4 == 1 else (col_f3 if idx % 4 == 2 else col_f4))
                with target_col:
                    val_sekarang = st.session_state.get(f"main_{db_key}", info["options"][0])
                    idx_opsi = info["options"].index(val_sekarang) if val_sekarang in info["options"] else 0
                    filter_terpilih[db_key] = st.selectbox(info["label"], info["options"], index=idx_opsi, key=f"main_{db_key}", on_change=manual_override)

        col_search, col_broker, col_min, col_max = st.columns([1.5, 1.5, 1, 1])
        with col_search: 
            search_ticker = st.text_input("🔍 Cari Kode Saham", "", placeholder="Contoh: BBCA", key="pencarian_ticker")
        with col_broker: 
            search_broker = st.text_input("👤 Cari Kode Broker", "", placeholder="Contoh: MG / YP", key="pencarian_broker")
        with col_min: 
            min_price = st.number_input("⬇️ Harga Minimal (Rp)", min_value=0, value=0, step=10, key="batas_harga_min")
        with col_max: 
            max_price = st.number_input("⬆️ Harga Maksimal (Rp)", min_value=0, value=0, step=10, key="batas_harga_max")

        df_filtered = df_hasil.copy()
        
        if search_ticker: 
            df_filtered = df_filtered[df_filtered["Ticker"].astype(str).str.contains(search_ticker.upper(), na=False)]
            
        if search_broker and "Broksum" in df_filtered.columns: 
            df_filtered = df_filtered[df_filtered["Broksum"].astype(str).str.contains(search_broker.upper(), na=False)]
            
        if min_price > 0:
            df_filtered = df_filtered[df_filtered["Harga (Rp)"] >= min_price]
        if max_price > 0:
            df_filtered = df_filtered[df_filtered["Harga (Rp)"] <= max_price]
        
        for db_key, nilai in filter_terpilih.items():
            if nilai != "Semua":
                if db_key == "RSI (14D)":
                    if "RSI (14D)" in df_filtered.columns: df_filtered = df_filtered[df_filtered["RSI (14D)"] > 50] if "Bullish" in nilai else df_filtered[df_filtered["RSI (14D)"] <= 50]
                elif db_key == "Total Score":
                    if "Total Score" in df_filtered.columns: df_filtered = df_filtered[df_filtered["Total Score"] == int(nilai)]
                elif db_key == "Kategori" and nilai == "Mid Cap (Lapis 2) + Small Cap (Lapis 3)":
                    if "Kategori" in df_filtered.columns:
                        df_filtered = df_filtered[df_filtered["Kategori"].isin(["Mid Cap (Lapis 2)", "Small Cap (Lapis 3)"])]
                elif db_key in df_filtered.columns: 
                    df_filtered = df_filtered[df_filtered[db_key] == nilai]

        if not df_filtered.empty:
            st.caption(f"Menampilkan **{len(df_filtered)}** saham yang lolos filter dari total **{len(df_hasil)}** saham.")
            st.markdown("<div class='view-mode-container'>", unsafe_allow_html=True)
            mode_tampilan = st.radio("👁️ Pilih Mode Tampilan Tabel:", ["🚀 Ringkasan Cepat", "👤 Bandarmologi & Wyckoff", "📈 Teknikal & Support", "💎 Fundamental & Likuiditas", "🌌 Tampilkan Semua Kolom"], horizontal=True)
            st.markdown("</div>", unsafe_allow_html=True)
            
            cp1, cp2, cp3 = st.columns([1, 1, 2])
            with cp1: per_hal = st.selectbox("Tampilkan baris:", [20, 50, 100])
            tot_hal = int(np.ceil(len(df_filtered) / per_hal))
            with cp2: hal_aktif = st.selectbox("Halaman:", range(1, tot_hal + 1)) if tot_hal > 0 else 1
                    
            idx_awal = (hal_aktif - 1) * per_hal
            df_tampil = df_filtered.iloc[idx_awal : idx_awal + per_hal].copy()
            if "Total Score" in df_tampil.columns: df_tampil["Total Score"] = df_tampil["Total Score"].apply(format_skor)
            
            kolom_ringkasan = ["Ticker", "Harga (Rp)", "Change (%)", "Value Transaksi", "Volume", "Broksum", "Rekomendasi", "Status Open", "Posisi VWAP", "Total Score", "Auto Trading Plan"]
            kolom_bandar = ["Ticker", "Harga (Rp)", "Change (%)", "Value Transaksi", "Broksum", "Fase Siklus Bandar", "Kekuatan A/D", "Status Bandar", "RVOL (Anomali Vol)", "Karakter Gorengan", "Tekanan Bandar", "OBV Trend", "Kondisi Supply", "Prediksi Machine Learning"]
            kolom_teknikal = ["Ticker", "Harga (Rp)", "Change (%)", "Value Transaksi", "Auto Trading Plan", "Risk/Reward Ratio", "Status Fibonacci", "Sinyal Cuci Barang", "Posisi Entry", "Pola Candle", "Trend MA (5,20,50)", "MA Signal", "Status BB", "RSI (14D)", "MACD", "Status Stochastic"]
            kolom_fundamental = ["Ticker", "Harga (Rp)", "Value Transaksi", "Kategori", "Valuasi", "PER (x)", "PBV (x)", "Kelas Transaksi", "Likuiditas", "Status Sentimen"]
            kolom_semua = ["Ticker", "Value Transaksi", "Broksum", "Status Open", "Risk/Reward Ratio", "Status Fibonacci", "Auto Trading Plan", "Streak Harian", "Sinyal Cuci Barang", "Kategori", "Kelas Transaksi", "Valuasi", "Harga (Rp)", "PER (x)", "PBV (x)", "Harga MA20", "Posisi VWAP", "Support", "Resistance", "Posisi Entry", "Pola Candle", "Change (%)", "Volume", "RVOL (Anomali Vol)", "Vol Breakout", "Status Gap", "Fase Siklus Bandar", "Karakter Gorengan", "Tekanan Bandar", "Kekuatan A/D", "Status Bandar", "OBV Trend", "RSI (14D)", "Momentum", "Trend MA (5,20,50)", "MA Signal", "MA Cross", "MACD", "Status Stochastic", "Status BB", "Risiko", "Likuiditas", "Status Sentimen", "Prediksi Machine Learning", "Kondisi Supply", "Total Score", "Rekomendasi"]
            
            if "Ringkasan" in mode_tampilan: kolom_pilih = kolom_ringkasan
            elif "Bandarmologi" in mode_tampilan: kolom_pilih = kolom_bandar
            elif "Teknikal" in mode_tampilan: kolom_pilih = kolom_teknikal
            elif "Fundamental" in mode_tampilan: kolom_pilih = kolom_fundamental
            else: kolom_pilih = kolom_semua

            kolom_ada = [c for c in kolom_pilih if c in df_tampil.columns]
            format_dict = {}
            for col in ["Harga (Rp)", "Harga MA20", "Support", "Resistance", "Volume"]:
                if col in df_tampil.columns: format_dict[col] = format_angka
            if "Change (%)" in df_tampil.columns: format_dict["Change (%)"] = format_pct
            if "Momentum" in df_tampil.columns: format_dict["Momentum"] = format_mom
            if "Value Transaksi" in df_tampil.columns: format_dict["Value Transaksi"] = format_singkat_rp # <-- Tambahkan ini
            for col in ["PER (x)", "PBV (x)"]:
                if col in df_tampil.columns: format_dict[col] = format_desimal
            if "RSI (14D)" in df_tampil.columns: format_dict["RSI (14D)"] = "{:.0f}"

            styler_obj = df_tampil[kolom_ada].style.format(format_dict)
            subset_warna = [c for c in kolom_ada if c not in ["Ticker", "Auto Trading Plan"]]
            tabel_akhir = styler_obj.map(warna_tabel, subset=subset_warna) if hasattr(styler_obj, 'map') else styler_obj.applymap(warna_tabel, subset=subset_warna)
            st.dataframe(tabel_akhir, use_container_width=True, hide_index=True)
            
            st.markdown("---")
            col_dl, col_wl = st.columns([1, 1])
            with col_dl:
                csv_filter = df_filtered[kolom_ada].to_csv(index=False).encode('utf-8')
                st.download_button(label=f"📥 Download Data Tabel CSV", data=csv_filter, file_name=f"Screener_View_{datetime.now().strftime('%Y%m%d_%H%M')}.csv", mime="text/csv", key="dl_tab2")
            with col_wl:
                st.markdown("**📋 Salin Daftar Saham:**")
                st.code("\n".join(df_filtered["Ticker"].tolist()), language="text")
                st.caption("Klik icon 'Copy' untuk paste massal ke Tab AI.")
        else: st.warning("Tidak ada data sesuai filter.")

    # ==========================================================================
    # [TAB 3] ASISTEN AI SPESIAL (TURNAMEN)
    # ==========================================================================
    with tab3:
        st.markdown("## 🦅 Radar BSJP & Laboratorium Forensik AI")
        st.markdown("<div class='bandar-box-green'><b>💡 INFO:</b> Gunakan kotak pilihan (Dropdown) di bawah ini untuk beralih antar strategi atau mode AI agar tampilan lebih rapi.</div>", unsafe_allow_html=True)
        
        if 'Tekanan Bandar' not in df_hasil.columns:
            st.warning("⏳ **Fitur Radar belum menerima data terbaru.** Harap jalankan 'update_data.py'.")
        else:
            # --- SYARAT MUTLAK: WAJIB SQUEEZE ---
            cond_squeeze = (df_hasil.get('Status BB', '') == 'Squeeze')

            # RUMUS 1 (BARU) : Squeeze + Supply Kering + Di Atas VWAP
            cond_v1 = (cond_squeeze & 
                       df_hasil.get('Kondisi Supply', '').astype(str).str.contains('Supply Kering', na=False) &
                       (df_hasil.get('Posisi VWAP', '') == 'Di Atas VWAP (Kuat)'))
            df_v1 = df_hasil[cond_v1].copy() if not df_hasil.empty else pd.DataFrame()

            # RUMUS 2 (BARU - Mantan R2) : Squeeze + Anomali ML + OBV Akumulasi
            cond_v2 = (cond_squeeze & 
                       df_hasil.get('Prediksi Machine Learning', '').astype(str).str.contains('ANOMALI BANDAR', na=False) &
                       (df_hasil.get('OBV Trend', '') == 'Akumulasi (Naik)'))
            df_v2 = df_hasil[cond_v2].copy() if not df_hasil.empty else pd.DataFrame()

            # RUMUS 3 (BARU - Mantan R6) : Squeeze + Akumulasi Kuat (Bandar) + Akumulasi Pro (A/D)
            cond_v3 = (cond_squeeze & 
                       (df_hasil.get('Status Bandar', '') == 'Akumulasi Kuat') &
                       (df_hasil.get('Kekuatan A/D', '') == 'Akumulasi Pro (Smart Money)'))
            df_v3 = df_hasil[cond_v3].copy() if not df_hasil.empty else pd.DataFrame()

            # RUMUS 4 (BARU) : Squeeze + Volume Tembus MA20 + Ritel Aktif (5M - 50M)
            cond_v4 = (cond_squeeze & 
                       (df_hasil.get('Vol Breakout', '') == 'Tembus MA20') &
                       (df_hasil.get('Kelas Transaksi', '') == 'Ritel Aktif (5M - 50M)'))
            df_v4 = df_hasil[cond_v4].copy() if not df_hasil.empty else pd.DataFrame()

            # RUMUS 5 (Mantan R4) : Squeeze + Golden Cross
            cond_v5 = (cond_squeeze & (df_hasil.get('MA Cross', '') == 'Golden Cross'))
            df_v5 = df_hasil[cond_v5].copy() if not df_hasil.empty else pd.DataFrame()

            # RUMUS 6 (Mantan R5) : Squeeze + Hammer
            cond_v6 = (cond_squeeze & (df_hasil.get('Pola Candle', '') == 'Hammer (Potensi Reversal)'))
            df_v6 = df_hasil[cond_v6].copy() if not df_hasil.empty else pd.DataFrame()

            # RUMUS 7 : Squeeze + Solid (Jarang Dibanting)
            cond_v7 = (cond_squeeze & (df_hasil.get('Karakter Gorengan', '') == 'Solid (Jarang Dibanting)'))
            df_v7 = df_hasil[cond_v7].copy() if not df_hasil.empty else pd.DataFrame()

            # RUMUS 8 : Squeeze + Accumulation (Wyckoff)
            cond_v8 = (cond_squeeze & (df_hasil.get('Fase Siklus Bandar', '') == 'Accumulation (Kumpul Barang)'))
            df_v8 = df_hasil[cond_v8].copy() if not df_hasil.empty else pd.DataFrame()

            # RUMUS 9 : Squeeze + Risk/Reward Menarik
            cond_v9 = (cond_squeeze & (df_hasil.get('Risk/Reward Ratio', '') == 'Sangat Menarik (> 1:3)'))
            df_v9 = df_hasil[cond_v9].copy() if not df_hasil.empty else pd.DataFrame()

            tab_screener, tab_fundamental, tab_ai, tab_tracker = st.tabs([
                "🎯 Screener Spesial", 
                "💎 Fundamental Super (Jumat 20:00)",
                "🧠 Asisten AI", 
                "📈 Tracker Akurasi 9 Rumus (Per Jam & Harian)"
            ])
            
            with tab_screener:
                pilihan_v = st.selectbox(
                    "Pilih Rumus Screener (Wajib Squeeze):",
                    [
                        "RUMUS 1 : Squeeze + Supply Kering 🏜️ + Di Atas VWAP", 
                        "RUMUS 2 : Squeeze + 🔥 ANOMALI ML + OBV Akumulasi Naik", 
                        "RUMUS 3 : Squeeze + 🕵️ Akumulasi Kuat (Broksum & Smart Money)", 
                        "RUMUS 4 : Squeeze + Volume Tembus MA20 🔊 + Ritel Aktif 💸", 
                        "RUMUS 5 : Squeeze + Golden Cross",
                        "RUMUS 6 : Squeeze + Hammer (Potensi Reversal)",
                        "RUMUS 7 : Squeeze + Solid (Jarang Dibanting)",
                        "RUMUS 8 : Squeeze + 🔄 Siklus Wyckoff ( Accumulation )",
                        "RUMUS 9 : Squeeze + Sangat Menarik (> 1:3)"
                    ]
                )
                
                st.markdown("---")
                if "RUMUS 1" in pilihan_v:
                    render_strategy_table(df_v1, "Screener_Rumus_1")
                elif "RUMUS 2" in pilihan_v:
                    render_strategy_table(df_v2, "Screener_Rumus_2")
                elif "RUMUS 3" in pilihan_v:
                    render_strategy_table(df_v3, "Screener_Rumus_3")
                elif "RUMUS 4" in pilihan_v:
                    render_strategy_table(df_v4, "Screener_Rumus_4")
                elif "RUMUS 5" in pilihan_v:
                    render_strategy_table(df_v5, "Screener_Rumus_5")
                elif "RUMUS 6" in pilihan_v:
                    render_strategy_table(df_v6, "Screener_Rumus_6")
                elif "RUMUS 7" in pilihan_v:
                    render_strategy_table(df_v7, "Screener_Rumus_7")
                elif "RUMUS 8" in pilihan_v:
                    render_strategy_table(df_v8, "Screener_Rumus_8")
                elif "RUMUS 9" in pilihan_v:
                    render_strategy_table(df_v9, "Screener_Rumus_9")

            with tab_fundamental:
                st.markdown("### 💎 Screener Fundamental Super (Jumat Malam 20:00 WIB)")
                st.caption("Penyaring seluruh saham listing bursa dengan 12 kriteria ketat Stockbit Screener: Valuasi Diskon, Kas Melimpah (Net Cash), Bebas Risiko Utang (DER <= 0.5), Profitabilitas Prima (ROA >= 10%, ROE >= 15%), dan Laba Bertumbuh.")
                
                col_f1, col_f2, col_f3 = st.columns([1, 1, 1])
                with col_f1:
                    btn_run_fund = st.button("🔄 Jalankan Screening Sekarang", use_container_width=True, key="btn_run_fund_ui")
                with col_f2:
                    btn_send_fund = st.button("📲 Kirim Hasil ke Telegram", use_container_width=True, key="btn_send_fund_ui")
                with col_f3:
                    st.caption("⏰ **Jadwal Otomatis:** Setiap Jumat 20:00 WIB")
                
                file_fund_csv = "Database/hasil_screener_fundamental_jumat.csv"
                if btn_run_fund:
                    with st.spinner("Mengevaluasi seluruh saham bursa (bisa memakan waktu 30-60 detik)..."):
                        from screener_fundamental_jumat import jalankan_screener_fundamental
                        df_fund = jalankan_screener_fundamental()
                        st.success(f"Analisa selesai! Ditemukan {len(df_fund)} emiten lolos kriteria.")
                elif os.path.exists(file_fund_csv):
                    try:
                        df_fund = pd.read_csv(file_fund_csv)
                    except Exception:
                        df_fund = pd.DataFrame()
                else:
                    df_fund = pd.DataFrame()

                if btn_send_fund:
                    with st.spinner("Mengirimkan laporan ke bot Telegram..."):
                        from notifikasi_telegram import kirim_alert_screener_fundamental_jumat
                        sukses_tg, msg_tg = kirim_alert_screener_fundamental_jumat(df_lolos=df_fund, force=True)
                        if sukses_tg:
                            st.success(msg_tg)
                            st.toast("Laporan Fundamental terkirim ke Telegram!", icon="💎")
                        else:
                            st.error(msg_tg)

                st.markdown("---")
                if not df_fund.empty:
                    m1, m2, m3, m4 = st.columns(4)
                    m1.metric("🌟 Saham Lolos", f"{len(df_fund)} Emiten")
                    avg_roe = df_fund["ROE (%)"].mean() if "ROE (%)" in df_fund.columns else 0
                    m2.metric("📈 Rata-Rata ROE", f"{avg_roe:.1f}%")
                    avg_per = df_fund["PER TTM"].mean() if "PER TTM" in df_fund.columns else 0
                    m3.metric("📊 Rata-Rata PER", f"{avg_per:.1f}x")
                    avg_pbv = df_fund["PBV"].mean() if "PBV" in df_fund.columns else 0
                    m4.metric("💰 Rata-Rata PBV", f"{avg_pbv:.2f}x")
                    
                    st.dataframe(df_fund, use_container_width=True, hide_index=True)
                    csv_data = df_fund.to_csv(index=False).encode('utf-8')
                    st.download_button(
                        label="📥 Download Hasil Screener Fundamental (CSV)",
                        data=csv_data,
                        file_name="hasil_screener_fundamental_jumat.csv",
                        mime="text/csv",
                        key="dl_fund_csv"
                    )
                else:
                    st.info("ℹ️ Belum ada data hasil screening fundamental tersimpan. Klik **'Jalankan Screening Sekarang'** untuk memulai analisa seluruh bursa.")

            with tab_ai:
                pilihan_ai = st.selectbox(
                    "Pilih Mode Analisis AI:",
                    [
                        "🤖 AI Bandar (Persiapan BSJP)", 
                        "🔎 Forensik Bandar (Bongkar DNA ARA)", 
                        "🎯 Pemburu ARA (Spesialis DNA Ledakan)"
                    ]
                )
                st.markdown("---")
                
                if "AI Bandar" in pilihan_ai:
                    st.subheader("🤖 AI Bandar (Persiapan BSJP Besok)")
                    
                    # MEMBAGI AI BANDAR MENJADI 2 TAB AGAR RAPI
                    tab_otomatis, tab_manual = st.tabs(["🛸 Auto-Pilot 9 Rumus (Spreadsheet)", "✍️ Mode Manual (Paste Saham)"])
                    
                    with tab_otomatis:
                        st.markdown("Sistem akan menyeleksi 15 saham terbaik per rumus secara global, lalu AI akan memilih Top 5 untuk dicetak ke tabel Spreadsheet.")
                        
                        if not get_secret("GEMINI_API_KEY"):
                            with st.expander("🔑 Masukkan Kunci Gemini API (Sesi Ini / Belum Ada di .env)", expanded=True):
                                st.caption("Kunci API ini akan digunakan selama sesi berjalan, atau Anda dapat menyimpannya permanen di file `.env`.")
                                st.text_input("Gemini API Key:", type="password", placeholder="Tempel kunci AIzaSy... di sini", key="custom_GEMINI_API_KEY")

                        if st.button("🛸 Jalankan Auto-Pilot Ultimate", type="primary", key="autopilot_utama"):
                            
                            GEMINI_API_KEY = get_secret("GEMINI_API_KEY")
                            
                            if not GEMINI_API_KEY:
                                st.error("❌ **Kunci API GEMINI belum dipasang!**\n\nSilakan masukkan kunci API pada kotak input di atas atau buat file `.env` di folder proyek dengan isi:\n```ini\nGEMINI_API_KEY=kunci_anda_disini\n```")
                            else:
                                daftar_rumus = {
                                    1: df_v1, 2: df_v2, 3: df_v3, 
                                    4: df_v4, 5: df_v5, 6: df_v6, 
                                    7: df_v7, 8: df_v8, 9: df_v9
                                }
                                
                                progress_bar = st.progress(0)
                                status_teks = st.empty()
                                
                                # Siapkan keranjang untuk membuat tabel spreadsheet di akhir
                                keranjang_spreadsheet = {f"RUMUS {i}": [] for i in range(1, 10)}
                                
                                for i in range(1, 10):
                                    df_target = daftar_rumus[i]
                                    progress_bar.progress(i / 9.0)
                                    
                                    if len(df_target) == 0:
                                        status_teks.warning(f"⏭️ Rumus {i} kosong. Dilewati.")
                                        time.sleep(1)
                                        continue
                                        
                                    status_teks.info(f"🔄 **Algojo Python bekerja pada Rumus {i}**... (Mengekstrak data global)")
                                    
                                    saham_valid = df_target['Ticker'].tolist()
                                    df_seleksi = df_hasil[df_hasil['Ticker'].isin(saham_valid)].copy()
                                    
                                    df_seleksi['Score_Num'] = pd.to_numeric(df_seleksi['Total Score'], errors='coerce').fillna(0)
                                    
                                    # TAHAP 1: KLASEMEN GLOBAL (Pilih Top 15 berdasarkan Data Keras)
                                    df_sorted = df_seleksi.sort_values(by=['Score_Num', 'Volume', 'Change (%)'], ascending=[False, False, False])
                                    top_15 = df_sorted.head(15)
                                    
                                    data_kirim_ai = {}
                                    for _, row in top_15.iterrows():
                                        data_kirim_ai[row['Ticker']] = {
                                            'Harga': row.get('Harga (Rp)', 0),
                                            'Volume': row.get('Volume', 0),
                                            'Score': row.get('Score_Num', 0),
                                            'Change_Pct': row.get('Change (%)', 0),
                                            'Tekanan_Bandar': row.get('Tekanan Bandar', 'Normal'),
                                            'Broksum': row.get('Broksum', 'Normal')
                                        }
                                        
                                    status_teks.warning(f"🧠 Rumus {i} - Sidang Grand Final AI... (Menyaring 5 Jawara dari Top 15)")
                                    
                                    # TAHAP 2: HAKIM AI (Pilih Top 5 Mutlak)
                                    try:
                                        hasil_mentah = ai_hakim_klasemen(data_kirim_ai, GEMINI_API_KEY)
                                        
                                        if "Error_AI:" in hasil_mentah:
                                            st.error(f"❌ API Error Rumus {i} : {hasil_mentah}")
                                            keranjang_spreadsheet[f"RUMUS {i}"] = ["", "", "", "", ""]
                                            continue
                                            
                                        import json
                                        import re
                                        
                                        # ========================================================
                                        # PENYEDOT DEBU V2 (Sistem Coba-Baca dari Bawah)
                                        # ========================================================
                                        # Cari SEMUA teks yang diapit kurung siku [...]
                                        semua_blok_kurung = re.findall(r'\[.*?\]', hasil_mentah, re.DOTALL)
                                        
                                        hasil_json = None
                                        
                                        # Coba baca dari blok yang paling bawah (hasil akhir AI) ke atas
                                        for blok in reversed(semua_blok_kurung):
                                            try:
                                                # Bersihkan tanda kutip nyeleneh dan koma berlebih
                                                blok_bersih = blok.replace("'", '"')
                                                blok_bersih = re.sub(r',\s*\]', ']', blok_bersih) 
                                                
                                                # Coba ubah teks menjadi tabel asli
                                                hasil_json = json.loads(blok_bersih)
                                                
                                                if isinstance(hasil_json, list):
                                                    break # Berhasil menemukan tabel utuh! Hentikan pencarian.
                                                else:
                                                    hasil_json = None
                                            except:
                                                continue # Jika gagal (karena ada titik-titik '...'), lanjut coba blok lain
                                                
                                        if hasil_json is not None:
                                            df_tampil = pd.DataFrame(hasil_json)
                                            
                                            # Ambil ticker untuk tabel
                                            jawara_tickers = df_tampil['Ticker'].tolist() if 'Ticker' in df_tampil.columns else []
                                            jawara_tickers = (jawara_tickers + ["", "", "", "", ""])[:5] 
                                            keranjang_spreadsheet[f"RUMUS {i}"] = jawara_tickers
                                            
                                            # Simpan Sinyal
                                            if 'Target_TP' in df_tampil.columns and 'Target_CL' in df_tampil.columns:
                                                df_tampil[['Ticker', 'Target_TP', 'Target_CL']].to_csv(f"Database/sinyal_ai_rumus_{i}.csv", index=False)
                                                
                                        else:
                                            st.error(f"❌ Rumus {i} dilewati: Tidak ada format tabel yang utuh.")
                                            st.code(hasil_mentah, language="text")
                                            keranjang_spreadsheet[f"RUMUS {i}"] = ["", "", "", "", ""]
                                            
                                    except Exception as e:
                                        st.error(f"❌ Error Sistem Mesin pada Rumus {i}: {e}")
                                        keranjang_spreadsheet[f"RUMUS {i}"] = ["", "", "", "", ""]
                                    
                                    time.sleep(2.5) # Nafas panjang untuk API Google
                                
                                status_teks.success("🎉 MISSION ACCOMPLISHED! SELURUH RUMUS BERHASIL DISARING!")
                                st.balloons()
                                
                                # TAHAP 3: CETAK TABEL SPREADSHEET (Siap Copy-Paste)
                                st.markdown("### 📋 Tabel Master Portofolio (Siap Salin)")
                                df_spreadsheet = pd.DataFrame(keranjang_spreadsheet)
                                
                                st.data_editor(df_spreadsheet, use_container_width=True, hide_index=True)

                    with tab_manual:
                        st.markdown("Paste saham yang MASIH MERAH / SIDEWAYS. AI akan mencari siapa yang siap terbang besok.")
                        input_saham_massal = st.text_area("📋 Paste Daftar Saham (Pisahkan dengan Enter/Spasi):", placeholder="Contoh:\nDMAS\nINDF", height=200, key="input_ai_bandar")
                        
                        if st.button("🔮 Mulai Eksekusi AI Bandar"):
                            saham_bersih = [s.strip().upper() for s in re.split(r'[,\s\n]+', input_saham_massal) if s.strip()]
                            saham_unik = list(dict.fromkeys(saham_bersih))
                            saham_valid = [s for s in saham_unik if s in df_hasil['Ticker'].values]
                            
                            df_valid = df_hasil[df_hasil['Ticker'].isin(saham_valid)].copy()
                            if 'Change (%)' in df_valid.columns:
                                df_valid = df_valid[df_valid['Change (%)'] <= 5.0]
                                saham_valid = df_valid['Ticker'].tolist()

                            if not saham_valid:
                                st.error("❌ Saham yang Anda masukkan sudah terbang terlalu tinggi (>5%). Gunakan AI Bandar untuk mencari saham yang masih di bawah!")
                            else:
                                if len(saham_valid) > 19:
                                    st.info("🤖 Menyaring 19 saham terbaik untuk mencegah limit AI...")
                                    df_valid = df_valid.sort_values(by=['Total Score', 'Volume'], ascending=[False, False])
                                    saham_valid = df_valid['Ticker'].head(19).tolist()
                                
                                with st.spinner(f"Menganalisa {len(saham_valid)} saham untuk BSJP besok..."):
                                    data_kompilasi = {}
                                    for ticker in saham_valid:
                                        data_saham = df_hasil[df_hasil['Ticker'] == ticker].iloc[0]
                                        teks_ringkasan = get_historical_summary(ticker)
                                        data_kompilasi[ticker] = {
                                            'harga': data_saham.get('Harga (Rp)', 0),
                                            'change': data_saham.get('Change (%)', 0), 
                                            'broksum': data_saham.get('Broksum', 'Tidak Ada'),
                                            'status': data_saham.get('Fase Siklus Bandar', 'Normal'),
                                            'skor': data_saham.get('Total Score', 0),
                                            'histori': teks_ringkasan if teks_ringkasan else "Arsip belum tersedia."
                                        }
                                    hasil_ai = analisa_bandar_ai_multisaham(data_kompilasi, 'pilihan_ai')
                                    st.info(hasil_ai)

                elif "Forensik Bandar" in pilihan_ai:
                    st.subheader("📡 Radar Pencari Model Gemini Aktif (Live Server)")
                    st.markdown("Mesin ini akan bertanya langsung ke server Google AI Studio untuk mencari **semua nama model Gemini yang valid dan mendukung fitur Generate Content** untuk API Key Anda, lalu mengujinya satu per satu.")
                    
                    input_tester = st.text_area("📋 Paste Daftar Saham Uji Coba (Minimal 3 Saham):", placeholder="Contoh:\nVISI\nBBHI\nPANI", height=150, key="input_tester_gemini")
                    
                    if st.button("🚀 Tarik Daftar Server Google & Mulai Uji Coba"):
                        GEMINI_API_KEY = get_secret("GEMINI_API_KEY")
                        if not GEMINI_API_KEY:
                            st.error("❌ Kunci API GEMINI belum dipasang! Masukkan di .env atau konfigurasi Secrets.")
                        else:
                            saham_bersih = [s.strip().upper() for s in re.split(r'[,\s\n]+', input_tester) if s.strip()]
                            saham_unik = list(dict.fromkeys(saham_bersih))
                            saham_valid = [s for s in saham_unik if s in df_hasil['Ticker'].values]
                            
                            if len(saham_valid) < 2:
                                st.error("❌ Masukkan minimal 2 kode saham yang valid di database hari ini.")
                            else:
                                st.info("🔄 Langkah 1: Meminta katalog model langsung dari server Google AI...")
                                
                                daftar_model_aktif = []
                                try:
                                    genai.configure(api_key=GEMINI_API_KEY)
                                    for m in genai.list_models():
                                        if 'generateContent' in m.supported_generation_methods:
                                            daftar_model_aktif.append(m.name)
                                except Exception as e:
                                    st.error(f"Gagal menarik data dari server Google. Error: {e}")
                                
                                if not daftar_model_aktif:
                                    st.warning("⚠️ Tidak ada model yang ditemukan untuk API Key ini.")
                                else:
                                    st.success(f"✅ Ditemukan {len(daftar_model_aktif)} model Gemini yang online untuk Anda! Memulai pengujian...")
                                    
                                    progress_bar = st.progress(0)
                                    status_text = st.empty()
                                    
                                    payload_text = ""
                                    for ticker in saham_valid:
                                        data_saham = df_hasil[df_hasil['Ticker'] == ticker].iloc[0]
                                        payload_text += f"\n- {ticker}: Harga {data_saham.get('Harga (Rp)', 0)}, Vol {data_saham.get('Volume', 0)}"

                                    prompt_test = f"""
                                    CRITICAL INSTRUCTION: You are an automated data filter. 
                                    Read this data:
                                    {payload_text}
                                    
                                    MISSION: Pick EXACTLY 1 best ticker based on volume.
                                    STRICT RULE: Output ONLY the 4-letter ticker code (e.g., BBCA). DO NOT add any other words, punctuation, explanations, or formatting.
                                    """
                                    
                                    hasil_rekap = []
                                    
                                    for i, nama_model in enumerate(daftar_model_aktif):
                                        model_id_bersih = nama_model.replace("models/", "")
                                        status_text.text(f"⏳ Sedang menguji: {model_id_bersih} ({i+1}/{len(daftar_model_aktif)})")
                                        
                                        try:
                                            model_uji = genai.GenerativeModel(model_id_bersih)
                                            response = model_uji.generate_content(prompt_test)
                                            raw_content = response.text or ""
                                            bersih = raw_content.replace('`', '').replace('.', '').replace('\n', '').strip().upper()
                                            
                                            if bersih in saham_valid:
                                                status = "✅ Lulus & Patuh (Sangat Cocok!)"
                                            else:
                                                status = f"⚠️ Aktif tapi Bawel (Jawab: {raw_content.strip()[:25]}...)"
                                                
                                            hasil_rekap.append({"Nama Model": model_id_bersih, "Status": status})
                                            
                                        except Exception as e:
                                            pesan_error = str(e)
                                            hasil_rekap.append({"Nama Model": model_id_bersih, "Status": f"❌ Gagal: {pesan_error[:30]}..."})
                                        
                                        progress_bar.progress((i + 1) / len(daftar_model_aktif))
                                        time.sleep(2)
                                    
                                    status_text.success("🎉 Pengecekan Server Google Selesai!")
                                    
                                    df_rekap = pd.DataFrame(hasil_rekap)
                                    st.markdown("### 🏆 Hasil Uji Coba Model Gemini (Live Server)")
                                    st.dataframe(df_rekap, use_container_width=True)
                                    
                                    st.info("💡 **TUGAS ANDA:** Salin nama model yang berstatus '✅ Lulus & Patuh', dan kita gunakan nama pasti itu untuk skrip turnamen!")

                elif "Pemburu ARA" in pilihan_ai:
                    st.subheader("🎯 Pemburu ARA (Sistem Kualifikasi)")
                    st.info("💡 **Fitur Auto-Pilot 9 Rumus (Klasemen Global & AI) telah dipusatkan pada menu '🤖 AI Bandar'.**")
                    st.markdown("""
                    Silakan pilih mode **'🤖 AI Bandar (Persiapan BSJP)'** pada menu dropdown di atas untuk:
                    - Menjalankan **Auto-Pilot 9 Rumus** dengan seleksi Top 15 data keras dan Hakim AI.
                    - Mencetak **Tabel Master Portofolio** siap salin ke Spreadsheet.
                    - Menghasilkan file sinyal otomatis untuk eksekusi bot simulator.
                    """)

            with tab_tracker:
                st.markdown("### 📈 Evaluasi & Validasi Akurasi Prediksi 9 Rumus AI")
                st.markdown("<div class='bandar-box-green'><b>💡 CARA KERJA TRACKER:</b> Sistem otomatis menyimpan snapshot setiap saham yang masuk ke dalam 9 Rumus BSJP pada jam bursa (per jam), merekam jejak harga hari H, dan memverifikasi realisasi harga di keesokan harinya (T+1) untuk membuktikan apakah rekomendasi akurat menghasilkan cuan (Hit TP) atau meleset.</div>", unsafe_allow_html=True)
                
                col_trk1, col_trk2 = st.columns([3, 1])
                with col_trk1:
                    st.caption("Data di bawah ini mencatat histori rekomendasi per jam dan memvalidasi kenaikan harga T+1.")
                with col_trk2:
                    if st.button("🔄 Evaluasi Akurasi Sekarang", use_container_width=True, key="btn_eval_tracker_now", help="Periksa harga pasar terkini untuk mengevaluasi rekomendasi kemarin"):
                        with st.spinner("Mengevaluasi realisasi harga saham..."):
                            jml_eval = tracker_ai.evaluasi_akurasi_rekomendasi(df_hasil)
                            st.cache_data.clear()
                            st.success(f"Berhasil mengevaluasi {jml_eval} saham!")
                            time.sleep(1)
                            st.rerun()

                # Hitung Statistik Ringkasan
                stat_data = tracker_ai.hitung_ringkasan_statistik()
                
                # Metric Cards
                m1, m2, m3, m4 = st.columns(4)
                with m1:
                    st.markdown(f"""
                        <div class="metric-container">
                            <span style="font-size:12px; color:#94a3b8; font-weight:600;">🎯 AKURASI TOTAL (WIN RATE)</span>
                            <h2 style="margin:5px 0; color:#10b981; font-size:28px;">{stat_data['win_rate_total']}%</h2>
                            <span style="font-size:11px; color:#6ee7b7;">{stat_data['total_akurat']} Akurat / {stat_data['total_evaluasi']} Terevaluasi</span>
                        </div>
                    """, unsafe_allow_html=True)
                with m2:
                    st.markdown(f"""
                        <div class="metric-container">
                            <span style="font-size:12px; color:#94a3b8; font-weight:600;">📈 RATA-RATA MAX GAIN BESOK</span>
                            <h2 style="margin:5px 0; color:#38bdf8; font-size:28px;">+{stat_data['avg_max_gain']}%</h2>
                            <span style="font-size:11px; color:#bae6fd;">Potensi Cuan Maksimal T+1</span>
                        </div>
                    """, unsafe_allow_html=True)
                with m3:
                    st.markdown(f"""
                        <div class="metric-container">
                            <span style="font-size:12px; color:#94a3b8; font-weight:600;">🏆 RUMUS PALING AKURAT (#1)</span>
                            <h2 style="margin:5px 0; color:#facc15; font-size:20px;">{stat_data['rumus_terbaik']}</h2>
                            <span style="font-size:11px; color:#fef08a;">Berdasarkan Tingkat Keberhasilan</span>
                        </div>
                    """, unsafe_allow_html=True)
                with m4:
                    st.markdown(f"""
                        <div class="metric-container">
                            <span style="font-size:12px; color:#94a3b8; font-weight:600;">📦 TOTAL SAHAM TERPANTAU</span>
                            <h2 style="margin:5px 0; color:#f8fafc; font-size:28px;">{stat_data['total_rekomendasi']}</h2>
                            <span style="font-size:11px; color:#94a3b8;">Saham Masuk Radar AI</span>
                        </div>
                    """, unsafe_allow_html=True)

                # Grafik Perbandingan Akurasi Antar Rumus (Plotly Bar Chart)
                if stat_data["stat_per_rumus"]:
                    st.markdown("#### 📊 Perbandingan Tingkat Kemenangan (*Win Rate %*) Antar 9 Rumus")
                    
                    df_chart_stat = pd.DataFrame([
                        {
                            "Rumus": v["nama"],
                            "Judul": v["judul"],
                            "Win Rate (%)": v["win_rate"],
                            "Avg Max Gain (%)": v["avg_max_gain"],
                            "Total Saham": v["total"]
                        }
                        for k, v in stat_data["stat_per_rumus"].items()
                    ])
                    
                    fig_winrate = go.Figure()
                    fig_winrate.add_trace(go.Bar(
                        x=df_chart_stat["Rumus"],
                        y=df_chart_stat["Win Rate (%)"],
                        text=[f"{val}%" if tot > 0 else "0" for val, tot in zip(df_chart_stat["Win Rate (%)"], df_chart_stat["Total Saham"])],
                        textposition='auto',
                        marker=dict(
                            color=df_chart_stat["Win Rate (%)"],
                            colorscale='Viridis',
                            showscale=True,
                            colorbar=dict(title="Win Rate %")
                        ),
                        hovertext=[f"{r}: {j}<br>Win Rate: {w}%<br>Avg Gain: +{g}% ({t} saham)" for r, j, w, g, t in zip(df_chart_stat["Rumus"], df_chart_stat["Judul"], df_chart_stat["Win Rate (%)"], df_chart_stat["Avg Max Gain (%)"], df_chart_stat["Total Saham"])],
                        hoverinfo="text"
                    ))
                    fig_winrate.update_layout(
                        height=350,
                        margin=dict(l=20, r=20, t=30, b=20),
                        paper_bgcolor="rgba(0,0,0,0)",
                        plot_bgcolor="rgba(15,23,42,0.6)",
                        yaxis=dict(title="Win Rate (%)", range=[0, 105], gridcolor="#334155"),
                        xaxis=dict(title="Kategori Rumus BSJP", gridcolor="#334155"),
                        font=dict(color="#f8fafc")
                    )
                    st.plotly_chart(fig_winrate, use_container_width=True)

                # Tabel Rincian Tracker
                st.markdown("#### 📋 Tabel Riwayat Rekomendasi Per Jam & Hasil Realisasi Besok")
                df_tracker_view = tracker_ai.get_tracker_dataframe()
                
                if not df_tracker_view.empty:
                    col_f1, col_f2, col_f3 = st.columns([2, 2, 2])
                    with col_f1:
                        pilih_rumus_filter = st.selectbox(
                            "Filter Rumus:",
                            ["Semua Rumus"] + [f"{info['nama']} - {info['judul']}" for info in tracker_ai.DAFTAR_RUMUS.values()],
                            key="filter_rumus_tracker"
                        )
                    with col_f2:
                        pilih_status_filter = st.selectbox(
                            "Filter Status Akurasi:",
                            ["Semua Status", "🎯 AKURAT (HIT TP)", "⚖️ NETRAL (BEP)", "❌ MELESET (CL)", "⏳ MENUNGGU T+1"],
                            key="filter_status_tracker"
                        )
                    with col_f3:
                        cari_ticker = st.text_input("Cari Saham (Ticker):", placeholder="Contoh: BBRI", key="cari_ticker_tracker").strip().upper()

                    # Terapkan filter
                    df_filtered = df_tracker_view.copy()
                    if pilih_rumus_filter != "Semua Rumus":
                        df_filtered = df_filtered[df_filtered["Rumus"] == pilih_rumus_filter]
                    if pilih_status_filter != "Semua Status":
                        df_filtered = df_filtered[df_filtered["Status Akurasi"] == pilih_status_filter]
                    if cari_ticker:
                        df_filtered = df_filtered[df_filtered["Ticker"].str.contains(cari_ticker, na=False)]

                    def warnai_status_akurasi(val):
                        if "AKURAT" in str(val):
                            return 'background-color: #166534; color: #f0fdf4; font-weight: 700;'
                        elif "NETRAL" in str(val):
                            return 'background-color: #854d0e; color: #fefce8; font-weight: 700;'
                        elif "MELESET" in str(val):
                            return 'background-color: #991b1b; color: #fef2f2; font-weight: 700;'
                        return 'color: #94a3b8;'

                    def warnai_gain(val):
                        if isinstance(val, (int, float)):
                            if val >= 1.5:
                                return 'background-color: #166534; color: #f0fdf4; font-weight: bold;'
                            elif val > 0:
                                return 'background-color: #065f46; color: #ecfdf5;'
                            elif val < 0:
                                return 'background-color: #991b1b; color: #fef2f2;'
                        return ''

                    styler_trk = df_filtered.style
                    tabel_trk = styler_trk.map(warnai_status_akurasi, subset=["Status Akurasi"]) if hasattr(styler_trk, 'map') else styler_trk.applymap(warnai_status_akurasi, subset=["Status Akurasi"])
                    tabel_trk = tabel_trk.map(warnai_gain, subset=["Max Gain T+1 (%)", "Open Gain T+1 (%)"]) if hasattr(tabel_trk, 'map') else tabel_trk.applymap(warnai_gain, subset=["Max Gain T+1 (%)", "Open Gain T+1 (%)"])

                    st.dataframe(
                        tabel_trk.format({
                            "Harga Masuk (Rp)": "Rp {:,.0f}",
                            "T+1 Open (Rp)": lambda x: f"Rp {x:,.0f}" if pd.notnull(x) else "-",
                            "T+1 High (Rp)": lambda x: f"Rp {x:,.0f}" if pd.notnull(x) else "-",
                            "T+1 Close (Rp)": lambda x: f"Rp {x:,.0f}" if pd.notnull(x) else "-",
                            "Max Gain T+1 (%)": lambda x: f"{x:+.2f}%" if pd.notnull(x) else "-",
                            "Open Gain T+1 (%)": lambda x: f"{x:+.2f}%" if pd.notnull(x) else "-"
                        }),
                        use_container_width=True,
                        hide_index=True
                    )
                    
                    st.caption(f"Menampilkan {len(df_filtered)} data rekomendasi. Kriteria Akurat: Max Gain besok >= +1.5% (Target Standar Cuan BSJP).")
                else:
                    st.info("Belum ada data tracker yang tercatat. Jalankan update data pasar untuk mulai mencatat.")

    # ==========================================
    # TAB 4: PORTOFOLIO & BOT
    # ==========================================
    with tab4:
        st.markdown("## 🤖 Monitor Bot Simulator")
        
        # --- TOMBOL PEMICU BOT ---
        if st.button("🛒 Eksekusi Pembelian Bot Sekarang!", type="primary", use_container_width=True):
            with st.spinner("Bot sedang membaca sinyal dan mengeksekusi pembelian..."):
                import subprocess
                import sys  
                
                try:
                    proses_bot = subprocess.run([sys.executable, "bot_simulator.py"], capture_output=True, text=True)
                    
                    if proses_bot.returncode != 0:
                        st.error("❌ Bot gagal dijalankan. Berikut adalah log error dari sistem:")
                        st.code(proses_bot.stderr, language="bash")
                    else:
                        st.success("✅ Bot selesai berbelanja! Memuat ulang halaman...")
                        time.sleep(2)
                        st.rerun()
                except Exception as e:
                    st.error(f"Sistem web gagal memanggil file bot: {e}")
        
        st.markdown("---")
        
        # =========================================================
        # 📊 LAPORAN PERFORMA (SISTEM BRANKAS 3 LAPIS)
        # =========================================================
        st.markdown("## 📊 Dashboard Performa AI (Live)")
        
        pilihan_arena = st.selectbox("📂 Pilih Arena untuk diinspeksi:", [f"Rumus {i}" for i in range(1, 10)])
        nomor_rumus = pilihan_arena.split(" ")[1]

        FILE_SINYAL = f"Database/sinyal_ai_rumus_{nomor_rumus}.csv"
        file_porto = f"Database/portofolio_aktif_rumus_{nomor_rumus}.csv"
        file_hist = f"Database/histori_transaksi_rumus_{nomor_rumus}.csv"

        MODAL_AWAL = 100000000.0 
        
        df_porto = pd.read_csv(file_porto) if os.path.exists(file_porto) else pd.DataFrame()
        df_hist = pd.read_csv(file_hist) if os.path.exists(file_hist) else pd.DataFrame()

        # ---------------------------------------------------------
        # 🏆 LAPIS 3: PAPAN SKOR WINRATE & SALDO KAS
        # ---------------------------------------------------------
        total_profit_rp = df_hist['Total_Return_Rp'].sum() if not df_hist.empty and 'Total_Return_Rp' in df_hist.columns else 0
        modal_terpakai = df_porto['Total_Modal'].sum() if not df_porto.empty and 'Total_Modal' in df_porto.columns else 0
        
        saldo_saat_ini = MODAL_AWAL + total_profit_rp - modal_terpakai
        total_aset = saldo_saat_ini + modal_terpakai
        
        total_trade = len(df_hist)
        if total_trade > 0 and 'Return_%' in df_hist.columns:
            win_trade = len(df_hist[df_hist['Return_%'] > 0])
            winrate = (win_trade / total_trade) * 100
        else:
            winrate = 0.0

        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric(label="💰 Total Aset (Kas + Saham)", value=f"Rp {total_aset:,.0f}".replace(",", "."))
        with col2:
            st.metric(label="💵 Dana Kas Tersedia", value=f"Rp {saldo_saat_ini:,.0f}".replace(",", "."))
        with col3:
            st.metric(label="📈 Realized Profit/Loss", value=f"Rp {total_profit_rp:,.0f}".replace(",", "."), delta=f"Rp {total_profit_rp:,.0f}".replace(",", "."))
        with col4:
            st.metric(label="🎯 Winrate AI", value=f"{winrate:.1f}%", delta=f"{total_trade} Selesai", delta_color="off")

        st.markdown("---")
        
        # ---------------------------------------------------------
        # MENUNJUKKAN 3 TABEL (ANTREAN, AKTIF, HISTORI)
        # ---------------------------------------------------------
        sub1, sub2, sub3 = st.tabs(["📝 Sinyal Antrean", "🟢 Lapis 1: Portofolio Aktif", "📚 Lapis 2: Histori Transaksi"])
        
        with sub1:
            if os.path.exists(FILE_SINYAL):
                df_sinyal = pd.read_csv(FILE_SINYAL)
                st.success("🔥 Sinyal AI (Kertas Belanja) telah diterima! Bot akan mengeksekusi pembelian pada jam bursa.")
                st.dataframe(df_sinyal, use_container_width=True, hide_index=True)
            else:
                st.info(f"KOSONG. Belum ada sinyal masuk untuk {pilihan_arena}, atau bot sudah membelinya dan membakar kertas belanja.")
        
        with sub2:
            if not df_porto.empty:
                df_porto_tampil = df_porto.copy()
                df_porto_tampil['Harga_Beli'] = df_porto_tampil['Harga_Beli'].apply(lambda x: f"Rp {x:,.0f}".replace(",", "."))
                df_porto_tampil['Target_TP'] = df_porto_tampil['Target_TP'].apply(lambda x: f"Rp {x:,.0f}".replace(",", "."))
                df_porto_tampil['Target_CL'] = df_porto_tampil['Target_CL'].apply(lambda x: f"Rp {x:,.0f}".replace(",", "."))
                df_porto_tampil['Total_Modal'] = df_porto_tampil['Total_Modal'].apply(lambda x: f"Rp {x:,.0f}".replace(",", "."))
                st.dataframe(df_porto_tampil, use_container_width=True, hide_index=True)
            else:
                st.info("📦 Gudang kosong. Belum ada saham yang dibeli atau semua sudah terjual (Masuk ke Lapis 2).")
        
        with sub3:
            if not df_hist.empty:
                def warnai_profit(val):
                    if isinstance(val, (int, float)):
                        color = '#166534' if val > 0 else '#991b1b' if val < 0 else ''
                        return f'background-color: {color}'
                    return ''
                    
                if 'Tanggal_Jual' in df_hist.columns:
                    df_hist_tampil = df_hist.sort_values(by='Tanggal_Jual', ascending=False).reset_index(drop=True)
                else:
                    df_hist_tampil = df_hist.copy()
                    
                styler_hist = df_hist_tampil.style
                tabel_hist = styler_hist.map(warnai_profit, subset=['Total_Return_Rp', 'Return_%']) if hasattr(styler_hist, 'map') else styler_hist.applymap(warnai_profit, subset=['Total_Return_Rp', 'Return_%'])
                st.dataframe(
                    tabel_hist.format({
                        'Harga_Beli': "Rp {:,.0f}",
                        'Harga_Jual': "Rp {:,.0f}",
                        'Total_Return_Rp': "Rp {:,.0f}",
                        'Return_%': "{:.2f}%"
                    }),
                    use_container_width=True,
                    hide_index=True
                )
            else:
                st.info(f"📭 Belum ada riwayat penjualan saham untuk {pilihan_arena}.")

    # ==========================================================================
    # [TAB 5] 🌐 MULTI-ASET & FORECAST AI (DARI SAHAM-IDX)
    # ==========================================================================
    with tab5:
        st.markdown("## 🌐 Multi-Aset Tracker & Mesin Prediksi AI")
        st.markdown("<div class='bandar-box-green'><b>💡 FITUR MULTI-ASET & FORECAST:</b> Pantau portofolio terdiversifikasi lintas kelas aset (Saham IHSG, Emas Fisik/Digital, Cryptocurrency, Saham US) serta analisis proyeksi harga saham masa depan berbasis machine learning.</div>", unsafe_allow_html=True)
        
        tab_sub_multi, tab_sub_forecast = st.tabs([
            "🥇 Multi-Aset Portfolio Tracker",
            "🔮 AI Price Forecaster (XGBoost)"
        ])
        
        # --- SUBTAB 1: MULTI-ASET PORTFOLIO ---
        with tab_sub_multi:
            st.markdown("### 📊 Ringkasan Portofolio Multi-Aset")
            
            with st.spinner("Mengambil data valuasi pasar terkini..."):
                multi_summary = calculate_multi_asset_summary()
            
            usd_rate = multi_summary.get("usd_idr", 16350.0)
            gold_data = get_gold_price_idr(usd_rate)
            
            # Kartu Metrik Valuta & Emas
            col_k1, col_k2, col_k3, col_k4 = st.columns(4)
            with col_k1:
                st.metric("💱 Kurs USD / IDR", f"Rp {usd_rate:,.0f}".replace(",", "."))
            with col_k2:
                st.metric("🥇 Harga Emas / Gram", f"Rp {gold_data.get('idr_per_gram', 0):,.0f}".replace(",", "."))
            with col_k3:
                st.metric("💰 Total Modal Multi-Aset", f"Rp {multi_summary.get('total_modal', 0):,.0f}".replace(",", "."))
            with col_k4:
                pl_tot = multi_summary.get('total_pl_rp', 0)
                pl_tot_pct = multi_summary.get('total_pl_pct', 0)
                st.metric(
                    "📈 Floating Profit / Loss",
                    f"Rp {pl_tot:+,.0f}".replace(",", "."),
                    f"{pl_tot_pct:+.2f}%"
                )
            
            st.markdown("---")
            
            # Tabel Aset
            asset_rows = multi_summary.get("assets", [])
            if asset_rows:
                df_multi = pd.DataFrame(asset_rows)
                df_multi_view = df_multi[[
                    "Ticker", "Nama", "Kelas Aset", "Jumlah", 
                    "Harga Rata-rata Beli (Rp)", "Harga Saat Ini (Rp)", 
                    "Total Modal (Rp)", "Nilai Pasar (Rp)", 
                    "Floating P/L (Rp)", "Floating P/L (%)", "Catatan"
                ]].copy()
                
                def warnai_pl(val):
                    if isinstance(val, (int, float)):
                        color = '#166534' if val > 0 else '#991b1b' if val < 0 else ''
                        return f'background-color: {color}'
                    return ''
                
                styler_mv = df_multi_view.style
                tabel_mv = styler_mv.map(warnai_pl, subset=["Floating P/L (Rp)", "Floating P/L (%)"]) if hasattr(styler_mv, 'map') else styler_mv.applymap(warnai_pl, subset=["Floating P/L (Rp)", "Floating P/L (%)"])
                st.dataframe(
                    tabel_mv.format({
                        "Jumlah": "{:,.4f}" if any(df_multi_view["Jumlah"] < 1) else "{:,.0f}",
                        "Harga Rata-rata Beli (Rp)": "Rp {:,.0f}",
                        "Harga Saat Ini (Rp)": "Rp {:,.0f}",
                        "Total Modal (Rp)": "Rp {:,.0f}",
                        "Nilai Pasar (Rp)": "Rp {:,.0f}",
                        "Floating P/L (Rp)": "Rp {:+,.0f}",
                        "Floating P/L (%)": "{:+.2f}%"
                    }),
                    use_container_width=True,
                    hide_index=True
                )
            else:
                st.info("Portofolio multi-aset kosong. Tambahkan aset baru di bawah ini.")
            
            # Form Tambah Aset
            with st.expander("➕ Tambah Aset ke Portofolio"):
                with st.form("form_tambah_aset"):
                    col_f1, col_f2, col_f3 = st.columns(3)
                    with col_f1:
                        f_ticker = st.text_input("Ticker / Kode Aset:", placeholder="Contoh: BBCA, BTC, GOLD, AAPL").upper().strip()
                        f_nama = st.text_input("Nama Aset:", placeholder="Contoh: Bank BCA, Bitcoin")
                    with col_f2:
                        f_kelas = st.selectbox("Kelas Aset:", list(ASSET_CLASS_LABELS.keys()), format_func=lambda x: ASSET_CLASS_LABELS[x])
                        f_qty = st.number_input("Jumlah Kepemilikan (Qty):", min_value=0.0001, value=1.0, step=0.1, format="%.4f")
                    with col_f3:
                        f_harga = st.number_input("Harga Beli Rata-rata (IDR):", min_value=1.0, value=10000.0, step=1000.0)
                        f_catatan = st.text_input("Catatan Investasi:", placeholder="Contoh: Tabungan jangka panjang")
                    
                    submit_aset = st.form_submit_button("💾 Simpan Aset ke Portofolio")
                    if submit_aset:
                        if f_ticker:
                            current_holdings = load_multi_asset_portfolio()
                            current_holdings.append({
                                "ticker": f_ticker,
                                "nama": f_nama or f_ticker,
                                "asset_class": f_kelas,
                                "quantity": float(f_qty),
                                "avg_buy_price_idr": float(f_harga),
                                "catatan": f_catatan
                            })
                            save_multi_asset_portfolio(current_holdings)
                            st.success(f"Aset {f_ticker} berhasil ditambahkan!")
                            st.rerun()
                        else:
                            st.error("Ticker aset tidak boleh kosong.")
        
        # --- SUBTAB 2: AI PRICE FORECASTER ---
        with tab_sub_forecast:
            st.markdown("### 🔮 Mesin Prediksi Tren Harga Saham (Machine Learning)")
            st.caption("Memproyeksikan estimasi pergerakan harga 7–30 hari ke depan menggunakan regresi multi-langkah dan rentang volatilitas ketidakpastian.")
            
            col_fc1, col_fc2, col_fc3 = st.columns([2, 1, 1])
            with col_fc1:
                daftar_pilihan_ticker = df_hasil['Ticker'].tolist() if 'Ticker' in df_hasil.columns else ['BBCA', 'TLKM', 'BBRI', 'ASII', 'BMRI']
                pilih_ticker_fc = st.selectbox(
                    "Pilih Emiten untuk Diprediksi:",
                    daftar_pilihan_ticker,
                    index=0,
                    key="fc_ticker_pilih"
                )
            with col_fc2:
                pilih_hari_fc = st.slider("Horizon Prediksi (Hari):", min_value=7, max_value=30, value=14, step=7)
            with col_fc3:
                st.markdown("<br>", unsafe_allow_html=True)
                btn_prediksi = st.button("🚀 Jalankan Prediksi AI", use_container_width=True, type="primary")
            
            if btn_prediksi or f"prediksi_{pilih_ticker_fc}" in st.session_state:
                st.session_state[f"prediksi_{pilih_ticker_fc}"] = True
                with st.spinner(f"Melatih model machine learning & memproyeksikan harga {pilih_ticker_fc}..."):
                    hasil_fc = run_stock_forecast(pilih_ticker_fc, periods=pilih_hari_fc)
                
                if hasil_fc.get("status") == "success":
                    st.success(f"Prediksi untuk **{pilih_ticker_fc}** berhasil diselesaikan!")
                    
                    # Metrik Hasil Prediksi
                    col_m1, col_m2, col_m3, col_m4 = st.columns(4)
                    with col_m1:
                        st.metric("Harga Terakhir", f"Rp {hasil_fc['current_price']:,.0f}".replace(",", "."))
                    with col_m2:
                        st.metric(
                            f"Target Prediksi ({pilih_hari_fc} Hari)",
                            f"Rp {hasil_fc['predicted_price']:,.0f}".replace(",", "."),
                            f"{hasil_fc['expected_return_pct']:+.2f}%"
                        )
                    with col_m3:
                        st.metric("Estimasi Error (MAPE)", f"{hasil_fc['mape']:.2f}%")
                    with col_m4:
                        arah = "BULLISH 🚀" if hasil_fc['expected_return_pct'] > 0 else "BEARISH 📉"
                        st.metric("Arah Tren Model", arah)
                    
                    # Visualisasi Plotly Interaktif
                    df_hist_fc = hasil_fc["history_df"]
                    df_future_fc = hasil_fc["forecast_df"]
                    
                    fig = go.Figure()
                    
                    # 1. Garis Riwayat Harga Aktual
                    fig.add_trace(go.Scatter(
                        x=df_hist_fc["ds"],
                        y=df_hist_fc["y"],
                        mode="lines",
                        name="Harga Aktual (60 Hari)",
                        line=dict(color="#3b82f6", width=2)
                    ))
                    
                    # 2. Area Rentang Ketidakpastian (Upper & Lower Band)
                    fig.add_trace(go.Scatter(
                        x=list(df_future_fc["ds"]) + list(df_future_fc["ds"])[::-1],
                        y=list(df_future_fc["yhat_upper"]) + list(df_future_fc["yhat_lower"])[::-1],
                        fill="toself",
                        fillcolor="rgba(245, 158, 11, 0.15)",
                        line=dict(color="rgba(255,255,255,0)"),
                        name="Rentang Ketidakpastian (Confidence Band)",
                        showlegend=True
                    ))
                    
                    # 3. Garis Prediksi Proyeksi Masa Depan
                    fig.add_trace(go.Scatter(
                        x=df_future_fc["ds"],
                        y=df_future_fc["yhat"],
                        mode="lines+markers",
                        name=f"Estimasi Model ({pilih_hari_fc} Hari)",
                        line=dict(color="#f59e0b", width=3, dash="dash")
                    ))
                    
                    fig.update_layout(
                        title=f"Grafik Proyeksi Harga {pilih_ticker_fc} Masa Depan",
                        xaxis_title="Tanggal",
                        yaxis_title="Harga (Rp)",
                        template="plotly_dark",
                        hovermode="x unified",
                        margin=dict(l=20, r=20, t=50, b=20),
                        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
                    )
                    
                    st.plotly_chart(fig, use_container_width=True)
                    
                    # Faktor Penggerak (Feature Importance)
                    feat_imp = hasil_fc.get("feature_importance", {})
                    if feat_imp:
                        st.markdown("**🧠 Faktor Penggerak Model (Feature Importance):**")
                        cols_fi = st.columns(len(feat_imp))
                        for idx_fi, (k_fi, v_fi) in enumerate(feat_imp.items()):
                            with cols_fi[idx_fi]:
                                st.caption(f"**{k_fi}**")
                                st.progress(min(1.0, max(0.0, v_fi / 100)))
                                st.caption(f"{v_fi:.1f}%")
                else:
                    st.error(hasil_fc.get("message", "Gagal memproses prediksi."))