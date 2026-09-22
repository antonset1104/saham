#!/bin/bash
# ==============================================================================
# SCRIPT SCREENER FUNDAMENTAL JUMAT MALAM (20:00 WIB)
# Mengevaluasi seluruh saham listing di BEI dengan 12 kriteria Stockbit
# dan mengirimkan laporannya ke bot Telegram.
# ==============================================================================
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR" || exit 1

mkdir -p Database
echo "[$(date '+%Y-%m-%d %H:%M:%S')] 🚀 Memulai Screener Fundamental Jumat Malam 20:00 WIB..." >> Database/screener_jumat.log
./.venv/bin/python screener_fundamental_jumat.py --kirim-telegram >> Database/screener_jumat.log 2>&1
echo "[$(date '+%Y-%m-%d %H:%M:%S')] ✅ Screener Fundamental Jumat selesai." >> Database/screener_jumat.log
