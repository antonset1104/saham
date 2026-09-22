import os
import json
import html
import requests
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

def get_telegram_config():
    """Mengambil konfigurasi Telegram dinamis dari session_state, secrets, atau env."""
    tok, cid = "", ""
    try:
        import streamlit as st
        if hasattr(st, "secrets"):
            tok = str(st.secrets.get("TELEGRAM_BOT_TOKEN", "")).strip()
            cid = str(st.secrets.get("TELEGRAM_CHAT_ID", "")).strip()
    except Exception:
        pass

    if not tok:
        tok = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not cid:
        cid = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    return tok, cid

def is_telegram_configured() -> bool:
    """Memeriksa apakah konfigurasi bot Telegram telah terisi."""
    tok, cid = get_telegram_config()
    return bool(tok and cid and "ISI_" not in tok)

def simpan_konfigurasi_telegram(token: str, chat_id: str) -> bool:
    """Menyimpan token dan chat ID Telegram langsung ke file .env."""
    env_file = ".env"
    lines = []
    if os.path.exists(env_file):
        with open(env_file, "r") as f:
            lines = f.readlines()
            
    token_found = False
    chat_found = False
    new_lines = []
    for line in lines:
        if line.startswith("TELEGRAM_BOT_TOKEN="):
            new_lines.append(f"TELEGRAM_BOT_TOKEN={token.strip()}\n")
            token_found = True
        elif line.startswith("TELEGRAM_CHAT_ID="):
            new_lines.append(f"TELEGRAM_CHAT_ID={chat_id.strip()}\n")
            chat_found = True
        else:
            new_lines.append(line)
            
    if not token_found:
        new_lines.append(f"TELEGRAM_BOT_TOKEN={token.strip()}\n")
    if not chat_found:
        new_lines.append(f"TELEGRAM_CHAT_ID={chat_id.strip()}\n")
        
    try:
        with open(env_file, "w") as f:
            f.writelines(new_lines)
        os.environ["TELEGRAM_BOT_TOKEN"] = token.strip()
        os.environ["TELEGRAM_CHAT_ID"] = chat_id.strip()
        return True
    except Exception as e:
        print(f"Gagal menyimpan ke .env: {e}")
        return False

def kirim_pesan_telegram(pesan: str, token: str = None, chat_id: str = None) -> bool:
    """
    Mengirim pesan teks dengan format HTML ke Telegram.
    Returns: True jika sukses, False jika gagal/belum terkonfigurasi.
    """
    tok = token or os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    cid = chat_id or os.getenv("TELEGRAM_CHAT_ID", "").strip()

    if not tok or not cid:
        return False

    url = f"https://api.telegram.org/bot{tok}/sendMessage"
    payload = {
        "chat_id": cid,
        "text": pesan,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }

    try:
        resp = requests.post(url, json=payload, timeout=10)
        if resp.status_code == 200:
            return True
        print(f"⚠️ [Telegram] Gagal kirim (HTTP {resp.status_code}): {resp.text[:200]}")
        return False
    except Exception as e:
        print(f"⚠️ [Telegram] Error koneksi: {e}")
        return False

def kirim_alert_transaksi_bot(arena: str, ticker: str, aksi: str, harga: float, lot: int, profit_rp: float = 0, profit_pct: float = 0) -> bool:
    """Mengirim notifikasi instan saat bot trading mengeksekusi beli/jual."""
    if not is_telegram_configured():
        return False

    waktu_str = datetime.now().strftime("%d/%m/%Y %H:%M WIB")
    nilai_rp = harga * lot * 100
    safe_ticker = html.escape(str(ticker))
    safe_arena = html.escape(str(arena))

    if aksi.upper() == "BELI":
        header = f"🟢 <b>[BOT EKSEKUSI BELI] — {safe_ticker}</b>"
        detail_profit = ""
    else:
        status_cuan = "PROFIT 🚀" if profit_rp >= 0 else "CUT LOSS 🩸"
        header = f"🔴 <b>[BOT EKSEKUSI JUAL - {html.escape(status_cuan)}] — {safe_ticker}</b>"
        detail_profit = f"\n💵 <b>P/L Realisasi:</b> Rp {profit_rp:+,.0f} ({profit_pct:+.2f}%)"

    pesan = (
        f"{header}\n"
        f"🏛️ <b>Arena:</b> {safe_arena}\n"
        f"💰 <b>Harga:</b> Rp {harga:,.0f}\n"
        f"📦 <b>Volume:</b> {lot:,} lot (~Rp {nilai_rp:,.0f})"
        f"{detail_profit}\n"
        f"⏰ <i>{waktu_str}</i>"
    )
    return kirim_pesan_telegram(pesan)

