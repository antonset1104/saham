# ⚡ AlgoTrade Screener IHSG & Bot Simulator BSJP

Platform screening kuantitatif saham Bursa Efek Indonesia (IHSG), deteksi bandarmologi & Smart Money, machine learning anomali volume, penilaian kecerdasan buatan (Google Gemini & Groq), serta simulator portofolio trading otomatis berbasis strategi **BSJP (Beli Sore Jual Pagi)**.

---

## 📑 Daftar Isi
- [Fitur Utama](#-fitur-utama)
- [9 Rumus Strategi BSJP](#-9-rumus-strategi-bsjp)
- [Struktur Direktori](#-struktur-direktori)
- [Instalasi & Persiapan](#-instalasi--persiapan)
- [Konfigurasi API (.env)](#-konfigurasi-api-env)
- [Cara Penggunaan](#-cara-penggunaan)
- [Otomasi Cron (Jam Bursa)](#-otomasi-cron-jam-bursa)
- [Pengujian Otomatis (Unit Tests)](#-pengujian-otomatis-unit-tests)

---

## 🌟 Fitur Utama

1. **Analisis Kuantitatif & Bandarmologi Mendalam (45+ Indikator):**
   - **Broker Summary (Broksum):** Integrasi data akumulasi/distribusi bandar dan top 3 broker buyer/seller.
   - **Smart Money Flow:** Analisis *Accumulation/Distribution (A/D)* dan *Money Flow Volume (MFV)*.
   - **On-Balance Volume (OBV):** Deteksi divergensi tren akumulasi tersembunyi.
   - **Karakter Gorengan ("Tiang Jemuran"):** Deteksi probabilitas saham dibanting di pucuk berdasarkan riwayat rasio ekor candlestick.
   - **Kondisi Supply & Demand:** Deteksi *Supply Kering* (rasio volume rendah + volatilitas menyempit sebelum di-pump).
   - **Siklus Pasar Wyckoff:** Kategorisasi otomatis ke fase *Accumulation, Mark-Up, Distribution, Mark-Down,* atau *Sideways*.
   - **Level Fibonacci Otomatis:** Perhitungan level swing high/low dengan deteksi pantulan golden ratio (61.8% / 50.0%).

2. **Machine Learning Anomaly Detection:**
   - Menggunakan algoritma `IsolationForest` dari scikit-learn untuk mendeteksi emiten dengan anomali lonjakan volume dan skor tinggi yang belum mengalami kenaikan harga drastis (*"🔥 ANOMALI BANDAR (Siap Ledakan)"*).

3. **Otak Kecerdasan Buatan (AI Hakim & Turnamen):**
   - **Google Gemini API:** Format output JSON terstruktur untuk menyeleksi 5 saham jawara per rumus dari Top 15 data kuantitatif.
   - **Groq API:** Pemrosesan inferensi berkecepatan tinggi menggunakan model Llama 3.1 / 3.3 (70B) & DeepSeek untuk analisis forensik DNA saham sebelum ARA.

4. **Simulator Portofolio 9 Arena (Paper Trading BSJP):**
   - Modal awal Rp 100.000.000 per rumus (Total Rp 900 Juta untuk 9 arena).
   - Memperhitungkan fee beli (0.15%) dan fee jual (0.25%).
   - Sistem Brankas 3 Lapis:
     - **Lapis 1:** Portofolio Aktif (gudang saham yang sedang di-hold).
     - **Lapis 2:** Histori Transaksi (realisasi profit/loss & winrate).
     - **Lapis 3:** Scoreboard Kas & Aset Live di Streamlit.
   - Fitur **Auto Square-Off** pukul 15:30 WIB untuk mengamankan likuiditas harian.

5. **Pelacak Portofolio Multi-Aset (IHSG, Emas, Crypto, US Stock):**
   - Mendukung pencatatan aset multi-pasar: Saham IHSG, Emas Dunia (`GC=F`) dikonversi ke **IDR per gram**, Cryptocurrency (`BTC`, `ETH`, `SOL`), dan Saham US (`AAPL`, `NVDA`, `TSLA`).
   - Kurs tukar USD/IDR otomatis secara real-time via Yahoo Finance (`IDR=X`).
   - Perhitungan modal total, nilai pasar terkini, dan floating profit/loss (Rp & %).

6. **Mesin Prediksi Tren Harga Saham AI (Machine Learning Forecasting):**
   - Memproyeksikan estimasi pergerakan harga 7–30 hari ke depan menggunakan regresi multi-langkah (`XGBoost` / `GradientBoosting`).
   - Visualisasi interaktif Plotly menampilkan riwayat harga aktual, kurva proyeksi masa depan, dan area batas ketidakpastian (*confidence band*).
   - Evaluasi akurasi metrik MAPE (*Mean Absolute Percentage Error*) dan visualisasi *feature importance*.

7. **Sistem Notifikasi Telegram Cerdas:**
   - Mengirim alert rekomendasi BSJP sore hari secara otomatis sebelum jam bursa tutup.
   - Mengirim notifikasi eksekusi beli/jual bot simulator secara instan ke Telegram channel atau chat pribadi pengguna.
   - Tombol pengujian koneksi Telegram langsung dari sidebar web.

8. **Pembaruan Otomatis IHSG Per Jam (Background Scheduler):**
   - Layanan penjadwal otomatis yang memantau jam bursa IDX (Senin–Jumat pukul 09:00–16:00 WIB) setiap 60 menit.
   - Memproses data seluruh saham IHSG, menjalankan bot simulator, dan mencatat snapshot pasar secara kontinu.
   - Dilengkapi kartu status detak jantung (*heartbeat*) dan tombol *Start/Stop* langsung di sidebar web.

9. **Tracker Evaluasi Akurasi Prediksi AI 9 Rumus (Per Jam & Harian):**
   - Menyimpan riwayat setiap saham yang masuk ke dalam 9 Rumus BSJP pada setiap jam pasar.
   - Memverifikasi realisasi kenaikan harga di keesokan harinya (T+1: Open, High, Low, Close).
   - Menghitung akurasi secara transparan: Scorecard Win Rate Total, Rata-rata Max Gain, Rumus Terakurat (#1), Grafik Batang Perbandingan Akurasi Antar Rumus (Plotly), dan Tabel Riwayat Terfilter.

---

## 🎯 9 Rumus Strategi BSJP

Seluruh rumus mensyaratkan kondisi **Bollinger Bands Squeeze** (kompresi volatilitas sebelum ekspansi harga):

| Rumus | Nama Strategi | Karakteristik Utama |
|---|---|---|
| **Rumus 1** | Squeeze + Supply Kering + Di Atas VWAP | Barang habis di pasar, harga tertahan di atas VWAP intraday. |
| **Rumus 2** | Squeeze + 🔥 Anomali ML + OBV Naik | Outlier Machine Learning terdeteksi dengan akumulasi volume naik. |
| **Rumus 3** | Squeeze + 🕵️ Akumulasi Kuat & Pro | Konvergensi akumulasi broker summary + Smart Money A/D. |
| **Rumus 4** | Squeeze + Breakout MA20 + Ritel Aktif | Volume menembus rata-rata 20 hari dengan likuiditas ritel 5M–50M. |
| **Rumus 5** | Squeeze + Golden Cross | Persilangan moving average jangka pendek melintasi MA20. |
| **Rumus 6** | Squeeze + Pola Hammer | Pola pembalikan arah candlestick dengan ekor bawah panjang (shakeout). |
| **Rumus 7** | Squeeze + Karakter Solid | Saham disiplin yang jarang dibanting di penutupan sesi. |
| **Rumus 8** | Squeeze + Wyckoff Accumulation | Berada di fase kumpul barang Wyckoff sebelum fase Mark-Up. |
| **Rumus 9** | Squeeze + Risk/Reward Menarik (> 1:3) | Jarak ke level support ketat dengan potensi upside resistance tinggi. |

---

## 📁 Struktur Direktori

```text
├── Database/                   # Database CSV lokal (portofolio, histori, sinyal)
│   ├── hasil_screener.csv      # Snapshot data pasar & skor teknikal 900+ saham
│   ├── data_akuisisi.csv       # Status sentimen M&A emiten dari Google News
│   ├── portofolio_aktif_rumus_X.csv
│   └── histori_transaksi_rumus_X.csv
├── Arsip_Data_Harian/          # Arsip snapshot harian untuk analisis histori & AI
├── Konfigurasi/                # Konfigurasi master saham & kata kunci
│   ├── saham.txt               # Daftar 960+ ticker saham IHSG
│   ├── RENCANA_AKUISISI.txt    # Frasa kata kunci rencana aksi korporasi
│   └── DALAM_AKUISISI.txt      # Frasa kata kunci aksi korporasi rampung
├── tests/                      # Unit testing otomatis
│   └── test_screener.py
├── app.py                      # Dashboard Web interaktif (Streamlit)
├── update_data.py              # Ingestion data, kalkulasi teknikal & ML
├── bot_simulator.py            # Mesin eksekusi trading simulator 9 arena
├── mesin_ai.py                 # Engine AI Groq & helper histori arsip
├── update_akuisisi.py          # Pemindai RSS berita aksi korporasi
├── generate_keywords.py        # Generator variasi kata kunci akuisisi
├── jalankan_bot.sh             # Skrip automasi cron job (portabel)
├── requirements.txt            # Dependensi pustaka Python
├── .env.example                # Template konfigurasi kunci API
└── .gitignore                  # Pengabaian kredensial dan file sementara
```

---

## 🛠️ Instalasi & Persiapan

### 1. Prasyarat
- Python 3.10 atau versi yang lebih baru
- Git

### 2. Setup Virtual Environment
```bash
# Clone repositori
git clone https://github.com/dadungdadung87-cloud/SAHAM-SCREENING.git
cd SAHAM-SCREENING

# Buat dan aktifkan virtual environment
python3 -m venv .venv
source .venv/bin/activate  # macOS / Linux
# atau: .venv\Scripts\activate (Windows)

# Pasang seluruh dependensi
pip install -r requirements.txt
```

---

## 🔑 Konfigurasi API (.env)

Salin file template `.env.example` menjadi `.env`:
```bash
cp .env.example .env
```
Buka file `.env` dan lengkapi kunci API Anda:
```ini
# Token Bearer Stockbit untuk data broker summary
STOCKBIT_TOKEN=your_stockbit_token_here

# Kunci API Google AI Studio / Gemini
GEMINI_API_KEY=your_gemini_api_key_here

# Kunci API Groq (Llama 3.3 / DeepSeek)
GROQ_API_KEY=your_groq_api_key_here

# Kunci API OpenRouter (Opsional)
OPENROUTER_API_KEY=your_openrouter_api_key_here
```

---

## 🚀 Cara Penggunaan

### 1. Menjalankan Dashboard Web (Streamlit)
```bash
./.venv/bin/streamlit run app.py
```
Akses dashboard pada browser di: `http://localhost:8501`.

### 2. Memperbarui Data Pasar & Indikator
```bash
# Mode normal: memperbarui seluruh 960+ saham
./.venv/bin/python update_data.py

# Mode pengujian cepat (misal hanya 10 saham):
./.venv/bin/python update_data.py --limit 10

# Mode target ticker tertentu:
./.venv/bin/python update_data.py --tickers BBCA,BBRI,TLKM,ASII

# Mode simulasi tanpa menyimpan ke database (dry-run):
./.venv/bin/python update_data.py --tickers BBCA,TLKM --dry-run
```

### 3. Menjalankan Bot Simulator Portofolio
```bash
./.venv/bin/python bot_simulator.py
```

### 4. Memperbarui Data Sentimen Berita Akuisisi
```bash
./.venv/bin/python update_akuisisi.py
```

---

## ⏰ Otomasi Cron (Jam Bursa)

Gunakan skrip `jalankan_bot.sh` untuk menjalankan pembaruan otomatis via crontab Linux/macOS:
```bash
chmod +x jalankan_bot.sh
```

Contoh konfigurasi crontab (berjalan setiap 15 menit pada jam bursa Senin–Jumat pukul 09:00 - 16:00 WIB):
```bash
crontab -e
```
Tambahkan baris berikut:
```cron
*/15 9-16 * * 1-5 /path/to/SAHAM-SCREENING/jalankan_bot.sh >> /path/to/SAHAM-SCREENING/bot.log 2>&1
```

---

## 🧪 Pengujian Otomatis (Unit Tests)

Jalankan suite pengujian unit untuk memastikan seluruh logika matematika, kalkulasi fee, dan analisis berfungsi normal:
```bash
./.venv/bin/python -m unittest discover tests
```

---

## ⚖️ Lisensi & Disclaimer

*Aplikasi ini dibuat murni untuk tujuan riset kuantitatif, edukasi, dan simulasi strategi pasar modal (paper trading). Data dan hasil analisis AI bukan merupakan rekomendasi finansial resmi. Segala keputusan investasi dan risiko transaksi pasar saham berada sepenuhnya di tangan pengguna.*