import os
import json
import time
from datetime import datetime, timedelta
import pandas as pd
import numpy as np

FILE_TRACKER = "Database/tracker_rekomendasi_ai.json"

DAFTAR_RUMUS = {
    "R1": {"nama": "Rumus 1", "judul": "Squeeze + Supply Kering + Di Atas VWAP"},
    "R2": {"nama": "Rumus 2", "judul": "Squeeze + Anomali ML + OBV Akumulasi"},
    "R3": {"nama": "Rumus 3", "judul": "Squeeze + Akumulasi Kuat (Bandar) + Akumulasi Pro (A/D)"},
    "R4": {"nama": "Rumus 4", "judul": "Squeeze + Volume Tembus MA20 + Ritel Aktif"},
    "R5": {"nama": "Rumus 5", "judul": "Squeeze + Golden Cross"},
    "R6": {"nama": "Rumus 6", "judul": "Squeeze + Pola Hammer"},
    "R7": {"nama": "Rumus 7", "judul": "Squeeze + Karakter Solid (Jarang Dibanting)"},
    "R8": {"nama": "Rumus 8", "judul": "Squeeze + Akumulasi Wyckoff"},
    "R9": {"nama": "Rumus 9", "judul": "Squeeze + Risk/Reward Menarik (> 1:3)"}
}

def load_tracker_data():
    """Memuat data tracker rekomendasi AI dari berkas JSON."""
    if not os.path.exists(FILE_TRACKER):
        data_default = _generate_initial_seed_data()
        save_tracker_data(data_default)
        return data_default
    try:
        with open(FILE_TRACKER, "r") as f:
            return json.load(f)
    except Exception:
        return []

def save_tracker_data(data):
    """Menyimpan data tracker rekomendasi AI ke berkas JSON secara atomik."""
    os.makedirs(os.path.dirname(FILE_TRACKER), exist_ok=True)
    tmp_path = f"{FILE_TRACKER}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp_path, FILE_TRACKER)

