#!/bin/bash
# ==============================================================================
# SCRIPT PENJADWAL PER JAM BURSA IHSG
# Menjalankan update seluruh saham IHSG, bot simulator, dan evaluasi tracker AI
# ==============================================================================
DIR="/Users/antonsetiawan/Documents/website/saham"
cd "$DIR" || exit 1

mkdir -p Database
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Memulai siklus scheduler per jam..." >> Database/scheduler_cron.log
./.venv/bin/python scheduler_per_jam.py --run-once >> Database/scheduler_cron.log 2>&1
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Siklus selesai." >> Database/scheduler_cron.log