def kirim_alert_bsjp(top_saham: list) -> bool:
    """Mengirim ringkasan rekomendasi saham BSJP sore hari."""
    if not is_telegram_configured() or not top_saham:
        return False

    waktu_str = datetime.now().strftime("%d/%m/%Y %H:%M WIB")
    lines = [
        "🦅 <b>RADAR BSJP — REKOMENDASI BELI SORE</b>",
        f"📅 {waktu_str}",
        ""
    ]

    for idx, s in enumerate(top_saham[:5], 1):
        ticker = html.escape(str(s.get("Ticker", "")))
        harga = s.get("Harga (Rp)", 0)
        tp_cl = html.escape(str(s.get("Auto Trading Plan", "-")))
        bintang = html.escape(str(s.get("Total Score", "⭐")))
        lines.append(f"<b>{idx}. {ticker}</b> — Rp {harga:,.0f} ({bintang})")
        lines.append(f"   🎯 Plan: <code>{tp_cl}</code>")

    lines.append("\n⚠️ <i>Beli sore 15:30, jual pagi 09:00. Bukan ajakan finansial resmi.</i>")
    return kirim_pesan_telegram("\n".join(lines))

def kirim_ringkasan_pasar(ringkasan: dict) -> bool:
    """Mengirim ringkasan harian IHSG."""
    if not is_telegram_configured():
        return False

    waktu_str = datetime.now().strftime("%d/%m/%Y %H:%M WIB")
    pesan = (
        f"📊 <b>RINGKASAN PASAR IHSG</b>\n"
        f"📅 {waktu_str}\n\n"
        f"🔍 Total Saham : {ringkasan.get('total', 0)}\n"
        f"🟢 Menguat     : {ringkasan.get('menguat', 0)}\n"
        f"🔴 Melemah     : {ringkasan.get('melemah', 0)}\n"
        f"⚪ Stagnan     : {ringkasan.get('stagnan', 0)}\n"
        f"🧭 Sentimen    : <b>{ringkasan.get('sentimen', '-')}</b>\n"
    )
    return kirim_pesan_telegram(pesan)

FILE_LAST_SENT_1530 = "Database/telegram_1530_sent.json"
FILE_LAST_SENT_1000 = "Database/telegram_1000_sent.json"
FILE_LAST_SENT_JUMAT_2000 = "Database/last_sent_jumat_2000.json"