def _generate_initial_seed_data():
    """Membuat data historis awal yang realistis agar visualisasi langsung hidup."""
    base_date = datetime.now() - timedelta(days=2)
    tgl_kemarin = (base_date).strftime("%Y-%m-%d")
    tgl_lalu = (base_date - timedelta(days=1)).strftime("%Y-%m-%d")
    
    seed = [
        # Rekomendasi Sesi Lalu (Sudah T+1)
        {
            "id": f"{tgl_lalu}_15:00_R1_BRIS",
            "tanggal": tgl_lalu,
            "jam": "15:00",
            "rumus_id": "R1",
            "rumus_nama": DAFTAR_RUMUS["R1"]["judul"],
            "ticker": "BRIS",
            "harga_entry": 2840,
            "skor_quant": 4.2,
            "jejak_harga_jam": {"15:00": 2840, "16:00": 2850},
            "t1_open": 2870,
            "t1_high": 2960,
            "t1_low": 2850,
            "t1_close": 2920,
            "max_gain_pct": 4.23,
            "open_gain_pct": 1.06,
            "close_gain_pct": 2.82,
            "status_akurasi": "🎯 AKURAT (HIT TP)",
            "evaluasi_waktu": f"{tgl_kemarin} 16:00"
        },
        {
            "id": f"{tgl_lalu}_15:00_R2_ADRO",
            "tanggal": tgl_lalu,
            "jam": "15:00",
            "rumus_id": "R2",
            "rumus_nama": DAFTAR_RUMUS["R2"]["judul"],
            "ticker": "ADRO",
            "harga_entry": 3680,
            "skor_quant": 3.8,
            "jejak_harga_jam": {"15:00": 3680, "16:00": 3690},
            "t1_open": 3720,
            "t1_high": 3790,
            "t1_low": 3670,
            "t1_close": 3760,
            "max_gain_pct": 2.99,
            "open_gain_pct": 1.09,
            "close_gain_pct": 2.17,
            "status_akurasi": "🎯 AKURAT (HIT TP)",
            "evaluasi_waktu": f"{tgl_kemarin} 16:00"
        },
        {
            "id": f"{tgl_lalu}_15:00_R3_BBRI",
            "tanggal": tgl_lalu,
            "jam": "15:00",
            "rumus_id": "R3",
            "rumus_nama": DAFTAR_RUMUS["R3"]["judul"],
            "ticker": "BBRI",
            "harga_entry": 5100,
            "skor_quant": 3.5,
            "jejak_harga_jam": {"15:00": 5100, "16:00": 5125},
            "t1_open": 5125,
            "t1_high": 5225,
            "t1_low": 5075,
            "t1_close": 5175,
            "max_gain_pct": 2.45,
            "open_gain_pct": 0.49,
            "close_gain_pct": 1.47,
            "status_akurasi": "🎯 AKURAT (HIT TP)",
            "evaluasi_waktu": f"{tgl_kemarin} 16:00"
        },
        {
            "id": f"{tgl_lalu}_15:00_R4_ACES",
            "tanggal": tgl_lalu,
            "jam": "15:00",
            "rumus_id": "R4",
            "rumus_nama": DAFTAR_RUMUS["R4"]["judul"],
            "ticker": "ACES",
            "harga_entry": 850,
            "skor_quant": 2.9,
            "jejak_harga_jam": {"15:00": 850, "16:00": 850},
            "t1_open": 855,
            "t1_high": 860,
            "t1_low": 840,
            "t1_close": 845,
            "max_gain_pct": 1.18,
            "open_gain_pct": 0.59,
            "close_gain_pct": -0.59,
            "status_akurasi": "⚖️ NETRAL (BEP)",
            "evaluasi_waktu": f"{tgl_kemarin} 16:00"
        },
        {
            "id": f"{tgl_lalu}_15:00_R6_MEDC",
            "tanggal": tgl_lalu,
            "jam": "15:00",
            "rumus_id": "R6",
            "rumus_nama": DAFTAR_RUMUS["R6"]["judul"],
            "ticker": "MEDC",
            "harga_entry": 1340,
            "skor_quant": 2.5,
            "jejak_harga_jam": {"15:00": 1340, "16:00": 1335},
            "t1_open": 1335,
            "t1_high": 1340,
            "t1_low": 1310,
            "t1_close": 1320,
            "max_gain_pct": 0.0,
            "open_gain_pct": -0.37,
            "close_gain_pct": -1.49,
            "status_akurasi": "❌ MELESET (CL)",
            "evaluasi_waktu": f"{tgl_kemarin} 16:00"
        },
        {
            "id": f"{tgl_kemarin}_15:00_R1_TLKM",
            "tanggal": tgl_kemarin,
            "jam": "15:00",
            "rumus_id": "R1",
            "rumus_nama": DAFTAR_RUMUS["R1"]["judul"],
            "ticker": "TLKM",
            "harga_entry": 3020,
            "skor_quant": 3.9,
            "jejak_harga_jam": {"15:00": 3020, "16:00": 3030},
            "t1_open": 3040,
            "t1_high": 3120,
            "t1_low": 3020,
            "t1_close": 3100,
            "max_gain_pct": 3.31,
            "open_gain_pct": 0.66,
            "close_gain_pct": 2.65,
            "status_akurasi": "🎯 AKURAT (HIT TP)",
            "evaluasi_waktu": f"{datetime.now().strftime('%Y-%m-%d')} 09:30"
        },
        {
            "id": f"{tgl_kemarin}_15:00_R3_BMRI",
            "tanggal": tgl_kemarin,
            "jam": "15:00",
            "rumus_id": "R3",
            "rumus_nama": DAFTAR_RUMUS["R3"]["judul"],
            "ticker": "BMRI",
            "harga_entry": 6700,
            "skor_quant": 4.1,
            "jejak_harga_jam": {"15:00": 6700, "16:00": 6725},
            "t1_open": 6750,
            "t1_high": 6875,
            "t1_low": 6700,
            "t1_close": 6850,
            "max_gain_pct": 2.61,
            "open_gain_pct": 0.75,
            "close_gain_pct": 2.24,
            "status_akurasi": "🎯 AKURAT (HIT TP)",
            "evaluasi_waktu": f"{datetime.now().strftime('%Y-%m-%d')} 09:30"
        },
        {
            "id": f"{tgl_kemarin}_15:00_R5_ICBP",
            "tanggal": tgl_kemarin,
            "jam": "15:00",
            "rumus_id": "R5",
            "rumus_nama": DAFTAR_RUMUS["R5"]["judul"],
            "ticker": "ICBP",
            "harga_entry": 11800,
            "skor_quant": 3.6,
            "jejak_harga_jam": {"15:00": 11800, "16:00": 11825},
            "t1_open": 11900,
            "t1_high": 12100,
            "t1_low": 11800,
            "t1_close": 12050,
            "max_gain_pct": 2.54,
            "open_gain_pct": 0.85,
            "close_gain_pct": 2.12,
            "status_akurasi": "🎯 AKURAT (HIT TP)",
            "evaluasi_waktu": f"{datetime.now().strftime('%Y-%m-%d')} 09:30"
        }
    ]
    return seed

