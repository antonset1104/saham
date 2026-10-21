@echo off
TITLE AlgoTrade Screener - Server & Scheduler (Port 8501)
COLOR 0B

echo =====================================================================
echo       MENJALANKAN ALGOTRADE SCREENER & SCHEDULER (WINDOWS 11)
echo =====================================================================
echo.

cd /d "%~dp0"

:: Cek apakah .venv ada
if not exist ".venv\Scripts\activate.bat" (
    echo [PERINGATAN] Virtual environment .venv belum ditemukan.
    echo Menjalankan setup_windows.bat terlebih dahulu...
    call setup_windows.bat
)

call .venv\Scripts\activate.bat

:: Buat folder logs & database
if not exist "Logs" mkdir Logs
if not exist "Database" mkdir Database

echo [1/2] Menyalakan Scheduler Latar Belakang (Per Jam dan Riset EOD 17:45 WIB)...
.venv\Scripts\python.exe scheduler_per_jam.py --start

echo [2/2] Menyalakan Web Server Streamlit di http://localhost:8501...
echo.
echo =====================================================================
echo  Web aktif di: http://localhost:8501
echo  Untuk menutup server, tekan CTRL+C atau tutup jendela ini.
echo =====================================================================
echo.

.venv\Scripts\streamlit.exe run app.py --server.port 8501 --server.headless true
