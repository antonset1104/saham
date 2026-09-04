"""
Skrip pembuat dokumen Microsoft Word (.docx) panduan lengkap hosting
AlgoTrade Screener IHSG di Windows 11 menggunakan Cloudflare Tunnel (100% Free).
"""
import os
import docx
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml import parse_xml, OxmlElement
from docx.oxml.ns import nsdecls, qn

OUTPUT_FILE = "Panduan_Hosting_Windows11_Cloudflare_Tunnel.docx"

# Skema Warna Profesional
HEX_PRIMARY = "1A365D"      # Deep Navy
HEX_SECONDARY = "0D9488"    # Teal
HEX_TEXT_DARK = "1E293B"    # Slate Dark
HEX_BG_LIGHT = "F8FAFC"     # Off-white / Light Slate
HEX_BORDER = "CBD5E1"       # Border gray
HEX_CODE_BG = "F1F5F9"      # Code box background
HEX_CALLOUT_BG = "EFF6FF"   # Blue callout
HEX_CALLOUT_BORDER = "3B82F6"

COLOR_PRIMARY = RGBColor(26, 54, 93)
COLOR_SECONDARY = RGBColor(13, 148, 136)
COLOR_TEXT_DARK = RGBColor(30, 41, 59)
COLOR_GRAY = RGBColor(100, 116, 139)

def set_cell_background(cell, hex_color):
    """Menyetel warna latar belakang cell tabel."""
    shd = parse_xml(f'<w:shd {nsdecls("w")} w:fill="{hex_color}"/>')
    cell._tc.get_or_add_tcPr().append(shd)

def set_cell_margins(cell, top=100, bottom=100, left=150, right=150):
    """Menyetel padding/margin di dalam cell tabel."""
    tcPr = cell._tc.get_or_add_tcPr()
    tcMar = OxmlElement('w:tcMar')
    for m, val in [('top', top), ('bottom', bottom), ('left', left), ('right', right)]:
        node = OxmlElement(f'w:{m}')
        node.set(qn('w:w'), str(val))
        node.set(qn('w:type'), 'dxa')
        tcMar.append(node)
    tcPr.append(tcMar)

def add_callout(doc, text_list, title="💡 TIPS PENTING", bg_color=HEX_CALLOUT_BG, border_color=HEX_CALLOUT_BORDER):
    """Membuat kotak callout (box informasi) dengan border samping tebal."""
    table = doc.add_table(rows=1, cols=1)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False
    
    cell = table.cell(0, 0)
    cell.width = Inches(6.5)
    set_cell_background(cell, bg_color)
    set_cell_margins(cell, top=140, bottom=140, left=200, right=180)
    
    # Border kiri tebal, border lainnya hilang
    borders = parse_xml(
        f'<w:tcBorders {nsdecls("w")}>'
        f'<w:top w:val="none"/>'
        f'<w:left w:val="single" w:sz="36" w:space="0" w:color="{border_color}"/>'
        f'<w:bottom w:val="none"/>'
        f'<w:right w:val="none"/>'
        f'</w:tcBorders>'
    )
    cell._tc.get_or_add_tcPr().append(borders)
    
    p = cell.paragraphs[0]
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.space_after = Pt(4)
    run_title = p.add_run(title)
    run_title.bold = True
    run_title.font.name = "Segoe UI"
    run_title.font.size = Pt(10.5)
    run_title.font.color.rgb = COLOR_PRIMARY
    
    for t in text_list:
        p2 = cell.add_paragraph()
        p2.paragraph_format.space_before = Pt(2)
        p2.paragraph_format.space_after = Pt(2)
        p2.paragraph_format.line_spacing = 1.15
        run_t = p2.add_run(t)
        run_t.font.name = "Segoe UI"
        run_t.font.size = Pt(9.5)
        run_t.font.color.rgb = COLOR_TEXT_DARK
        
    doc.add_paragraph().paragraph_format.space_after = Pt(6)