def kirim_rekomendasi_rumus_2_dan_9(df_screener=None, force=False) -> tuple[bool, str]:
    """
    Mengirimkan daftar rekomendasi saham Beli Sore (BSJP) khusus Rumus 2 & Rumus 9
    ke Telegram bot secara otomatis pada jam 15:30 WIB.
    """
    if not is_telegram_configured():
        return False, "Bot Telegram belum terkonfigurasi (Token/Chat ID kosong)."

    today_str = datetime.now().strftime("%Y-%m-%d")
    
    # Cek agar tidak mengirim dobel di hari yang sama (kecuali force=True)
    if not force and os.path.exists(FILE_LAST_SENT_1530):
        try:
            with open(FILE_LAST_SENT_1530, "r") as f:
                last_data = json.load(f)
                if last_data.get("last_sent_date") == today_str:
                    return False, f"Alert 15:30 untuk hari ini ({today_str}) sudah pernah terkirim."
        except Exception:
            pass

    import pandas as pd
    import tracker_ai
    
    if df_screener is None or df_screener.empty:
        file_hasil = "Database/hasil_screener.csv"
        if os.path.exists(file_hasil):
            try:
                df_screener = pd.read_csv(file_hasil)
            except Exception as e:
                return False, f"Gagal membaca database: {e}"
        else:
            return False, "Database hasil screener belum tersedia."

    hasil_rumus = tracker_ai.filter_saham_9_rumus(df_screener)
    df_r2 = hasil_rumus.get("R2", pd.DataFrame())
    df_r9 = hasil_rumus.get("R9", pd.DataFrame())

    waktu_str = datetime.now().strftime("%d/%m/%Y %H:%M WIB")

    lines = [
        "🦅 <b>REKOMENDASI BELI SORE (BSJP) 15:30 WIB</b>",
        "🎯 <i>Strategi Terakurat: Rumus 2 & Rumus 9</i>",
        f"📅 <i>{waktu_str}</i>",
        "━━━━━━━━━━━━━━━━━━━━"
    ]

    total_emiten = 0
    rekomendasi_list = []

    # Ambil statistik win rate dinamis dari tracker_ai
    wr_r2_str = "Strategi Pilihan (Squeeze + Anomali ML)"
    wr_r9_str = "Strategi Pilihan (Squeeze + Risk/Reward > 1:3)"
    try:
        stats = tracker_ai.hitung_ringkasan_statistik()
        stat_dict = stats.get("stat_per_rumus", {})
        if "R2" in stat_dict and stat_dict["R2"].get("total_evaluasi", 0) > 0:
            wr_r2_str = f"Win Rate Historis: {stat_dict['R2']['win_rate']:.1f}% ({stat_dict['R2']['total_evaluasi']} Teruji)"
        if "R9" in stat_dict and stat_dict["R9"].get("total_evaluasi", 0) > 0:
            wr_r9_str = f"Win Rate Historis: {stat_dict['R9']['win_rate']:.1f}% ({stat_dict['R9']['total_evaluasi']} Teruji)"
    except Exception:
        pass

    # Bagian Rumus 2
    lines.append("🔥 <b>RUMUS 2: SQUEEZE + ANOMALI ML + OBV NAIK</b>")
    lines.append(f"🏆 <i>{html.escape(wr_r2_str)}</i>")
    if not df_r2.empty:
        sort_r2 = df_r2.sort_values(by=["Total Score", "Volume"], ascending=[False, False]) if "Total Score" in df_r2.columns else df_r2
        for idx, (_, row) in enumerate(sort_r2.head(5).iterrows(), 1):
            t = str(row.get("Ticker", "")).strip().upper()
            p = float(row.get("Harga (Rp)", 0))
            score = int(row.get("Total Score", 0)) if pd.notnull(row.get("Total Score")) else 0
            tp = round(p * 1.05)
            cl = round(p * 0.97)
            bintang = "⭐" * min(score, 8)
            plan = row.get("Auto Trading Plan", f"TP Rp {tp:,} (+5%) | CL Rp {cl:,} (-3%)")
            safe_t = html.escape(t)
            safe_plan = html.escape(str(plan))
            lines.append(f"<b>{idx}. #{safe_t}</b> — Rp {p:,.0f} ({bintang})")
            lines.append(f"   🎯 <code>{safe_plan}</code>")
            total_emiten += 1
            rekomendasi_list.append({
                "ticker": t,
                "rumus_id": "R2",
                "rumus_nama": "Rumus 2 (Anomali ML)",
                "harga_entry": p,
                "target_tp": tp,
                "stop_loss": cl,
                "score": score,
                "plan": plan
            })
        if len(df_r2) > 5:
            lines.append(f"   <i>(+{len(df_r2) - 5} emiten lainnya di dashboard)</i>")
    else:
        lines.append("   <i>(Tidak ada emiten lolos filter ketat Rumus 2 sore ini)</i>")

    lines.append("\n━━━━━━━━━━━━━━━━━━━━")

    # Bagian Rumus 9
    lines.append("🎯 <b>RUMUS 9: SQUEEZE + RISK/REWARD > 1:3</b>")
    lines.append(f"🏆 <i>{html.escape(wr_r9_str)}</i>")
    if not df_r9.empty:
        sort_r9 = df_r9.sort_values(by=["Total Score", "Volume"], ascending=[False, False]) if "Total Score" in df_r9.columns else df_r9
        for idx, (_, row) in enumerate(sort_r9.head(5).iterrows(), 1):
            t = str(row.get("Ticker", "")).strip().upper()
            p = float(row.get("Harga (Rp)", 0))
            score = int(row.get("Total Score", 0)) if pd.notnull(row.get("Total Score")) else 0
            tp = round(p * 1.05)
            cl = round(p * 0.97)
            bintang = "⭐" * min(score, 8)
            plan = row.get("Auto Trading Plan", f"TP Rp {tp:,} (+5%) | CL Rp {cl:,} (-3%)")
            safe_t = html.escape(t)
            safe_plan = html.escape(str(plan))
            lines.append(f"<b>{idx}. #{safe_t}</b> — Rp {p:,.0f} ({bintang})")
            lines.append(f"   🎯 <code>{safe_plan}</code>")
            total_emiten += 1
            rekomendasi_list.append({
                "ticker": t,
                "rumus_id": "R9",
                "rumus_nama": "Rumus 9 (Risk/Reward > 1:3)",
                "harga_entry": p,
                "target_tp": tp,
                "stop_loss": cl,
                "score": score,
                "plan": plan
            })
        if len(df_r9) > 5:
            lines.append(f"   <i>(+{len(df_r9) - 5} emiten lainnya di dashboard)</i>")
    else:
        lines.append("   <i>(Tidak ada emiten lolos filter ketat Rumus 9 sore ini)</i>")

    lines.append("\n━━━━━━━━━━━━━━━━━━━━")
    lines.append("⏰ <i>Beli sore 15:30-15:50 WIB sebelum bursa tutup. Pasang jual/TP besok pagi saat open market 09:00 WIB. Disiplin CL jika tembus batas risiko.</i>")

    pesan_final = "\n".join(lines)
    berhasil = kirim_pesan_telegram(pesan_final)
    
    if berhasil:
        try:
            os.makedirs(os.path.dirname(FILE_LAST_SENT_1530), exist_ok=True)
            with open(FILE_LAST_SENT_1530, "w") as f:
                json.dump({
                    "last_sent_date": today_str,
                    "waktu": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "total_emiten": total_emiten,
                    "rekomendasi": rekomendasi_list
                }, f, indent=2)
        except Exception:
            pass
        return True, f"Berhasil mengirim alert rekomendasi Rumus 2 & 9 ({total_emiten} saham)."
    else:
        return False, "Gagal mengirim pesan ke Telegram API."

