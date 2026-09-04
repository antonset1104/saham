import os
import itertools

DIR_CONFIG = "Konfigurasi"
os.makedirs(DIR_CONFIG, exist_ok=True)

# Komponen kata untuk Rencana Akuisisi
kata_kerja_rencana = ["rencana", "kaji", "proses", "tahap", "upaya", "bidik", "siapkan", "teken", "resmi", "tuntaskan", "jajaki", "incar"]
kata_aksi = ["akuisisi", "merger", "pengambilalihan", "pembelian", "konsolidasi", "integrasi", "transaksi", "kepemilikan"]
kata_objek = ["saham", "aset", "bisnis", "perusahaan", "unit usaha", "pangsa pasar", "entitas"]

# Komponen kata untuk Dalam Akuisisi (Deal selesai / sah)
kata_kerja_dalam = ["resmi", "tuntas", "selesai", "sepakat", "rampung", "sah", "eksekusi", "sukses"]

def generate_keywords(filename, kerja_list, aksi_list, objek_list):
    filepath = os.path.join(DIR_CONFIG, filename)
    frasa_set = set()

    # 1. Variasi 2 Kata: [kata_kerja] [kata_aksi]
    for k, a in itertools.product(kerja_list, aksi_list):
        frasa_set.add(f"{k} {a}")

    # 2. Variasi 3 Kata: [kata_kerja] [kata_aksi] [kata_objek]
    for k, a, o in itertools.product(kerja_list, aksi_list, objek_list):
        frasa_set.add(f"{k} {a} {o}")

    # Simpan ke file dalam urutan alfabetis
    frasa_urut = sorted(list(frasa_set))
    with open(filepath, "w", encoding="utf-8") as f:
        for frasa in frasa_urut:
            f.write(f"{frasa}\n")
            
    print(f"✅ {filepath} berhasil dibuat! (Total {len(frasa_urut)} frasa unik, 0 duplikat)")

def main():
    print("⚙️ Menghasilkan daftar kata kunci unik untuk sentimen akuisisi...")
    # 1. Rencana Akuisisi
    generate_keywords(
        "RENCANA_AKUISISI.txt",
        kata_kerja_rencana,
        ["akuisisi", "merger", "pengambilalihan", "konsolidasi"],
        kata_objek
    )
    # 2. Dalam / Sukses Akuisisi
    generate_keywords(
        "DALAM_AKUISISI.txt",
        kata_kerja_dalam,
        kata_aksi,
        kata_objek
    )
    print("🎉 Seluruh file kata kunci di folder 'Konfigurasi/' telah diperbarui secara optimal!")

if __name__ == "__main__":
    main()