def add_code_block(doc, code_text):
    """Membuat kotak monospace untuk baris perintah/skrip."""
    table = doc.add_table(rows=1, cols=1)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False
    
    cell = table.cell(0, 0)
    cell.width = Inches(6.5)
    set_cell_background(cell, HEX_CODE_BG)
    set_cell_margins(cell, top=100, bottom=100, left=150, right=150)
    
    borders = parse_xml(
        f'<w:tcBorders {nsdecls("w")}>'
        f'<w:top w:val="single" w:sz="6" w:space="0" w:color="{HEX_BORDER}"/>'
        f'<w:left w:val="single" w:sz="6" w:space="0" w:color="{HEX_BORDER}"/>'
        f'<w:bottom w:val="single" w:sz="6" w:space="0" w:color="{HEX_BORDER}"/>'
        f'<w:right w:val="single" w:sz="6" w:space="0" w:color="{HEX_BORDER}"/>'
        f'</w:tcBorders>'
    )
    cell._tc.get_or_add_tcPr().append(borders)
    
    p = cell.paragraphs[0]
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.space_after = Pt(0)
    p.paragraph_format.line_spacing = 1.1
    run = p.add_run(code_text)
    run.font.name = "Consolas"
    run.font.size = Pt(9.5)
    run.font.color.rgb = RGBColor(15, 23, 42)
    
    doc.add_paragraph().paragraph_format.space_after = Pt(6)

