#!/bin/bash
set -e

# Resolusi path direktori script secara dinamis (portabel di mesin apa pun)
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd "$SCRIPT_DIR"

echo "⏳ [$(date '+%Y-%m-%d %H:%M:%S')] Memulai pembaruan data saham..."

# Deteksi executable Python yang tersedia
if [ -f "$SCRIPT_DIR/.venv/bin/python" ]; then
    PYTHON_CMD="$SCRIPT_DIR/.venv/bin/python"
elif [ -f "$SCRIPT_DIR/venv/bin/python" ]; then
    PYTHON_CMD="$SCRIPT_DIR/venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
    PYTHON_CMD="python3"
else
    PYTHON_CMD="python"
fi

echo "🐍 Menggunakan Python: $PYTHON_CMD"

# 1. Jalankan update data market & teknikal
"$PYTHON_CMD" update_data.py

# 2. Jalankan bot simulator portofolio
"$PYTHON_CMD" bot_simulator.py

# ==========================================
# FITUR SAPU OTOMATIS ARSIP (Retensi 7 Hari Terakhir)
# ==========================================
if [ -d "Arsip_Data_Harian" ]; then
    find Arsip_Data_Harian/ -name "*.csv" -type f -mtime +7 -delete 2>/dev/null || true
fi

# ==========================================
# CADANGKAN KE GITHUB (JIKA ADA GIT REMOTE)
# ==========================================
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    echo "📤 Sinkronisasi dengan repositori Git..."
    
    # Tarik update terbaru jika remote dikonfigurasi
    if git remote get-url origin >/dev/null 2>&1; then
        git pull origin main --no-rebase 2>/dev/null || true
    fi

    # Simpan hanya file database yang terupdate
    git add Database/*.csv 2>/dev/null || true
    git add Arsip_Data_Harian/*.csv 2>/dev/null || true

    # Commit jika ada perubahan
    if ! git diff --cached --quiet; then
        git commit -m "Auto-update data, arsip, dan bot simulator [$(date '+%Y-%m-%d %H:%M')]" || true
        if git remote get-url origin >/dev/null 2>&1; then
            git push origin main 2>/dev/null || echo "⚠️ Gagal push ke origin main (mungkin offline atau auth ditolak)."
        fi
    else
        echo "ℹ️ Tidak ada perubahan data baru untuk di-commit."
    fi
fi

echo "✅ [$(date '+%Y-%m-%d %H:%M:%S')] Proses 100% Selesai!"