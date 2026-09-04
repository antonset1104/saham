import pandas as pd
import os
from datetime import datetime
import subprocess
from notifikasi_telegram import kirim_alert_transaksi_bot

# ==========================================
# ⚙️ KONFIGURASI BOT SIMULATOR BSJP (9 ARENA)
# ==========================================
MODAL_AWAL = 100000000.0  # Rp 100 Juta per Rumus
FEE_BELI = 0.0015         # 0.15%
FEE_JUAL = 0.0025         # 0.25%
FILE_MARKET = "Database/hasil_screener.csv"
DIR_DB = "Database"       

# ==========================================
# 🛠️ FUNGSI HELPER ATOMIC SAVE & GIT
# ==========================================
def simpan_csv_aman(df, filepath):
    """Menyimpan dataframe secara atomik agar tidak korup saat dibaca bersamaan"""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    tmp_path = f"{filepath}.tmp"
    df.to_csv(tmp_path, index=False)
    os.replace(tmp_path, filepath)

def auto_save_github():
    print("\n🔄 Memulai pencadangan (Auto-Save) permanen ke GitHub...")
    try:
        # Cek apakah repositori git valid
        cek_git = subprocess.run(["git", "rev-parse", "--is-inside-work-tree"], capture_output=True, text=True)
        if cek_git.returncode != 0:
            print("ℹ️ Bukan repositori Git, lewati auto-save GitHub.")
            return

        subprocess.run(["git", "add", "Database/*.csv"], check=False)
        waktu_sekarang = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        pesan_komit = f"🤖 Bot Update Portofolio: {waktu_sekarang}"
        commit_process = subprocess.run(["git", "commit", "-m", pesan_komit], capture_output=True, text=True)
        if "nothing to commit" in commit_process.stdout or "nothing to commit" in commit_process.stderr:
            print("✅ Data aman. Tidak ada transaksi baru.")
            return
        
        push_proc = subprocess.run(["git", "push", "origin", "main"], capture_output=True, text=True)
        if push_proc.returncode == 0:
            print("🚀 Pencadangan berhasil! Data portofolio Anda tersimpan di GitHub.")
        else:
            print(f"⚠️ Git push dilewati / tidak berhasil: {push_proc.stderr.strip()}")
    except Exception as e:
        print(f"❌ Gagal melakukan Auto-Save. Error: {e}")

# ==========================================
# 🛠️ FUNGSI INISIALISASI (BRANKAS 3 LAPIS)
# ==========================================
def inisialisasi_database(rumus_id):
    # Lapis 1: Gudang Aktif (Cabut-Pasang)
    file_porto = os.path.join(DIR_DB, f"portofolio_aktif_rumus_{rumus_id}.csv")
    # Lapis 2: Buku Besar Histori (Catat Abadi)
    file_hist = os.path.join(DIR_DB, f"histori_transaksi_rumus_{rumus_id}.csv")
    
    if not os.path.exists(file_porto):
        pd.DataFrame(columns=['Tanggal_Beli', 'Ticker', 'Harga_Beli', 'Lot', 'Total_Modal', 'Target_TP', 'Target_CL']).to_csv(file_porto, index=False)
        
    if not os.path.exists(file_hist):
        pd.DataFrame(columns=['Tanggal_Beli', 'Tanggal_Jual', 'Ticker', 'Harga_Beli', 'Harga_Jual', 'Status', 'Total_Return_Rp', 'Return_%']).to_csv(file_hist, index=False)
        
    return file_porto, file_hist

def cek_saldo_tersedia(df_porto):
    if df_porto.empty:
        return MODAL_AWAL
    return MODAL_AWAL - df_porto['Total_Modal'].sum()