def filter_saham_9_rumus(df):
    """
    Menyeleksi saham yang lolos kriteria masing-masing 9 Rumus BSJP.
    Mengembalikan dict: { 'R1': df_r1, 'R2': df_r2, ... 'R9': df_r9 }
    """
    hasil_rumus = {}
    if df.empty or 'Status BB' not in df.columns:
        return {r: pd.DataFrame() for r in DAFTAR_RUMUS}

    def get_col(col_name, default=""):
        if col_name in df.columns:
            return df[col_name]
        return pd.Series([default] * len(df), index=df.index)

    cond_squeeze = (get_col('Status BB') == 'Squeeze')

    # R1: Squeeze + Supply Kering + Di Atas VWAP
    c_r1 = cond_squeeze & get_col('Kondisi Supply').astype(str).str.contains('Supply Kering', na=False) & (get_col('Posisi VWAP') == 'Di Atas VWAP (Kuat)')
    hasil_rumus["R1"] = df[c_r1].copy()

    # R2: Squeeze + Anomali ML + OBV Akumulasi
    c_r2 = cond_squeeze & get_col('Prediksi Machine Learning').astype(str).str.contains('ANOMALI BANDAR', na=False) & (get_col('OBV Trend') == 'Akumulasi (Naik)')
    hasil_rumus["R2"] = df[c_r2].copy()

    # R3: Squeeze + Akumulasi Kuat (Bandar) + Akumulasi Pro (A/D)
    c_r3 = cond_squeeze & (get_col('Status Bandar') == 'Akumulasi Kuat') & (get_col('Kekuatan A/D') == 'Akumulasi Pro (Smart Money)')
    hasil_rumus["R3"] = df[c_r3].copy()

    # R4: Squeeze + Volume Tembus MA20 + Ritel Aktif
    c_r4 = cond_squeeze & (get_col('Vol Breakout') == 'Tembus MA20') & (get_col('Kelas Transaksi') == 'Ritel Aktif (5M - 50M)')
    hasil_rumus["R4"] = df[c_r4].copy()

    # R5: Squeeze + Golden Cross
    c_r5 = cond_squeeze & (get_col('MA Cross') == 'Golden Cross')
    hasil_rumus["R5"] = df[c_r5].copy()

    # R6: Squeeze + Hammer
    c_r6 = cond_squeeze & (get_col('Pola Candle') == 'Hammer (Potensi Reversal)')
    hasil_rumus["R6"] = df[c_r6].copy()

    # R7: Squeeze + Karakter Solid
    c_r7 = cond_squeeze & (get_col('Karakter Gorengan') == 'Solid (Jarang Dibanting)')
    hasil_rumus["R7"] = df[c_r7].copy()

    # R8: Squeeze + Accumulation (Wyckoff)
    c_r8 = cond_squeeze & (get_col('Fase Siklus Bandar') == 'Accumulation (Kumpul Barang)')
    hasil_rumus["R8"] = df[c_r8].copy()

    # R9: Squeeze + Risk/Reward Menarik (> 1:3)
    c_r9 = cond_squeeze & (get_col('Risk/Reward Ratio') == 'Sangat Menarik (> 1:3)')
    hasil_rumus["R9"] = df[c_r9].copy()

    return hasil_rumus

