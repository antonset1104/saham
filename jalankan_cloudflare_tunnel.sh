#!/bin/bash
# ==============================================================================
# SCRIPT CLOUDFLARE TUNNEL (MACOS / LINUX)
# Membuka akses publik HTTPS aman untuk AlgoTrade Screener IHSG
# ==============================================================================
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR" || exit 1

# Load .env jika ada
if [ -f ".env" ]; then
    set -a
    source .env
    set +a
fi

# Cari binary cloudflared
if [ -f "./cloudflared" ]; then
    CF_BIN="./cloudflared"
elif command -v cloudflared >/dev/null 2>&1; then
    CF_BIN="cloudflared"
else
    echo "⚠️ Binary cloudflared belum ditemukan. Mengunduh versi macOS terbaru..."
    curl -fsSL https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-darwin-amd64.tgz -o cloudflared.tgz
    tar -xzf cloudflared.tgz
    rm -f cloudflared.tgz
    chmod +x cloudflared
    CF_BIN="./cloudflared"
    echo "✅ cloudflared berhasil diunduh."
fi

mkdir -p Logs

echo "====================================================================="
echo "   CLOUDFLARE TUNNEL - ALGOTRADE SCREENER IHSG"
echo "====================================================================="
echo "Port Target Lokal : http://localhost:8501"

if [ -n "$CLOUDFLARE_TUNNEL_TOKEN" ]; then
    echo "Metode            : Named Tunnel (Zero Trust Token)"
    echo "====================================================================="
    "$CF_BIN" tunnel run --token "$CLOUDFLARE_TUNNEL_TOKEN"
else
    echo "Metode            : Quick Tunnel (Gratis Tanpa Domain / Setup)"
    echo "====================================================================="
    echo "⏳ Menghubungkan ke Cloudflare Edge..."
    "$CF_BIN" tunnel --url http://localhost:8501
fi