def build_document():
    doc = docx.Document()
    
    # 1. Atur Margin Halaman (Normal 1 inci / 2.54 cm)
    sections = doc.sections
    for s in sections:
        s.top_margin = Inches(1.0)
        s.bottom_margin = Inches(1.0)
        s.left_margin = Inches(1.0)
        s.right_margin = Inches(1.0)
        
        # Header & Footer
        footer = s.footer
        p_ft = footer.paragraphs[0]
        p_ft.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        r_ft = p_ft.add_run("AlgoTrade Screener IHSG — Panduan Hosting Windows 11 & Cloudflare Tunnel")
        r_ft.font.name = "Segoe UI"
        r_ft.font.size = Pt(8.5)
        r_ft.font.color.rgb = COLOR_GRAY

    # ==========================================
    # COVER / HEADER DOKUMEN
    # ==========================================
    p_badge = doc.add_paragraph()
    p_badge.paragraph_format.space_before = Pt(0)
    p_badge.paragraph_format.space_after = Pt(4)
    r_badge = p_badge.add_run("PANDUAN LENGKAP DEPLOYMENT & HOSTING MANDIRI")
    r_badge.font.name = "Segoe UI"
    r_badge.font.size = Pt(9)
    r_badge.bold = True
    r_badge.font.color.rgb = COLOR_SECONDARY

    p_title = doc.add_paragraph()
    p_title.paragraph_format.space_before = Pt(0)
    p_title.paragraph_format.space_after = Pt(4)
    r_title = p_title.add_run("Hosting AlgoTrade Screener IHSG di Windows 11 (24 Jam Nonstop)")
    r_title.font.name = "Segoe UI"
    r_title.font.size = Pt(22)
    r_title.bold = True
    r_title.font.color.rgb = COLOR_PRIMARY

    p_sub = doc.add_paragraph()
    p_sub.paragraph_format.space_before = Pt(0)
    p_sub.paragraph_format.space_after = Pt(14)
    r_sub = p_sub.add_run("Akses Publik Aman dari Mana Saja Menggunakan Cloudflare Tunnel (100% Free Plan) Tanpa Buka Port Router & Tanpa IP Publik")
    r_sub.font.name = "Segoe UI"
    r_sub.font.size = Pt(11)
    r_sub.font.color.rgb = COLOR_GRAY

    # Garis Pembatas
    p_hr = doc.add_paragraph()
    p_hr.paragraph_format.space_after = Pt(12)
    r_hr = p_hr.add_run("―" * 58)
    r_hr.font.color.rgb = RGBColor(203, 213, 225)

    # Metadata Ringkas
    meta_table = doc.add_table(rows=2, cols=2)
    meta_table.alignment = WD_TABLE_ALIGNMENT.CENTER
    meta_data = [
        [("Sistem Operasi Target:", "Windows 11 (PC Desktop / Laptop / Mini PC)"),
         ("Metode Akses Publik:", "Cloudflare Tunnel (Zero Trust Free Plan)")],
        [("Komponen Utama:", "Streamlit Web, Scheduler Per Jam, Bot Telegram BSJP"),
         ("Estimasi Biaya:", "Rp 0,- / Gratis Selamanya")]
    ]
    for r_idx, row in enumerate(meta_data):
        for c_idx, (lbl, val) in enumerate(row):
            cell = meta_table.cell(r_idx, c_idx)
            set_cell_background(cell, HEX_BG_LIGHT)
            set_cell_margins(cell, top=60, bottom=60, left=100, right=100)
            p = cell.paragraphs[0]
            p.paragraph_format.space_after = Pt(2)
            r_l = p.add_run(f"{lbl} ")
            r_l.bold = True
            r_l.font.size = Pt(9)
            r_l.font.color.rgb = COLOR_PRIMARY
            r_v = p.add_run(val)
            r_v.font.size = Pt(9)
            r_v.font.color.rgb = COLOR_TEXT_DARK
            
    doc.add_paragraph().paragraph_format.space_after = Pt(16)

    # ==========================================
    # DAFTAR ISI RINGKAS
    # ==========================================
    p_toc_title = doc.add_paragraph()
    r_toc = p_toc_title.add_run("📌 DAFTAR ISI PANDUAN")
    r_toc.bold = True
    r_toc.font.size = Pt(13)
    r_toc.font.color.rgb = COLOR_PRIMARY

    toc_items = [
        "Bab 1: Gambaran Arsitektur & Keunggulan Solusi",
        "Bab 2: Persiapan Sistem Operasi Windows 11 (Anti-Sleep & Daya)",
        "Bab 3: Pemindahan & Instalasi Proyek di Windows 11",
        "Bab 4: Otomatisasi Startup Windows (Menyala Otomatis Saat Booting / Mati Lampu)",
        "Bab 5: Konfigurasi Cloudflare Tunnel (100% Free Plan)",
        "Bab 6: Mengamankan Akses Web dengan Cloudflare Access (Zero Trust OTP)",
        "Bab 7: Pemeliharaan, Monitoring, & Troubleshooting"
    ]
    for item in toc_items:
        p_item = doc.add_paragraph(style='List Bullet')
        p_item.paragraph_format.space_before = Pt(2)
        p_item.paragraph_format.space_after = Pt(2)
        r_item = p_item.add_run(item)
        r_item.font.name = "Segoe UI"
        r_item.font.size = Pt(10)
        r_item.font.color.rgb = COLOR_TEXT_DARK

    doc.add_paragraph().paragraph_format.space_after = Pt(16)

    # ==========================================
    # BAB 1: GAMBARAN ARSITEKTUR
    # ==========================================
    h1 = doc.add_paragraph()
    r_h1 = h1.add_run("BAB 1: GAMBARAN ARSITEKTUR & KEUNGGULAN SOLUSI")
    r_h1.bold = True
    r_h1.font.size = Pt(14)
    r_h1.font.color.rgb = COLOR_PRIMARY
    h1.paragraph_format.space_before = Pt(12)
    h1.paragraph_format.space_after = Pt(6)

    doc.add_paragraph(
        "Menjalankan aplikasi screener saham langsung di komputer Windows 11 milik sendiri dan menghubungkannya "
        "ke internet menggunakan Cloudflare Tunnel adalah solusi paling efisien, aman, dan tanpa biaya langganan bulanan. "
        "Seluruh komputasi berat (Machine Learning, scraping data Stockbit, evaluasi 9 rumus) ditangani oleh prosesor lokal Anda, "
        "sementara Cloudflare bertugas menyajikan koneksi HTTPS aman ke HP Android Anda di mana pun Anda berada."
    )

    doc.add_paragraph(
        "Alur Arsitektur Koneksi:", style='Normal'
    )
    add_code_block(doc, 
        "[ HP Android / Browser Publik ]\n"
        "             │  (HTTPS Terenkripsi via internet)\n"
        "             ▼\n"
        "[ Cloudflare Global Edge Network (DDoS Protection + Free SSL) ]\n"
        "             │  (Koneksi Terowongan Terenkripsi Keluar / Outbound Tunnel)\n"
        "             ▼\n"
        "[ Layanan cloudflared Windows 11 ]\n"
        "             │  (Localhost Port 8501)\n"
        "             ▼\n"
        "[ Server Web Streamlit + Scheduler Per Jam + Bot Telegram ]"
    )

    add_callout(doc, [
        "1. 100% Gratis Selamanya: Baik Cloudflare Tunnel maupun aplikasi Streamlit tidak memerlukan biaya langganan.",
        "2. Tanpa Buka Port Router: Anda TIDAK perlu menyetel Port Forwarding di modem Indihome / Biznet / FirstMedia.",
        "3. Tahan Terhadap IP Dinamis / CGNAT: Koneksi tetap tersambung meskipun IP internet rumah Anda berubah-ubah.",
        "4. Keamanan Tingkat Tinggi: IP publik rumah Anda disembunyikan sepenuhnya di balik dinding pelindung Cloudflare."
    ], title="⭐ KEUNGGULAN UTAMA CLOUDFLARE TUNNEL")

    # ==========================================
    # BAB 2: PERSIAPAN WINDOWS 11
    # ==========================================
    h2 = doc.add_paragraph()
    r_h2 = h2.add_run("BAB 2: PERSIAPAN SISTEM OPERASI WINDOWS 11")
    r_h2.bold = True
    r_h2.font.size = Pt(14)
    r_h2.font.color.rgb = COLOR_PRIMARY
    h2.paragraph_format.space_before = Pt(16)
    h2.paragraph_format.space_after = Pt(6)

    doc.add_paragraph(
        "Agar Windows 11 dapat bekerja sebagai server yang menyala 24 jam nonstop tanpa terhenti di tengah jam bursa, "
        "terdapat beberapa pengaturan daya dan sistem yang wajib dikonfigurasi:"
    )

    doc.add_paragraph("2.1. Mematikan Fitur Sleep (Tidur Otomatis)", style='Heading 2')
    doc.add_paragraph(
        "Jika Windows masuk ke mode Sleep, seluruh skrip Python, server Streamlit, dan jadwal alert Telegram akan berhenti. "
        "Lakukan langkah berikut:"
    )
    p_step1 = doc.add_paragraph(style='List Number')
    p_step1.add_run("Buka menu Settings Windows 11 (tekan tombol Win + I).")
    p_step2 = doc.add_paragraph(style='List Number')
    p_step2.add_run("Pilih menu System > Power & battery (atau Daya & baterai).")
    p_step3 = doc.add_paragraph(style='List Number')
    p_step3.add_run("Klik pada bagian Screen and sleep.")
    p_step4 = doc.add_paragraph(style='List Number')
    p_step4.add_run("Pada opsi 'When plugged in, put my device to sleep after', pilih: NEVER (Jangan Pernah).")
    p_step5 = doc.add_paragraph(style='List Number')
    p_step5.add_run("Untuk layar monitor ('turn off my screen after'), Anda bebas memilih 5 atau 10 menit agar hemat daya. Mematikan layar TIDAK menghentikan program.")

    doc.add_paragraph("2.2. Mematikan Hibernasi via Command Prompt", style='Heading 2')
    doc.add_paragraph(
        "Buka Command Prompt (CMD) sebagai Administrator (klik kanan tombol Start > Terminal/CMD as Administrator), lalu jalankan perintah:"
    )
    add_code_block(doc, "powercfg -h off")

    doc.add_paragraph("2.3. Mengatur Jam Aktif Windows Update (Active Hours)", style='Heading 2')
    doc.add_paragraph(
        "Agar Windows tidak melakukan restart mendadak saat bursa saham sedang aktif:"
    )
    doc.add_paragraph(
        "Masuk ke Settings > Windows Update > Advanced options > Active hours. Atur jam aktif dari pukul 08:00 sampai 18:00."
    )

    doc.add_paragraph("2.4. Instalasi Python 3.10 / 3.11 / 3.12", style='Heading 2')
    doc.add_paragraph(
        "Jika PC Windows belum memiliki Python:"
    )
    p_py1 = doc.add_paragraph(style='List Number')
    p_py1.add_run("Unduh installer resmi dari https://www.python.org/downloads/ (disarankan Python 3.11 atau 3.12).")
    p_py2 = doc.add_paragraph(style='List Number')
    r_crit = p_py2.add_run("SANGAT PENTING: Saat installer pertama kali terbuka, CENTANG KOTAK 'Add python.exe to PATH' di bagian bawah sebelum mengklik tombol Install Now!")
    r_crit.bold = True

    # ==========================================
    # BAB 3: SETUP PROYEK DI WINDOWS 11
    # ==========================================
    h3 = doc.add_paragraph()
    r_h3 = h3.add_run("BAB 3: PEMINDAHAN & INSTALASI PROYEK DI WINDOWS 11")
    r_h3.bold = True
    r_h3.font.size = Pt(14)
    r_h3.font.color.rgb = COLOR_PRIMARY
    h3.paragraph_format.space_before = Pt(16)
    h3.paragraph_format.space_after = Pt(6)

    doc.add_paragraph("3.1. Menyalin Folder Proyek", style='Heading 2')
    doc.add_paragraph(
        "Salin seluruh folder aplikasi saham dari Mac ke PC Windows 11 Anda (bisa menggunakan Flashdisk, LAN Share, atau Google Drive / GitHub). "
        "Disarankan meletakkannya pada lokasi yang mudah dijangkau, misalnya di:"
    )
    add_code_block(doc, "C:\\saham")

    doc.add_paragraph("3.2. Menjalankan Instalasi Otomatis (setup_windows.bat)", style='Heading 2')
    doc.add_paragraph(
        "Telah disediakan berkas otomatisasi khusus Windows bernama setup_windows.bat di dalam folder proyek. "
        "Cukup klik dua kali (Double-Click) pada berkas tersebut:"
    )
    add_code_block(doc, "setup_windows.bat")
    doc.add_paragraph(
        "Skrip ini akan secara otomatis:\n"
        "1. Memverifikasi ketersediaan Python di Windows.\n"
        "2. Membuat folder Virtual Environment independen (.venv).\n"
        "3. Memperbarui pip ke versi terbaru.\n"
        "4. Menginstal seluruh paket library yang dibutuhkan dari requirements.txt (Streamlit, Pandas, Scikit-Learn, Plotly, Yfinance, dll).\n"
        "5. Menyiapkan file konfigurasi .env."
    )

    doc.add_paragraph("3.3. Memastikan Konfigurasi Telegram di File .env", style='Heading 2')
    doc.add_paragraph(
        "Buka file .env menggunakan Notepad di folder C:\\saham, lalu pastikan token bot dan Chat ID Telegram Anda sudah terisi:"
    )
    add_code_block(doc, 
        "TELEGRAM_BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrsTUVwxyz... (Token Bot Anda)\n"
        "TELEGRAM_CHAT_ID=123456789 (Chat ID Anda)"
    )

    doc.add_paragraph("3.4. Uji Coba Manual Pertama", style='Heading 2')
    doc.add_paragraph(
        "Untuk memastikan instalasi berhasil, klik dua kali berkas start_saham_windows.bat. "
        "Sebuah jendela terminal hitam akan muncul dan membuka server di port 8501. "
        "Buka browser Chrome atau Edge di Windows dan buka alamat: http://localhost:8501. "
        "Pastikan dashboard AlgoTrade Screener tampil utuh dengan tabel saham."
    )

    # ==========================================
    # BAB 4: OTOMATISASI STARTUP WINDOWS
    # ==========================================
    h4 = doc.add_paragraph()
    r_h4 = h4.add_run("BAB 4: OTOMATISASI STARTUP WINDOWS (AUTO-START 24/7)")
    r_h4.bold = True
    r_h4.font.size = Pt(14)
    r_h4.font.color.rgb = COLOR_PRIMARY
    h4.paragraph_format.space_before = Pt(16)
    h4.paragraph_format.space_after = Pt(6)

    doc.add_paragraph(
        "Dalam skenario 24 jam nonstop, ada kemungkinan terjadi mati listrik sesaat atau komputer restart otomatis karena update. "
        "Kita perlu memastikan bahwa saat Windows menyala kembali, aplikasi Streamlit dan Scheduler per jam otomatis berjalan kembali "
        "secara hening (silent) di latar belakang tanpa memerlukan campur tangan Anda."
    )

    doc.add_paragraph("Langkah Memasang ke Folder Startup Windows:", style='Heading 2')
    
    p_su1 = doc.add_paragraph(style='List Number')
    p_su1.add_run("Tekan tombol kombinasi Windows + R pada keyboard untuk membuka jendela Run.")
    
    p_su2 = doc.add_paragraph(style='List Number')
    p_su2.add_run("Ketik perintah berikut lalu tekan Enter:")
    add_code_block(doc, "shell:startup")
    
    p_su3 = doc.add_paragraph(style='List Number')
    p_su3.add_run("Folder Startup Windows akan terbuka secara otomatis.")
    
    p_su4 = doc.add_paragraph(style='List Number')
    p_su4.add_run("Buka folder proyek Anda (C:\\saham) di jendela file explorer lain.")
    
    p_su5 = doc.add_paragraph(style='List Number')
    p_su5.add_run("Klik kanan pada berkas start_silent_windows.vbs > pilih 'Show more options' > pilih 'Create shortcut' (Buat Shortcut).")
    
    p_su6 = doc.add_paragraph(style='List Number')
    p_su6.add_run("Pindahkan (Cut / Copy) shortcut yang baru dibuat tersebut ke dalam folder Startup yang terbuka di langkah 3.")

    add_callout(doc, [
        "Berkas start_silent_windows.vbs dirancang khusus agar saat komputer dinyalakan, server Streamlit dan scheduler langsung aktif di latar belakang (background) tanpa memunculkan jendela hitam Command Prompt di layar Anda.",
        "Aktivitas dan log scheduler per jam akan otomatis dicatat secara rapi di berkas: C:\\saham\\Logs\\scheduler_windows.log."
    ], title="✨ CARA KERJA START SILENT")

    # ==========================================
    # BAB 5: KONFIGURASI CLOUDFLARE TUNNEL
    # ==========================================
    h5 = doc.add_paragraph()
    r_h5 = h5.add_run("BAB 5: KONFIGURASI CLOUDFLARE TUNNEL (100% FREE)")
    r_h5.bold = True
    r_h5.font.size = Pt(14)
    r_h5.font.color.rgb = COLOR_PRIMARY
    h5.paragraph_format.space_before = Pt(16)
    h5.paragraph_format.space_after = Pt(6)

    doc.add_paragraph(
        "Ini adalah tahap inti yang menghubungkan server lokal Windows 11 Anda ke jaringan global Cloudflare "
        "sehingga dapat diakses dari HP Android atau laptop Anda di luar rumah menggunakan koneksi HTTPS resmi yang aman."
    )

    doc.add_paragraph("Langkah-langkah Pembuatan Cloudflare Tunnel (Metode Dashboard):", style='Heading 2')

    steps_cf = [
        ("Langkah 1: Masuk ke Cloudflare Zero Trust Dashboard",
         "Buka peramban (browser) dan akses alamat: https://one.dash.cloudflare.com/ . Masuk menggunakan akun Cloudflare gratis Anda."),
        ("Langkah 2: Menuju Menu Tunnels",
         "Di bilah navigasi kiri, klik menu Networks > pilih Tunnels."),
        ("Langkah 3: Membuat Tunnel Baru",
         "Klik tombol biru 'Add a tunnel' (atau 'Create a tunnel').\n"
         "Pilih tipe konektor: Cloudflared > klik tombol Next.\n"
         "Beri nama tunnel Anda, contohnya: server-saham > klik Save tunnel."),
        ("Langkah 4: Memasang Konektor di Windows 11",
         "Di halaman 'Install and run a connector', pilih sistem operasi: Windows (64-bit).\n"
         "Cloudflare akan menampilkan dua pilihan:\n"
         "a. Tautan unduh installer MSI (cloudflared-windows-amd64.msi).\n"
         "b. Kotak perintah instalasi service lengkap dengan Token Anda."),
        ("Langkah 5: Menjalankan Perintah Instalasi di PowerShell",
         "Buka Windows PowerShell sebagai Administrator (klik kanan menu Start > Terminal / PowerShell (Admin)).\n"
         "Salin seluruh baris perintah yang diberikan Cloudflare, contohnya seperti berikut:\n"
         "cloudflared.exe service install eyJhIjoiMDFj...\n"
         "Lalu tekan Enter di PowerShell.\n"
         "Layanan cloudflared akan otomatis terpasang sebagai Windows Service mandiri yang langsung berjalan 24 jam nonstop tanpa perlu dibuka manual."),
        ("Langkah 6: Menghubungkan Public Hostname (Domain Web Anda)",
         "Kembali ke halaman Cloudflare di browser, klik tombol Next menuju tab 'Public Hostnames'.\n"
         "Klik tombol 'Add a public hostname' dan isi formulir berikut:\n"
         "• Subdomain : saham (atau nama bebas yang Anda sukai)\n"
         "• Domain : pilih domain Anda yang terhubung di Cloudflare (misal: domainanda.com)\n"
         "• Type : HTTP\n"
         "• URL : localhost:8501 (atau 127.0.0.1:8501)\n"
         "Klik tombol 'Save hostname'."),
        ("Langkah 7: Selesai & Uji Coba Akses dari HP Android",
         "Buka peramban Chrome di HP Android Anda (menggunakan paket data seluler tanpa WiFi rumah).\n"
         "Ketik alamat: https://saham.domainanda.com\n"
         "Web AlgoTrade Screener akan langsung terbuka seketika dengan gembok hijau HTTPS resmi!")
    ]

    for judul_step, desk_step in steps_cf:
        p_s = doc.add_paragraph()
        p_s.paragraph_format.space_before = Pt(6)
        p_s.paragraph_format.space_after = Pt(2)
        r_js = p_s.add_run(judul_step)
        r_js.bold = True
        r_js.font.size = Pt(10.5)
        r_js.font.color.rgb = COLOR_PRIMARY
        
        p_ds = doc.add_paragraph()
        p_ds.paragraph_format.space_before = Pt(0)
        p_ds.paragraph_format.space_after = Pt(4)
        r_ds = p_ds.add_run(desk_step)
        r_ds.font.size = Pt(9.5)
        r_ds.font.color.rgb = COLOR_TEXT_DARK

    doc.add_paragraph("Opsi Alternatif: Quick Tunnel (Bagi yang Belum Memiliki Domain Sendiri)", style='Heading 2')
    doc.add_paragraph(
        "Jika saat ini Anda belum membeli nama domain (.com / .my.id), Anda tetap bisa langsung online gratis menggunakan fitur Cloudflare Quick Tunnel:"
    )
    p_qt1 = doc.add_paragraph(style='List Number')
    p_qt1.add_run("Unduh cloudflared.exe dari GitHub resmi: https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe")
    p_qt2 = doc.add_paragraph(style='List Number')
    p_qt2.add_run("Simpan file tersebut di folder C:\\saham dengan nama cloudflared.exe.")
    p_qt3 = doc.add_paragraph(style='List Number')
    p_qt3.add_run("Jalankan perintah ini di Command Prompt:")
    add_code_block(doc, "cloudflared.exe tunnel --url http://localhost:8501")
    p_qt4 = doc.add_paragraph(style='List Number')
    p_qt4.add_run("Cloudflare akan langsung membuatkan URL publik gratis sementara berakhiran: https://random-name.trycloudflare.com yang langsung bisa dibuka dari HP Anda!")

    # ==========================================
    # BAB 6: PENGAMANAN AKSES (ZERO TRUST)
    # ==========================================
    h6 = doc.add_paragraph()
    r_h6 = h6.add_run("BAB 6: MENGAMANKAN AKSES WEB DENGAN CLOUDFLARE ACCESS (ZERO TRUST)")
    r_h6.bold = True
    r_h6.font.size = Pt(14)
    r_h6.font.color.rgb = COLOR_PRIMARY
    h6.paragraph_format.space_before = Pt(16)
    h6.paragraph_format.space_after = Pt(6)

    doc.add_paragraph(
        "Karena web saham Anda kini online di internet, siapapun yang mengetahui alamat domain Anda bisa saja membuka website tersebut. "
        "Untuk mencegah orang asing mengakses screener Anda, manfaatkan fitur Cloudflare Access (100% Gratis hingga 50 pengguna):"
    )

    steps_sec = [
        "1. Di dashboard Cloudflare Zero Trust (https://one.dash.cloudflare.com/), pilih menu Access > Applications.",
        "2. Klik 'Add an application' > pilih tipe 'Self-hosted'.",
        "3. Beri nama aplikasi (misal: Proteksi Web Saham), dan masukkan subdomain serta domain Anda (saham.domainanda.com).",
        "4. Pada bagian Policy (Aturan Akses):",
        "   - Action: Allow",
        "   - Rule Name: Hanya Saya",
        "   - Selector: Emails",
        "   - Value: Masukkan alamat email pribadi Anda (misal: emailanda@gmail.com)",
        "5. Klik Next > Save application."
    ]
    for s in steps_sec:
        p_sec = doc.add_paragraph()
        p_sec.paragraph_format.space_before = Pt(2)
        p_sec.paragraph_format.space_after = Pt(2)
        r_sec = p_sec.add_run(s)
        r_sec.font.size = Pt(9.5)

    add_callout(doc, [
        "Setelah Cloudflare Access aktif, setiap kali Anda membuka web dari HP di luar rumah, Cloudflare akan meminta verifikasi email terlebih dahulu.",
        "Cloudflare akan mengirimkan 6 digit kode PIN OTP ke inbox email Anda. Setelah dimasukkan, web akan langsung terbuka.",
        "Perangkat Anda akan mengingat login tersebut selama 24 jam atau beberapa hari sehingga Anda tidak perlu mengetik kode berulang kali."
    ], title="🔒 PENGAMANAN KELAS KORPORAT")

    # ==========================================
    # BAB 7: MONITORING & TROUBLESHOOTING
    # ==========================================
    h7 = doc.add_paragraph()
    r_h7 = h7.add_run("BAB 7: PEMELIHARAAN, MONITORING, & TROUBLESHOOTING")
    r_h7.bold = True
    r_h7.font.size = Pt(14)
    r_h7.font.color.rgb = COLOR_PRIMARY
    h7.paragraph_format.space_before = Pt(16)
    h7.paragraph_format.space_after = Pt(6)

    doc.add_paragraph("7.1. Memeriksa Apakah Layanan Aktif Berjalan di Windows", style='Heading 2')
    doc.add_paragraph(
        "Untuk memastikan seluruh layanan berjalan normal di Windows 11:"
    )
    doc.add_paragraph("• Cek Layanan Cloudflared:", style='Normal')
    doc.add_paragraph("  Tekan Win + R > ketik services.msc > Enter. Cari layanan bernama 'Cloudflare Tunnel' atau 'cloudflared'. Pastikan statusnya 'Running' dan Startup Type 'Automatic'.")
    doc.add_paragraph("• Cek Log Scheduler Python:", style='Normal')
    doc.add_paragraph("  Buka berkas log di: C:\\saham\\Logs\\scheduler_windows.log menggunakan Notepad. Anda akan melihat catatan update per jam dan pemicu alert 10:00 & 15:30 WIB.")

    doc.add_paragraph("7.2. Troubleshooting Kendala Umum", style='Heading 2')

    table_trouble = doc.add_table(rows=1, cols=3)
    table_trouble.alignment = WD_TABLE_ALIGNMENT.CENTER
    table_trouble.autofit = False
    
    hdr_cells = table_trouble.rows[0].cells
    hdr_titles = ["Gejala Masalah", "Kemungkinan Penyebab", "Solusi Langkah Cepat"]
    col_widths = [Inches(1.8), Inches(2.2), Inches(2.5)]
    
    for i, title in enumerate(hdr_titles):
        cell = hdr_cells[i]
        cell.width = col_widths[i]
        set_cell_background(cell, HEX_PRIMARY)
        set_cell_margins(cell, top=100, bottom=100, left=100, right=100)
        p = cell.paragraphs[0]
        r = p.add_run(title)
        r.bold = True
        r.font.size = Pt(9.5)
        r.font.color.rgb = RGBColor(255, 255, 255)

    trouble_data = [
        ("Web tidak bisa dibuka (Error 502 Bad Gateway di Cloudflare)", 
         "Server Streamlit belum berjalan di port 8501 pada PC Windows.", 
         "Jalankan start_saham_windows.bat atau pastikan start_silent_windows.vbs telah aktif."),
        ("Notifikasi Telegram tidak masuk pada jam 10:00 atau 15:30", 
         "Token Bot atau Chat ID di file .env belum tepat, atau PC masuk mode Sleep.", 
         "Periksa file .env dan pastikan pengaturan Sleep di Windows 11 sudah diubah ke 'Never'."),
        ("Status Tunnel di dashboard Cloudflare berwarna merah (Inactive)", 
         "Service cloudflared terhenti atau koneksi internet PC terputus.", 
         "Buka PowerShell Administrator, jalankan: restart-service cloudflared."),
        ("Komputer restart otomatis di malam hari", 
         "Fitur Windows Update melakukan pembaruan berkala.", 
         "Pastikan shortcut start_silent_windows.vbs sudah berada di folder shell:startup agar aplikasi otomatis menyala kembali setelah restart.")
    ]

    for row_idx, row_data in enumerate(trouble_data):
        row = table_trouble.add_row()
        for i, val in enumerate(row_data):
            cell = row.cells[i]
            cell.width = col_widths[i]
            set_cell_background(cell, HEX_BG_LIGHT if row_idx % 2 == 1 else "FFFFFF")
            set_cell_margins(cell, top=80, bottom=80, left=100, right=100)
            p = cell.paragraphs[0]
            r = p.add_run(val)
            r.font.size = Pt(9)
            r.font.color.rgb = COLOR_TEXT_DARK

    doc.add_paragraph().paragraph_format.space_after = Pt(16)

    # Penutup / Checklist
    add_callout(doc, [
        "☑️ Windows 11 Power Settings: Sleep = NEVER.",
        "☑️ Python 3.11/3.12 terpasang dengan 'Add to PATH' tercentang.",
        "☑️ setup_windows.bat berhasil dijalankan (folder .venv terbentuk).",
        "☑️ File .env telah memuat Bot Token & Chat ID Telegram yang valid.",
        "☑️ Shortcut start_silent_windows.vbs sudah ditaruh di folder shell:startup.",
        "☑️ cloudflared service sudah terinstal via PowerShell Administrator.",
        "☑️ Public Hostname di dashboard Cloudflare mengarah ke http://localhost:8501."
    ], title="📋 CHECKLIST FINAL DEPLOYMENT WINDOWS 11")

    # Simpan dokumen
    doc.save(OUTPUT_FILE)
    print(f"Dokumen berhasil disimpan ke: {os.path.abspath(OUTPUT_FILE)}")

if __name__ == "__main__":
    build_document()
