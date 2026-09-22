#!/bin/bash
# ==============================================================================
# SCRIPT UTAMA ALGOTRADE SCREENER & SCHEDULER (MACOS)
# Menjalankan Scheduler Daemon per jam dan Web Server Streamlit di port 8501
# ==============================================================================
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR" || exit 1

mkdir -p Logs Database

echo "====================================================================="
echo "       MENJALANKAN ALGOTRADE SCREENER & SCHEDULER (MACOS)"
echo "====================================================================="
echo ""

# 1. Menyalakan Background Scheduler Daemon
echo "[1/2] Menyalakan Scheduler Latar Belakang (Per Jam, BSJP 15:30, Jumat 20:00)..."
./.venv/bin/python scheduler_per_jam.py --start

# 2. Menyalakan Streamlit Web Server
echo "[2/2] Menyalakan Web Server Streamlit di http://localhost:8501..."
echo "====================================================================="
echo "  Web lokal: http://localhost:8501"
echo "  Untuk membuka akses publik via Cloudflare Tunnel, jalankan:"
echo "    ./jalankan_cloudflare_tunnel.sh"
echo "  Untuk menghentikan web, tekan CTRL+C"
echo "====================================================================="
echo ""

./.venv/bin/streamlit run app.py --server.port 8501 --server.headless true --server.enableCORS false --server.enableXsrfProtection false