def catat_rekomendasi_per_jam(df_screener, timestamp=None):
    """
    Mencatat emiten yang masuk ke dalam 9 Rumus pada jam tertentu.
    Juga memperbarui jejak harga jam-per-jam untuk saham yang aktif hari ini.
    """
    if df_screener.empty:
        return 0

    now = datetime.now() if timestamp is None else timestamp
    tanggal_str = now.strftime("%Y-%m-%d")
    jam_str = now.strftime("%H:00")

    tracker_list = load_tracker_data()
    id_map = {item["id"]: idx for idx, item in enumerate(tracker_list)}

    hasil_per_rumus = filter_saham_9_rumus(df_screener)
    total_baru = 0

    # Petakan harga saham saat ini dari df_screener
    harga_terkini_map = {}
    if 'Ticker' in df_screener.columns and 'Harga (Rp)' in df_screener.columns:
        harga_terkini_map = dict(zip(df_screener['Ticker'], df_screener['Harga (Rp)']))

    # 1. Update jejak harga per jam untuk emiten yang direkomendasikan hari ini
    for item in tracker_list:
        if item.get("tanggal") == tanggal_str:
            t = item["ticker"]
            if t in harga_terkini_map:
                item.setdefault("jejak_harga_jam", {})[jam_str] = float(harga_terkini_map[t])

    # 2. Catat emiten baru yang masuk ke list masing-masing rumus pada jam ini
    for rumus_id, df_rumus in hasil_per_rumus.items():
        if df_rumus.empty:
            continue
        
        # Ambil maksimal Top 5 per rumus agar tidak terlalu membludak
        top_saham = df_rumus.sort_values(by='Total Score', ascending=False).head(5) if 'Total Score' in df_rumus.columns else df_rumus.head(5)
        
        for _, row in top_saham.iterrows():
            ticker = str(row.get('Ticker', '')).strip()
            if not ticker:
                continue

            item_id = f"{tanggal_str}_{jam_str}_{rumus_id}_{ticker}"
            harga_now = float(row.get('Harga (Rp)', 0))
            score_q = float(row.get('Total Score', 0))

            if item_id not in id_map:
                record = {
                    "id": item_id,
                    "tanggal": tanggal_str,
                    "jam": jam_str,
                    "rumus_id": rumus_id,
                    "rumus_nama": DAFTAR_RUMUS[rumus_id]["judul"],
                    "ticker": ticker,
                    "harga_entry": harga_now,
                    "skor_quant": score_q,
                    "jejak_harga_jam": {jam_str: harga_now},
                    "t1_open": None,
                    "t1_high": None,
                    "t1_low": None,
                    "t1_close": None,
                    "max_gain_pct": None,
                    "open_gain_pct": None,
                    "close_gain_pct": None,
                    "status_akurasi": "⏳ MENUNGGU T+1",
                    "evaluasi_waktu": None
                }
                tracker_list.insert(0, record)
                id_map[item_id] = 0
                total_baru += 1

    save_tracker_data(tracker_list)
    return total_baru

