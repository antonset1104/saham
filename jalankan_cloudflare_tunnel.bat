@echo off
TITLE Cloudflare Tunnel - AlgoTrade Screener IHSG
COLOR 0A

echo =====================================================================
echo    CLOUDFLARE TUNNEL - ALGOTRADE SCREENER IHSG (WINDOWS)
echo =====================================================================
echo.

cd /d "%~dp0"

:: Cek apakah cloudflared.exe ada
if not exist "cloudflared.exe" (
    echo [INFO] Mengunduh cloudflared.exe resmi dari Cloudflare...
    curl -fsSL https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe -o cloudflared.exe
    echo [OK] Selesai mengunduh cloudflared.exe
)

:: Cek apakah token disetel di file .env
set TOKEN=
if exist ".env" (
    for /f "usebackq tokens=1,2 delims==" %%A in (".env") do (
        if "%%A"=="CLOUDFLARE_TUNNEL_TOKEN" set TOKEN=%%B
    )
)

if not "%TOKEN%"=="" (
    echo [METODE] Menggunakan Cloudflare Named Tunnel Token
    cloudflared.exe tunnel run --token %TOKEN%
) else (
    echo [METODE] Menggunakan Quick Tunnel (Gratis, URL Publik Otomatis)
    echo Buka URL *.trycloudflare.com yang muncul di bawah ini dari HP Anda:
    echo.
    cloudflared.exe tunnel --url http://localhost:8501
)

pause