# ==========================================
# 🤖 MESIN EKSEKUSI UTAMA (MODE BSJP)
# ==========================================
def jalankan_bot():
    now = datetime.now()
    tanggal_hari_ini = now.strftime('%Y-%m-%d')
    jam_sekarang = now.time()
    jam_square_off = datetime.strptime("15:30", "%H:%M").time()
    
    print(f"[{now.strftime('%H:%M:%S')}] Membangunkan Bot Simulator AI...")

    # ----------------------------------------------------
    # 🔒 GEMBOK PAGI: SISTEM PENGAMAN ANTI-HILANG DATA
    # ----------------------------------------------------
    if not os.path.exists(FILE_MARKET):
        print("🔒 GEMBOK AKTIF: File hasil_screener.csv tidak ditemukan. Bot menolak beroperasi agar portofolio aman!")
        return
        
    try:
        df_market = pd.read_csv(FILE_MARKET)
        # Jika file CSV kosong karena update cron gagal / bursa maintenance
        if df_market.empty or 'Ticker' not in df_market.columns or 'Harga (Rp)' not in df_market.columns:
            print("🔒 GEMBOK AKTIF: Data market kosong atau cacat. Bot tidur kembali untuk melindungi data Anda.")
            return
    except Exception as e:
        print(f"🔒 GEMBOK AKTIF: Gagal membaca data market ({e}). Bot tidur kembali.")
        return
    # ----------------------------------------------------

    is_square_off_time = jam_sekarang >= jam_square_off
    if is_square_off_time:
        print("🧹 WAKTU SQUARE OFF / SORE HARI! Evaluasi jual paksa diaktifkan.")

    # MENYAPU RUMUS 1 SAMPAI 9
    for i in range(1, 10):
        file_porto, file_hist = inisialisasi_database(i)
        file_sinyal = os.path.join(DIR_DB, f"sinyal_ai_rumus_{i}.csv")
        
        df_porto = pd.read_csv(file_porto)
        df_history = pd.read_csv(file_hist)
        
        porto_baru = []
        history_baru = []
        
        # ==========================================
        # FASE A: MODE JUAL (CABUT SAHAM DARI GUDANG)
        # ==========================================
        for idx, posisi in df_porto.iterrows():
            ticker = posisi['Ticker']
            tgl_beli_saham = str(posisi['Tanggal_Beli']).split()[0]
            
            # BSJP: Jika beli hari ini, TAHAN! (Tidak Boleh Dijual)
            if tgl_beli_saham == tanggal_hari_ini:
                porto_baru.append(posisi)
                continue

            # Ambil harga terkini, jika sahamnya tidak ditemukan di file market, TAHAN!
            try:
                harga_sekarang = df_market[df_market['Ticker'] == ticker]['Harga (Rp)'].values[0]
            except:
                porto_baru.append(posisi) 
                continue
                
            terjual = False
            status_jual = ""
            harga_jual = 0
            
            # Logika Cek Jual
            if is_square_off_time:
                terjual = True
                status_jual = "AUTO_SQUARE_OFF 🧹"
                harga_jual = harga_sekarang
            elif harga_sekarang >= posisi['Target_TP']:
                terjual = True
                status_jual = "TAKE_PROFIT 🎯"
                harga_jual = harga_sekarang
            elif harga_sekarang <= posisi['Target_CL']:
                terjual = True
                status_jual = "CUT_LOSS ✂️"
                harga_jual = harga_sekarang
                
            # Jika saham terjual, pindahkan ke Buku Histori (Lapis 2)
            if terjual:
                nilai_jual_kotor = harga_jual * posisi['Lot'] * 100
                nilai_jual_bersih = nilai_jual_kotor - (nilai_jual_kotor * FEE_JUAL)
                profit_rp = nilai_jual_bersih - posisi['Total_Modal']
                profit_pct = (profit_rp / posisi['Total_Modal']) * 100
                
                history_baru.append({
                    'Tanggal_Beli': posisi['Tanggal_Beli'],
                    'Tanggal_Jual': now.strftime("%Y-%m-%d %H:%M"),
                    'Ticker': ticker,
                    'Harga_Beli': posisi['Harga_Beli'],
                    'Harga_Jual': harga_jual,
                    'Status': status_jual,
                    'Total_Return_Rp': round(profit_rp, 2),
                    'Return_%': round(profit_pct, 2)
                })
                print(f"💰 [RUMUS {i}] JUAL: {ticker} @ Rp {harga_jual} | {status_jual} | {profit_pct:.2f}%")
                kirim_alert_transaksi_bot(f"Rumus {i}", ticker, "JUAL", harga_jual, int(posisi['Lot']), profit_rp, profit_pct)
            else:
                porto_baru.append(posisi) # Jika tidak dijual, kembalikan ke Gudang (Lapis 1)

        # Update kondisi Lapis 1 & Lapis 2
        df_porto = pd.DataFrame(porto_baru)
        if df_porto.empty: # Jaga-jaga agar struktur tabel tidak rusak jika kosong
            df_porto = pd.DataFrame(columns=['Tanggal_Beli', 'Ticker', 'Harga_Beli', 'Lot', 'Total_Modal', 'Target_TP', 'Target_CL'])
        
        if history_baru:
            df_history = pd.concat([df_history, pd.DataFrame(history_baru)], ignore_index=True)

        # ==========================================
        # FASE B: MODE BELI (MASUKKAN SAHAM KE GUDANG)
        # ==========================================
        if os.path.exists(file_sinyal):
            saldo_sekarang = cek_saldo_tersedia(df_porto)
            saham_dimiliki = df_porto['Ticker'].tolist() if not df_porto.empty else []
            try:
                df_sinyal = pd.read_csv(file_sinyal)
                for _, sinyal in df_sinyal.iterrows():
                    ticker = sinyal['Ticker']
                    # Cegah beli saham yang sama berulang-ulang
                    if ticker in saham_dimiliki:
                        continue
                        
                    try:
                        harga_beli = df_market[df_market['Ticker'] == ticker]['Harga (Rp)'].values[0]
                    except:
                        continue
                    
                    # Maksimal alokasi Rp 20 Juta per saham
                    alokasi_dana = min(20000000, saldo_sekarang)
                    harga_1_lot_plus_fee = (harga_beli * 100) * (1 + FEE_BELI)
                    
                    if alokasi_dana >= harga_1_lot_plus_fee: 
                        jumlah_lot = int(alokasi_dana // harga_1_lot_plus_fee)
                        total_modal_dikeluarkan = jumlah_lot * harga_1_lot_plus_fee
                        
                        df_porto = pd.concat([df_porto, pd.DataFrame([{
                            'Tanggal_Beli': now.strftime("%Y-%m-%d %H:%M"),
                            'Ticker': ticker,
                            'Harga_Beli': harga_beli,
                            'Lot': jumlah_lot,
                            'Total_Modal': total_modal_dikeluarkan,
                            'Target_TP': sinyal['Target_TP'],
                            'Target_CL': sinyal['Target_CL']
                        }])], ignore_index=True)
                        saldo_sekarang -= total_modal_dikeluarkan
                        print(f"🛒 [RUMUS {i}] BELI: {ticker} @ Rp {harga_beli} | {jumlah_lot} Lot")
                        kirim_alert_transaksi_bot(f"Rumus {i}", ticker, "BELI", harga_beli, jumlah_lot)

                # WAJIB: Hapus kertas belanja agar besok tidak dibeli lagi
                os.remove(file_sinyal)
            except Exception as e:
                print(f"⚠️ Gagal membaca sinyal Rumus {i}: {e}")

        # ----------------------------------------------------
        # 💾 SIMPAN SEMUA KE DALAM FILE CSV MASING-MASING SECARA ATOMIK
        # ----------------------------------------------------
        simpan_csv_aman(df_porto, file_porto)
        simpan_csv_aman(df_history, file_hist)

    print("✅ Inspeksi 9 Arena selesai.")
    
    # EKSEKUSI AUTO-SAVE KE GITHUB
    auto_save_github()

if __name__ == "__main__":
    jalankan_bot()