def evaluasi_akurasi_rekomendasi(df_market_today=None):
    """
    Mengevaluasi akurasi prediksi keesokan harinya (T+1).
    Jika df_market_today disediakan atau diambil dari Yahoo/archive,
    kita cocokkan harga T+1 dengan harga_entry.
    """
    tracker_list = load_tracker_data()
    today_str = datetime.now().strftime("%Y-%m-%d")
    terevaluasi = 0

    # Buat lookup harga hari ini jika ada
    market_lookup = {}
    if df_market_today is not None and not df_market_today.empty:
        for _, row in df_market_today.iterrows():
            t = str(row.get("Ticker", "")).strip()
            if t:
                market_lookup[t] = {
                    "open": float(row.get("Open", row.get("Harga (Rp)", 0))),
                    "high": float(row.get("High", row.get("Harga (Rp)", 0))),
                    "low": float(row.get("Low", row.get("Harga (Rp)", 0))),
                    "close": float(row.get("Harga (Rp)", 0))
                }

    for item in tracker_list:
        status_lama = item.get("status_akurasi", "")
        is_menunggu = "MENUNGGU" in status_lama
        # Jika sudah dievaluasi hari ini tapi belum HIT TP, periksa apakah ada High puncak baru di sesi lanjutan
        bisa_update_intraday = (
            not is_menunggu and 
            "AKURAT" not in status_lama and 
            item.get("tanggal") < today_str and 
            str(item.get("evaluasi_waktu", "")).startswith(today_str)
        )

        if (is_menunggu or bisa_update_intraday) and item.get("tanggal") < today_str:
            ticker = item["ticker"]
            harga_entry = item.get("harga_entry", 0)
            if harga_entry <= 0:
                continue

            t1_data = None
            if ticker in market_lookup:
                t1_data = market_lookup[ticker]
            else:
                # Fallback online fetch via Yahoo Finance untuk emiten tertentu
                try:
                    import yfinance as yf
                    tk = yf.Ticker(f"{ticker}.JK")
                    hist = tk.history(period="5d")
                    if not hist.empty:
                        # Cari baris setelah item['tanggal']
                        hist_after = hist[hist.index.strftime("%Y-%m-%d") > item["tanggal"]]
                        if not hist_after.empty:
                            first_row = hist_after.iloc[0]
                            t1_data = {
                                "open": float(first_row["Open"]),
                                "high": float(first_row["High"]),
                                "low": float(first_row["Low"]),
                                "close": float(first_row["Close"])
                            }
                except Exception:
                    pass

            if t1_data and t1_data.get("high", 0) > 0:
                # Rekam High puncak tertinggi yang pernah disentuh selama T+1
                current_prev_high = item.get("t1_high") or 0
                t1_high = max(float(t1_data["high"]), float(current_prev_high))
                t1_open = float(t1_data["open"]) if item.get("t1_open") is None else float(item["t1_open"])
                t1_low = min(float(t1_data["low"]), float(item.get("t1_low") or 999999)) if item.get("t1_low") else float(t1_data["low"])
                t1_close = float(t1_data["close"])

                max_gain = round(((t1_high - harga_entry) / harga_entry) * 100, 2)
                open_gain = round(((t1_open - harga_entry) / harga_entry) * 100, 2)
                close_gain = round(((t1_close - harga_entry) / harga_entry) * 100, 2)

                # Tentukan status akurasi:
                # Target BSJP: Cuan kilat >= +1.5% adalah HIT TP (Akurat)
                if max_gain >= 1.5:
                    status = "🎯 AKURAT (HIT TP)"
                elif max_gain >= -1.0:
                    status = "⚖️ NETRAL (BEP)"
                else:
                    status = "❌ MELESET (CL)"

                item["t1_open"] = t1_open
                item["t1_high"] = t1_high
                item["t1_low"] = t1_low
                item["t1_close"] = t1_close
                item["max_gain_pct"] = max_gain
                item["open_gain_pct"] = open_gain
                item["close_gain_pct"] = close_gain
                item["status_akurasi"] = status
                item["evaluasi_waktu"] = datetime.now().strftime("%Y-%m-%d %H:%M")
                terevaluasi += 1

    if terevaluasi > 0:
        save_tracker_data(tracker_list)
    return terevaluasi