def cek_dan_kirim_jadwal_1530(df_screener=None, now=None):
    """
    Pemeriksaan berkala yang dipanggil oleh scheduler:
    Jika hari bursa (Senin-Jumat) dan waktu sudah mencapai >= 15:30 WIB (dan belum lewat 20:00 WIB),
    serta belum pernah kirim hari ini -> kirim otomatis!
    """
    if now is None:
        now = datetime.now()
        
    if now.weekday() >= 5:
        return False, "Bukan hari bursa (Weekend)"
        
    total_minutes = now.hour * 60 + now.minute
    target_start = 15 * 60 + 30 # 15:30 WIB
    target_end = 20 * 60 + 0    # 20:00 WIB (Fleksibel hingga malam hari bursa jika PC/aplikasi baru aktif)
    
    if target_start <= total_minutes <= target_end:
        return kirim_rekomendasi_rumus_2_dan_9(df_screener=df_screener, force=False)
    if total_minutes < target_start:
        return False, "Belum jam 15:30 WIB"
    return False, "Lewat jam 20:00 WIB"

def _ambil_data_realtime_emiten(tickers: list, df_screener=None) -> dict:
    """
    Mengambil harga real-time, Open, High, dan Low untuk daftar ticker.
    Menggunakan kombinasi screener database lokal dan Yahoo Finance (yfinance).
    """
    import numpy as np
    import pandas as pd
    
    data_lookup = {}
    
    # 1. Dari df_screener atau file lokal hasil_screener.csv
    if df_screener is None or df_screener.empty:
        file_hasil = "Database/hasil_screener.csv"
        if os.path.exists(file_hasil):
            try:
                df_screener = pd.read_csv(file_hasil)
            except Exception:
                pass

    if df_screener is not None and not df_screener.empty and "Ticker" in df_screener.columns:
        for _, row in df_screener.iterrows():
            tkr = str(row.get("Ticker", "")).strip().upper()
            if tkr in tickers:
                p = float(row.get("Harga (Rp)", 0))
                h = float(row.get("High", row.get("Resistance", p)))
                o = float(row.get("Open", p))
                l = float(row.get("Low", row.get("Support", p)))
                data_lookup[tkr] = {
                    "price": p,
                    "open": o,
                    "high": max(h, p),
                    "low": l if l > 0 else p
                }

    # 2. Ambil update live intraday via yfinance (satu kali batch download cepat)
    if tickers:
        try:
            import yfinance as yf
            symbols = [f"{t}.JK" for t in tickers]
            df_yf = yf.download(symbols, period="2d", progress=False)
            if not df_yf.empty:
                for t in tickers:
                    sym = f"{t}.JK"
                    try:
                        if len(symbols) == 1:
                            c = float(df_yf["Close"].iloc[-1])
                            h = float(df_yf["High"].iloc[-1])
                            o = float(df_yf["Open"].iloc[-1])
                            l = float(df_yf["Low"].iloc[-1])
                        else:
                            c = float(df_yf["Close"][sym].iloc[-1])
                            h = float(df_yf["High"][sym].iloc[-1])
                            o = float(df_yf["Open"][sym].iloc[-1])
                            l = float(df_yf["Low"][sym].iloc[-1])
                        
                        if not np.isnan(c) and c > 0:
                            prev_high = data_lookup.get(t, {}).get("high", 0)
                            data_lookup[t] = {
                                "price": c,
                                "open": o,
                                "high": max(h, prev_high, c),
                                "low": l if (not np.isnan(l) and l > 0) else c
                            }
                    except Exception:
                        pass
        except Exception:
            pass

    return data_lookup

