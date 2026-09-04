import os
import sys
import time
import json
import signal
import subprocess
from datetime import datetime, timedelta

FILE_STATUS = "Database/scheduler_status.json"
FILE_CONTROL = "Database/scheduler_control.json"

def is_market_hours(now=None):
    """
    Mengecek apakah saat ini merupakan jam perdagangan bursa efek Indonesia (WIB).
    Senin - Jumat:
      Sesi 1: 08:55 - 12:05 WIB (Jumat: 08:55 - 11:35 WIB)
      Sesi 2: 13:25 - 16:15 WIB (Jumat: 13:55 - 16:15 WIB)
    """
    if now is None:
        now = datetime.now()
    
    # 0 = Senin, 4 = Jumat, 5 = Sabtu, 6 = Minggu
    if now.weekday() >= 5:
        return False
        
    hour = now.hour
    minute = now.minute
    total_minutes = hour * 60 + minute
    
    # Jumat
    if now.weekday() == 4:
        sesi1 = (8 * 60 + 55) <= total_minutes <= (11 * 60 + 35)
        sesi2 = (13 * 60 + 55) <= total_minutes <= (16 * 60 + 15)
        return sesi1 or sesi2
    else:
        # Senin - Kamis
        sesi1 = (8 * 60 + 55) <= total_minutes <= (12 * 60 + 5)
        sesi2 = (13 * 60 + 25) <= total_minutes <= (16 * 60 + 15)
        return sesi1 or sesi2