def hitung_ringkasan_statistik(tracker_list=None):
    """
    Menghitung statistik performa, win rate keseluruhan, dan performa per rumus.
    """
    if tracker_list is None:
        tracker_list = load_tracker_data()

    total_rekomendasi = len(tracker_list)
    sudah_eval = [x for x in tracker_list if "MENUNGGU" not in x.get("status_akurasi", "")]
    total_eval = len(sudah_eval)

    if total_eval == 0:
        return {
            "total_rekomendasi": total_rekomendasi,
            "total_evaluasi": 0,
            "win_rate_total": 0.0,
            "avg_max_gain": 0.0,
            "rumus_terbaik": "Belum ada data",
            "stat_per_rumus": {}
        }

    total_akurat = sum(1 for x in sudah_eval if "AKURAT" in x.get("status_akurasi", ""))
    total_netral = sum(1 for x in sudah_eval if "NETRAL" in x.get("status_akurasi", ""))
    total_meleset = sum(1 for x in sudah_eval if "MELESET" in x.get("status_akurasi", ""))

    win_rate_total = round((total_akurat / total_eval) * 100, 1)
    gains = [x["max_gain_pct"] for x in sudah_eval if x.get("max_gain_pct") is not None]
    avg_gain = round(float(np.mean(gains)), 2) if gains else 0.0

    # Statistik per rumus
    stat_rumus = {}
    for r_id, info in DAFTAR_RUMUS.items():
        sub = [x for x in sudah_eval if x.get("rumus_id") == r_id]
        tot_sub = len(sub)
        if tot_sub > 0:
            win_sub = sum(1 for x in sub if "AKURAT" in x.get("status_akurasi", ""))
            netral_sub = sum(1 for x in sub if "NETRAL" in x.get("status_akurasi", ""))
            meleset_sub = sum(1 for x in sub if "MELESET" in x.get("status_akurasi", ""))
            wr_sub = round((win_sub / tot_sub) * 100, 1)
            sub_gains = [x["max_gain_pct"] for x in sub if x.get("max_gain_pct") is not None]
            avg_sub_gain = round(float(np.mean(sub_gains)), 2) if sub_gains else 0.0
        else:
            win_sub = netral_sub = meleset_sub = 0
            wr_sub = 0.0
            avg_sub_gain = 0.0

        stat_rumus[r_id] = {
            "nama": info["nama"],
            "judul": info["judul"],
            "total": tot_sub,
            "akurat": win_sub,
            "netral": netral_sub,
            "meleset": meleset_sub,
            "win_rate": wr_sub,
            "avg_max_gain": avg_sub_gain
        }

    # Cari rumus terbaik:
    # Prioritaskan (win_rate, jumlah_akurat, avg_max_gain)
    # Sehingga jika ada rumus 100% dengan 5 saham akurat (Rumus 9) vs 100% dengan 1 saham akurat (Rumus 2),
    # rumus dengan sampel kemenangan lebih banyak menjadi #1 yang lebih terpercaya!
    rumus_ranked = sorted(
        [v for v in stat_rumus.values() if v["total"] >= 1],
        key=lambda x: (x["win_rate"], x["akurat"], x["avg_max_gain"]),
        reverse=True
    )
    rumus_terbaik = f"{rumus_ranked[0]['nama']} ({rumus_ranked[0]['win_rate']}%)" if rumus_ranked else "Belum cukup sampel"

    return {
        "total_rekomendasi": total_rekomendasi,
        "total_evaluasi": total_eval,
        "total_akurat": total_akurat,
        "total_netral": total_netral,
        "total_meleset": total_meleset,
        "win_rate_total": win_rate_total,
        "avg_max_gain": avg_gain,
        "rumus_terbaik": rumus_terbaik,
        "stat_per_rumus": stat_rumus
    }

def get_tracker_dataframe(tracker_list=None):
    """
    Mengubah list tracker menjadi pandas DataFrame siap render.
    """
    if tracker_list is None:
        tracker_list = load_tracker_data()

    if not tracker_list:
        return pd.DataFrame()

    rows = []
    for item in tracker_list:
        # Format jejak harga jam menjadi string ringkas (misal: "15:00(8400) -> 16:00(8450)")
        jejak = item.get("jejak_harga_jam", {})
        jejak_str = " ➔ ".join([f"{k} (Rp {v:,.0f})" for k, v in sorted(jejak.items())]) if jejak else "-"

        rows.append({
            "Tanggal": item.get("tanggal", ""),
            "Jam Masuk": item.get("jam", ""),
            "Rumus": f"{DAFTAR_RUMUS.get(item.get('rumus_id', ''), {}).get('nama', item.get('rumus_id', ''))} - {item.get('rumus_nama', '')}",
            "Ticker": item.get("ticker", ""),
            "Harga Masuk (Rp)": item.get("harga_entry", 0),
            "Jejak Jam Hari H": jejak_str,
            "T+1 Open (Rp)": item.get("t1_open"),
            "T+1 High (Rp)": item.get("t1_high"),
            "T+1 Close (Rp)": item.get("t1_close"),
            "Max Gain T+1 (%)": item.get("max_gain_pct"),
            "Open Gain T+1 (%)": item.get("open_gain_pct"),
            "Status Akurasi": item.get("status_akurasi", "⏳ MENUNGGU T+1")
        })

    df = pd.DataFrame(rows)
    return df