def kirim_update_realtime_pagi_1000(df_screener=None, force=False) -> tuple[bool, str]:
    """
    Mengirimkan update harga realtime daftar saham BSJP (Rumus 2 & Rumus 9)
    yang dikirim pada hari/sore sebelumnya ke bot Telegram pada jam 10:00 WIB.
    """
    if not is_telegram_configured():
        return False, "Bot Telegram belum terkonfigurasi (Token/Chat ID kosong)."

    today_str = datetime.now().strftime("%Y-%m-%d")

    # Cek apakah sudah pernah kirim update pagi hari ini
    if not force and os.path.exists(FILE_LAST_SENT_1000):
        try:
            with open(FILE_LAST_SENT_1000, "r") as f:
                last_data = json.load(f)
                last_sent_date = last_data.get("last_sent_date")
                last_waktu = last_data.get("waktu", "")
                if last_sent_date == today_str:
                    # Alert 10:00 WIB bursa hanya dianggap 'sudah terkirim' jika dikirim pada jam bursa (>= 09:50 WIB)
                    if last_waktu:
                        try:
                            dt_sent = datetime.strptime(last_waktu, "%Y-%m-%d %H:%M:%S")
                            if (dt_sent.hour * 60 + dt_sent.minute) >= (9 * 60 + 50):
                                return False, f"Update realtime 10:00 WIB hari ini ({today_str}) sudah pernah terkirim pukul {dt_sent.strftime('%H:%M')} WIB."
                        except Exception:
                            return False, f"Update realtime 10:00 WIB hari ini ({today_str}) sudah pernah terkirim."
                    else:
                        return False, f"Update realtime 10:00 WIB hari ini ({today_str}) sudah pernah terkirim."
        except Exception:
            pass

    import pandas as pd
    import tracker_ai

    rekomendasi = []
    tgl_rekomendasi = "Kemarin Sore"

    # 1. Ambil dari catatan pengiriman 15:30 WIB terakhir (pastikan dari sesi sore kemarin/sebelumnya)
    if os.path.exists(FILE_LAST_SENT_1530):
        try:
            with open(FILE_LAST_SENT_1530, "r") as f:
                data_1530 = json.load(f)
                tgl_sent = data_1530.get("last_sent_date", "")
                wkt_sent = data_1530.get("waktu", "")
                is_valid_kemarin = False
                if tgl_sent and tgl_sent < today_str:
                    is_valid_kemarin = True
                elif wkt_sent:
                    try:
                        dt_w = datetime.strptime(wkt_sent, "%Y-%m-%d %H:%M:%S")
                        # Jika dikirim sebelum jam 09:00 hari ini, berarti itu emiten sesi sore sebelumnya
                        if dt_w.date() < datetime.now().date() or dt_w.hour < 9:
                            is_valid_kemarin = True
                    except Exception:
                        pass
                
                if (is_valid_kemarin or force) and data_1530.get("rekomendasi"):
                    rekomendasi = data_1530["rekomendasi"]
                    tgl_rekomendasi = tgl_sent if tgl_sent and tgl_sent < today_str else "Kemarin Sore"
        except Exception:
            pass

    # 2. Fallback: Ambil dari tracker_rekomendasi_ai.json untuk tanggal trading terakhir (< today_str)
    if not rekomendasi:
        try:
            tracker_data = tracker_ai.load_tracker_data()
            dates = sorted(list(set(x.get("tanggal", "") for x in tracker_data if x.get("tanggal"))))
            past_dates = [d for d in dates if d < today_str]
            target_date = past_dates[-1] if past_dates else (dates[-1] if dates else None)
            
            if target_date:
                tgl_rekomendasi = target_date
                items_hari_itu = [x for x in tracker_data if x.get("tanggal") == target_date and x.get("rumus_id") in ["R2", "R9"]]
                jam_tersedia = sorted(list(set(x.get("jam", "") for x in items_hari_itu)), reverse=True)
                jam_sore = [j for j in jam_tersedia if j >= "14:00"]
                jam_target = jam_sore[0] if jam_sore else (jam_tersedia[0] if jam_tersedia else "")
                
                sudah_ada = set()
                for item in items_hari_itu:
                    if jam_target and item.get("jam") != jam_target and len(sudah_ada) >= 5:
                        continue
                    tkr = str(item.get("ticker", "")).strip().upper()
                    if tkr and tkr not in sudah_ada:
                        sudah_ada.add(tkr)
                        p = float(item.get("harga_entry", 0))
                        tp = round(p * 1.05)
                        cl = round(p * 0.97)
                        rid = item.get("rumus_id", "R9")
                        rnama = "Rumus 2 (Anomali ML)" if rid == "R2" else "Rumus 9 (Risk/Reward > 1:3)"
                        rekomendasi.append({
                            "ticker": tkr,
                            "rumus_id": rid,
                            "rumus_nama": rnama,
                            "harga_entry": p,
                            "target_tp": tp,
                            "stop_loss": cl,
                            "score": item.get("skor_quant", 0),
                            "plan": f"TP Rp {tp:,} (+5%) | CL Rp {cl:,} (-3%)"
                        })
        except Exception:
            pass

    # 3. Fallback kedua: Jika masih kosong (misal database baru direset), ambil dari screener aktif
    if not rekomendasi:
        if df_screener is None or df_screener.empty:
            file_hasil = "Database/hasil_screener.csv"
            if os.path.exists(file_hasil):
                try:
                    df_screener = pd.read_csv(file_hasil)
                except Exception:
                    pass
        if df_screener is not None and not df_screener.empty:
            hasil_rumus = tracker_ai.filter_saham_9_rumus(df_screener)
            for rid, rnama in [("R2", "Rumus 2 (Anomali ML)"), ("R9", "Rumus 9 (Risk/Reward > 1:3)")]:
                df_sub = hasil_rumus.get(rid, pd.DataFrame())
                for _, r in df_sub.head(3).iterrows():
                    t = str(r.get("Ticker", "")).strip().upper()
                    p = float(r.get("Harga (Rp)", 0))
                    tp = round(p * 1.05)
                    cl = round(p * 0.97)
                    rekomendasi.append({
                        "ticker": t,
                        "rumus_id": rid,
                        "rumus_nama": rnama,
                        "harga_entry": p,
                        "target_tp": tp,
                        "stop_loss": cl,
                        "score": int(r.get("Total Score", 0)) if pd.notnull(r.get("Total Score")) else 0,
                        "plan": r.get("Auto Trading Plan", f"TP Rp {tp:,} (+5%) | CL Rp {cl:,} (-3%)")
                    })

    if not rekomendasi:
        return False, "Tidak ditemukan daftar saham BSJP yang direkomendasikan pada sesi sebelumnya."

    # Ambil data harga realtime terkini
    tickers = list(set(item["ticker"] for item in rekomendasi if item.get("ticker")))
    market_data = _ambil_data_realtime_emiten(tickers, df_screener=df_screener)

    waktu_str = datetime.now().strftime("%d/%m/%Y %H:%M WIB")
    lines = [
        "🌅 <b>UPDATE REALTIME BSJP PAGI (10:00 WIB)</b>",
        f"📊 <i>Realisasi Saham Rekomendasi Sore ({tgl_rekomendasi})</i>",
        f"📅 <i>{waktu_str}</i>",
        "━━━━━━━━━━━━━━━━━━━━"
    ]

    r2_items = [x for x in rekomendasi if x.get("rumus_id") == "R2"]
    r9_items = [x for x in rekomendasi if x.get("rumus_id") == "R9"]
    lain_items = [x for x in rekomendasi if x.get("rumus_id") not in ["R2", "R9"]]

    def _render_kelompok(judul: str, items: list):
        if not items:
            return
        lines.append(f"\n{judul}")
        for idx, item in enumerate(items, 1):
            tkr = item["ticker"]
            entry = float(item.get("harga_entry", 0))
            quote = market_data.get(tkr, {})
            
            cur_price = quote.get("price", entry)
            high_price = max(quote.get("high", cur_price), cur_price)
            
            # Hitung gain
            if entry > 0:
                cur_gain = ((cur_price - entry) / entry) * 100
                max_gain = ((high_price - entry) / entry) * 100
            else:
                cur_gain = 0.0
                max_gain = 0.0

            # Badge status performa pagi
            if max_gain >= 1.5 or cur_gain >= 1.5:
                status_str = f"🚀 <b>CUAN (Peak High: {max_gain:+.2f}%)</b>"
            elif cur_gain >= -1.0:
                status_str = f"⚖️ <b>STABIL / BEP ({cur_gain:+.2f}%)</b>"
            else:
                status_str = f"🩸 <b>WASPADA CL ({cur_gain:+.2f}%)</b>"

            tp_target = item.get("target_tp", round(entry * 1.05))
            cl_target = item.get("stop_loss", round(entry * 0.97))

            lines.append(f"<b>{idx}. #{tkr}</b> (Beli: Rp {entry:,.0f})")
            lines.append(f"   💰 <b>Sekarang:</b> Rp {cur_price:,.0f} ({cur_gain:+.2f}%)")
            lines.append(f"   🏔️ <b>High Sesi 1:</b> Rp {high_price:,.0f} ({max_gain:+.2f}%)")
            lines.append(f"   🎯 <code>Target: TP Rp {tp_target:,} | CL Rp {cl_target:,}</code>")
            lines.append(f"   📊 <b>Status:</b> {status_str}")

    if r2_items:
        _render_kelompok("🔥 <b>RUMUS 2: SQUEEZE + ANOMALI ML + OBV</b>", r2_items)
    if r9_items:
        _render_kelompok("🎯 <b>RUMUS 9: SQUEEZE + RISK/REWARD > 1:3</b>", r9_items)
    if lain_items:
        _render_kelompok("⚡ <b>REKOMENDASI BSJP LAINNYA</b>", lain_items)

    lines.append("\n━━━━━━━━━━━━━━━━━━━━")
    lines.append("💡 <i>Panduan Sesi 1: Jika sudah mencapai target TP (+1.5% s/d +5.0%), amankan profit bertahap (taking profit). Pasang trailing stop atau disiplin cut loss bila harga tembus batas risiko.</i>")

    pesan_final = "\n".join(lines)
    berhasil = kirim_pesan_telegram(pesan_final)

    if berhasil:
        try:
            os.makedirs(os.path.dirname(FILE_LAST_SENT_1000), exist_ok=True)
            with open(FILE_LAST_SENT_1000, "w") as f:
                json.dump({
                    "last_sent_date": today_str,
                    "waktu": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "total_emiten": len(rekomendasi),
                    "tgl_rekomendasi_asal": tgl_rekomendasi
                }, f, indent=2)
        except Exception:
            pass
        return True, f"Berhasil mengirim update realtime 10:00 WIB ({len(rekomendasi)} saham dipantau)."
    else:
        return False, "Gagal mengirim pesan ke Telegram API."