def update_scheduler_status(is_running=False, pid=None, last_status="Siap", last_run=None, next_run=None):
    """Menyimpan status detak jantung (heartbeat) scheduler ke JSON."""
    os.makedirs(os.path.dirname(FILE_STATUS), exist_ok=True)
    status_data = {
        "is_running": is_running,
        "pid": pid,
        "last_status": last_status,
        "last_run": last_run or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "next_run": next_run or (datetime.now() + timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S"),
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    with open(FILE_STATUS, "w") as f:
        json.dump(status_data, f, indent=2)

def get_scheduler_status():
    """Mengambil status scheduler saat ini."""
    if not os.path.exists(FILE_STATUS):
        return {
            "is_running": False,
            "pid": None,
            "last_status": "Belum pernah dijalankan",
            "last_run": "-",
            "next_run": "-",
            "updated_at": "-"
        }
    try:
        with open(FILE_STATUS, "r") as f:
            data = json.load(f)
            # Verifikasi apakah proses dengan PID tersebut benar-benar masih hidup
            pid = data.get("pid")
            if pid and data.get("is_running"):
                try:
                    os.kill(pid, 0)
                except OSError:
                    data["is_running"] = False
                    data["last_status"] = "Proses berhenti secara eksternal"
            return data
    except Exception:
        return {"is_running": False, "last_status": "Error membaca status"}

def jalankan_satu_siklus(limit=None):
    """
    Menjalankan satu siklus pembaruan pasar lengkap:
    1. update_data.py (Scraping Stockbit & kalkulasi teknikal + pemicu tracker_ai)
    2. bot_simulator.py (Eksekusi transaksi virtual bot BSJP)
    """
    py_bin = sys.executable or "./.venv/bin/python"
    waktu_mulai = datetime.now()
    
    cmd_update = [py_bin, "update_data.py"]
    if limit:
        cmd_update.extend(["--limit", str(limit)])
        
    print(f"🔄 [{waktu_mulai.strftime('%H:%M:%S')}] Memulai eksekusi update_data.py...")
    res_update = subprocess.run(cmd_update, capture_output=True, text=True)
    
    # Jalankan bot simulator
    cmd_bot = [py_bin, "bot_simulator.py"]
    print(f"🤖 [{datetime.now().strftime('%H:%M:%S')}] Memulai eksekusi bot_simulator.py...")
    res_bot = subprocess.run(cmd_bot, capture_output=True, text=True)
    
    # 3. Kirim alert BSJP 15:30 WIB otomatis jika jadwal tiba
    try:
        from notifikasi_telegram import cek_dan_kirim_jadwal_1530
        sukses_tg, msg_tg = cek_dan_kirim_jadwal_1530()
        if sukses_tg:
            print(f"📲 [15:30 WIB] Alert Telegram BSJP Rumus 2 & 9 terkirim: {msg_tg}")
    except Exception as e_tg:
        pass

    # 4. Kirim update realtime BSJP 10:00 WIB otomatis jika jadwal tiba
    try:
        from notifikasi_telegram import cek_dan_kirim_jadwal_1000
        sukses_10, msg_10 = cek_dan_kirim_jadwal_1000()
        if sukses_10:
            print(f"📲 [10:00 WIB] Alert Telegram Realtime BSJP terkirim: {msg_10}")
    except Exception as e_10:
        pass
    
    durasi = (datetime.now() - waktu_mulai).total_seconds()
    status_msg = f"Selesai dalam {durasi:.1f} detik" if res_update.returncode == 0 else f"Gagal: {res_update.stderr[:100]}"
    
    return res_update.returncode == 0, status_msg

def start_scheduler_daemon():
    """Memulai proses background daemon dari scheduler."""
    status = get_scheduler_status()
    if status.get("is_running"):
        return False, f"Scheduler sudah aktif dengan PID {status.get('pid')}"
        
    py_bin = sys.executable or "./.venv/bin/python"
    script_path = os.path.abspath(__file__)
    
    with open(FILE_CONTROL, "w") as f:
        json.dump({"active": True}, f)
        
    # Jalankan sebagai subprocess mandiri yang terpisah (detached session)
    proc = subprocess.Popen(
        [py_bin, script_path, "--run-loop"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True
    )
    
    pid = proc.pid
    with open(FILE_CONTROL, "w") as f:
        json.dump({"active": True, "pid": pid}, f)
        
    update_scheduler_status(is_running=True, pid=pid, last_status="Scheduler dimulai, mengecek jam pasar...")
    return True, f"Scheduler berhasil dimulai (PID: {pid})"

def stop_scheduler_daemon():
    """Menghentikan background scheduler."""
    status = get_scheduler_status()
    pid = status.get("pid")
    
    if os.path.exists(FILE_CONTROL):
        try: os.remove(FILE_CONTROL)
        except: pass
        
    if pid:
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass
            
    update_scheduler_status(is_running=False, pid=None, last_status="Scheduler dihentikan pengguna")
    return True, "Scheduler berhasil dihentikan."

def loop_scheduler_utama():
    """Loop utama scheduler yang berjalan setiap jam."""
    pid = os.getpid()
    print(f"🚀 Scheduler daemon per jam berjalan (PID: {pid})...")
    
    last_run_dt = None
    st_old = get_scheduler_status()
    if st_old.get("last_run") and st_old.get("last_run") != "-":
        try:
            last_run_dt = datetime.strptime(st_old["last_run"], "%Y-%m-%d %H:%M:%S")
        except:
            pass
            
    update_scheduler_status(is_running=True, pid=pid, last_status="Aktif memantau jam pasar")
    
    # Tangani sinyal penghentian
    def sig_handler(signum, frame):
        print("🛑 Menerima sinyal berhenti. Menutup daemon...")
        update_scheduler_status(is_running=False, pid=None, last_status="Dihentikan")
        sys.exit(0)
        
    signal.signal(signal.SIGTERM, sig_handler)
    signal.signal(signal.SIGINT, sig_handler)
    
    while True:
        # Cek apakah kontrol file masih ada
        if not os.path.exists(FILE_CONTROL):
            print("🛑 File kontrol tidak ditemukan. Keluar...")
            break
            
        now = datetime.now()
        next_hour = (now + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
        
        # Cek apakah perlu run:
        # 1. Saat ini dalam jam bursa IDX
        # 2. Belum pernah run, ATAU tanggal last_run < hari ini, ATAU jam bursa baru berganti, ATAU jeda >= 55 menit
        perlu_run = False
        if is_market_hours(now):
            if last_run_dt is None:
                perlu_run = True
            elif last_run_dt.date() < now.date():
                perlu_run = True
            elif (now.hour != last_run_dt.hour) and ((now - last_run_dt).total_seconds() >= 1500):
                perlu_run = True
            elif (now - last_run_dt).total_seconds() >= 3300: # 55 menit
                perlu_run = True
                
        if perlu_run:
            print(f"🔔 [{now.strftime('%Y-%m-%d %H:%M:%S')}] Waktu pasar tiba! Menjalankan update per jam...")
            update_scheduler_status(is_running=True, pid=pid, last_status="Sedang memperbarui seluruh IHSG...")
            
            sukses, pesan = jalankan_satu_siklus()
            last_run_dt = datetime.now()
            
            status_text = f"Sukses update jam {last_run_dt.strftime('%H:%M')} WIB ({pesan})" if sukses else f"Gagal update: {pesan}"
            update_scheduler_status(
                is_running=True, 
                pid=pid, 
                last_status=status_text,
                last_run=last_run_dt.strftime("%Y-%m-%d %H:%M:%S"),
                next_run=next_hour.strftime("%Y-%m-%d %H:%M:%S")
            )
        else:
            if not is_market_hours(now):
                ket = "Di luar jam bursa IDX (Menunggu sesi berikutnya)"
            else:
                sisa_menit = int((3600 - (now - last_run_dt).total_seconds()) / 60) if last_run_dt else 0
                ket = f"Menunggu jadwal jam berikutnya (~{max(1, sisa_menit)} menit lagi)"
                
            update_scheduler_status(
                is_running=True, 
                pid=pid, 
                last_status=ket,
                last_run=last_run_dt.strftime("%Y-%m-%d %H:%M:%S") if last_run_dt else "-",
                next_run=next_hour.strftime("%Y-%m-%d %H:%M:%S")
            )
            
        # Periksa setiap 15 detik agar responsif saat komputer bangun dari sleep atau dimatikan dari web
        for _ in range(4): # 4 x 15s = 60s
            if not os.path.exists(FILE_CONTROL):
                break
            # Pengecekan berkala pemicu alert BSJP jam 15:30 WIB
            now_cek = datetime.now()
            if now_cek.weekday() < 5 and now_cek.hour == 15 and now_cek.minute >= 30:
                try:
                    from notifikasi_telegram import cek_dan_kirim_jadwal_1530
                    cek_dan_kirim_jadwal_1530()
                except Exception:
                    pass

            # Pengecekan berkala pemicu update realtime BSJP pagi (09:55 - 11:45 WIB)
            if now_cek.weekday() < 5 and (now_cek.hour == 10 or (now_cek.hour == 9 and now_cek.minute >= 55) or (now_cek.hour == 11 and now_cek.minute <= 45)):
                try:
                    from notifikasi_telegram import cek_dan_kirim_jadwal_1000
                    cek_dan_kirim_jadwal_1000()
                except Exception:
                    pass
            time.sleep(15)

    update_scheduler_status(is_running=False, pid=None, last_status="Daemon selesai")

if __name__ == "__main__":
    if "--run-loop" in sys.argv:
        loop_scheduler_utama()
    elif "--start" in sys.argv:
        _, msg = start_scheduler_daemon()
        print(msg)
    elif "--stop" in sys.argv:
        _, msg = stop_scheduler_daemon()
        print(msg)
    elif "--run-once" in sys.argv:
        print("Menjalankan satu siklus sekarang...")
        sukses, msg = jalankan_satu_siklus()
        print("Hasil:", msg)
    else:
        st = get_scheduler_status()
        print("Status Scheduler:", st)
