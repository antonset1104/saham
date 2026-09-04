@echo off
TITLE Setup AlgoTrade Screener - Windows 11
COLOR 0A

echo =====================================================================
echo       SETUP ENVIRONMENT ALGOTRADE SCREENER (WINDOWS 11)
echo =====================================================================
echo.

cd /d "%~dp0"

echo [1/3] Memeriksa instalasi Python...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python tidak ditemukan!
    echo Silakan install Python 3.10 / 3.11 / 3.12 dari python.org
    echo PENTING: Centang kotak "Add Python to PATH" saat instalasi.
    pause
    exit /b 1
)
python --version

echo.
echo [2/3] Membuat Virtual Environment Python (.venv)...
if not exist ".venv" (
    python -m venv .venv
    echo Virtual Environment berhasil dibuat di folder .venv
) else (
    echo Virtual Environment .venv sudah ada, melanjutkan...
)

echo.
echo [3/3] Menginstal dependensi library Python dari requirements.txt...
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt

if not exist ".env" (
    if exist ".env.example" (
        copy .env.example .env >nul
        echo File .env contoh telah dibuat. Silakan isi Token Telegram di file .env
    )
)

echo.
echo =====================================================================
echo [SUKSES] Setup selesai!
echo Untuk menjalankan aplikasi dan scheduler, klik dua kali:
echo   - start_saham_windows.bat (Dengan jendela terminal terlihat)
echo   - start_silent_windows.vbs (Berjalan di latar belakang tanpa jendela)
echo =====================================================================
echo.
pause