def cek_dan_kirim_jadwal_1000(df_screener=None, now=None):
    """
    Pemeriksaan berkala yang dipanggil oleh scheduler:
    Jika hari bursa (Senin-Jumat) dan waktu sudah mencapai 10:00 WIB (s/d 10:15 WIB),
    serta belum pernah kirim update pagi hari ini -> kirim otomatis!
    """
    if now is None:
        now = datetime.now()

    if now.weekday() >= 5:
        return False, "Bukan hari bursa (Weekend)"

    total_minutes = now.hour * 60 + now.minute
    target_start = 9 * 60 + 55   # 09:55 WIB
    target_end = 12 * 60 + 30   # 12:30 WIB (Sepanjang Sesi 1 Bursa s/d istirahat siang)

    if target_start <= total_minutes <= target_end:
        return kirim_update_realtime_pagi_1000(df_screener=df_screener, force=False)
    return False, "Di luar jam Sesi 1 bursa (09:55 - 12:30 WIB)"

def kirim_alert_screener_fundamental_jumat(df_lolos=None, force=False):
    """
    Mengirimkan laporan saham yang lolos screener fundamental 12 kriteria (Jumat malam 20:00 WIB).
    """
    from screener_fundamental_jumat import kirim_hasil_ke_telegram
    return kirim_hasil_ke_telegram(df_lolos=df_lolos, force=force)

def cek_dan_kirim_jadwal_jumat_2000(now=None, force=False):
    """
    Pemeriksaan berkala yang dipanggil oleh scheduler:
    Jika hari Jumat (now.weekday() == 4) dan waktu sudah mencapai 20:00 WIB (s/d 23:59 WIB),
    serta belum pernah kirim hari ini -> jalankan screener fundamental seluruh emiten dan kirim ke Telegram!
    """
    if now is None:
        now = datetime.now()

    # 4 = Jumat
    if now.weekday() != 4 and not force:
        return False, "Bukan hari Jumat (Jadwal evaluasi hanya setiap Jumat malam 20:00 WIB)"

    total_minutes = now.hour * 60 + now.minute
    target_start = 20 * 60  # 20:00 WIB

    if total_minutes >= target_start or force:
        return kirim_alert_screener_fundamental_jumat(force=force)
    return False, "Belum mencapai jam 20:00 WIB"


