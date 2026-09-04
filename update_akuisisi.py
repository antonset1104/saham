import os
import pandas as pd

try:
    import feedparser
except ImportError:
    feedparser = None

DIR_CONFIG = "Konfigurasi"
DIR_DATABASE = "Database"
FILE_SAHAM = os.path.join(DIR_CONFIG, "saham.txt") if os.path.exists(os.path.join(DIR_CONFIG, "saham.txt")) else "saham.txt"
FILE_RENCANA = os.path.join(DIR_CONFIG, "RENCANA_AKUISISI.txt") if os.path.exists(os.path.join(DIR_CONFIG, "RENCANA_AKUISISI.txt")) else "RENCANA_AKUISISI.txt"
FILE_DALAM = os.path.join(DIR_CONFIG, "DALAM_AKUISISI.txt") if os.path.exists(os.path.join(DIR_CONFIG, "DALAM_AKUISISI.txt")) else "DALAM_AKUISISI.txt"
FILE_OUTPUT = os.path.join(DIR_DATABASE, "data_akuisisi.csv")

def load_keywords(filename):
    """Memuat daftar kata kunci dari file txt."""
    if not os.path.exists(filename):
        print(f"⚠️ Peringatan: File '{filename}' tidak ditemukan.")
        return []
    with open(filename, "r", encoding="utf-8") as file:
        return [line.strip().lower() for line in file if line.strip()]

def get_news_titles(ticker):
    """Menarik judul berita terbaru dari Google News RSS secara aman"""
    if feedparser is None:
        return "Tidak ada berita terbaru."
    query = f"saham+{ticker}+akuisisi"
    url = f"https://news.google.com/rss/search?q={query}&hl=id&gl=ID&ceid=ID:id"
    try:
        feed = feedparser.parse(url)
        titles = [entry.title for entry in feed.entries[:5]]
        return " | ".join(titles) if titles else "Tidak ada berita terbaru."
    except Exception as e:
        return "Tidak ada berita terbaru."

def analyze_acquisition_status(news_text, kata_rencana, kata_dalam):
    if news_text == "Tidak ada berita terbaru.":
        return "TIDAK ADA"
        
    teks_kecil = news_text.lower()
    
    # Hanya ambil yang panjangnya >= 2 kata
    dalam_valid = [k for k in kata_dalam if len(k.split()) >= 2]
    rencana_valid = [k for k in kata_rencana if len(k.split()) >= 2]
    
    # Prioritas: DALAM AKUISISI
    if any(k in teks_kecil for k in dalam_valid):
        return "DALAM AKUISISI"
        
    # Prioritas kedua: RENCANA AKUISISI
    if any(k in teks_kecil for k in rencana_valid):
        return "RENCANA AKUISISI"
        
    return "TIDAK ADA"

def main():
    print("🔍 Memulai pemindaian berita sentimen akuisisi...")
    
    if not os.path.exists(FILE_SAHAM):
        print(f"❌ Error: File saham '{FILE_SAHAM}' tidak ditemukan!")
        return

    # Memuat kata kunci dari file eksternal
    kata_rencana = load_keywords(FILE_RENCANA)
    kata_dalam = load_keywords(FILE_DALAM)

    with open(FILE_SAHAM, "r", encoding="utf-8") as file:
        daftar_saham = [baris.strip().upper() for baris in file if baris.strip()]
        
    hasil_akuisisi = []
    
    for ticker in daftar_saham:
        berita = get_news_titles(ticker)
        status = analyze_acquisition_status(berita, kata_rencana, kata_dalam)
        
        hasil_akuisisi.append({
            "Ticker": ticker,
            "Status Akuisisi": status
        })
        
    if hasil_akuisisi:
        os.makedirs(DIR_DATABASE, exist_ok=True)
        df = pd.DataFrame(hasil_akuisisi)
        # Tulis secara atomik
        tmp_file = f"{FILE_OUTPUT}.tmp"
        df.to_csv(tmp_file, index=False)
        os.replace(tmp_file, FILE_OUTPUT)
        print(f"✅ Selesai! File '{FILE_OUTPUT}' berhasil diperbarui.")

if __name__ == "__main__":
    main()