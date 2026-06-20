# ☕ KAPIO — Sistem Kasir & Manajemen Kedai

**KAPIO** (*Kedainya Kita Semua*) adalah sistem POS (Point of Sale) berbasis web yang terintegrasi untuk manajemen kedai kopi/resto, mencakup pemesanan, kasir, inventaris, laporan keuangan, membership, antrian display, hingga absensi karyawan.

---

## 🌟 Fitur Utama

### 1. 📋 Sistem Pemesanan (Kasir / Waiter)
- **Interface Responsif**: Desain modern yang optimal di HP pelanggan maupun tablet kasir.
- **Customization Menu**: Pelanggan/kasir dapat memilih varian, topping, dan level gula/es secara mandiri.
- **Diskon per Item**: Setiap menu mendukung diskon persentase yang ditampilkan langsung di struk.
- **Student Discount**: Potongan 10% khusus untuk pembelian Dine-In.
- **Dine-in / Take Away**: Pilihan tipe pesanan saat checkout.
- **Antrian Otomatis**: Nomor antrian dikelola secara otomatis oleh sistem.

### 2. 🖥️ Admin Dashboard
- **Kelola Pesanan Real-time**: Lihat, konfirmasi bayar, selesaikan, dan reprint pesanan dari satu halaman.
- **Panel Manajemen Menu**: Tambah, edit, hapus menu termasuk gambar, varian, topping, diskon, resep, dan status tampil di TV.
- **Analitik Penjualan**: Grafik penjualan 30 hari terakhir (gabungan data live + arsip Excel).
- **Best Seller**: Ranking produk terlaris berdasarkan periode (Hari, Bulan, Tahun, Semua).
- **Rekap Finansial**: Total pemasukan, pengeluaran, dan keuntungan berdasarkan periode (Hari Ini, Bulan Ini, Tahun Ini, Semua).

### 3. 📦 Manajemen Inventaris & Resep
- **Manajemen Bahan Baku**: Tambah dan pantau stok bahan baku beserta satuan.
- **Resep per Menu**: Konfigurasi komposisi bahan per menu untuk penghitungan stok otomatis.
- **Auto-Deduction Stok**: Stok bahan baku berkurang otomatis saat pesanan diselesaikan (berdasarkan resep).
- **Input Stok Masuk**: Catat penambahan stok dan harga beli untuk laporan pengeluaran.
- **Stock Alert**: Pantau sisa bahan baku langsung dari dashboard.

### 4. 📊 Laporan & Arsip
- **Export Excel**: Generate laporan (Pemasukan, Pengeluaran, Stok) ke file `.xlsx` kapan saja.
- **Export PDF**: Cetak laporan dalam format PDF via modul `pdf_generator.py`.
- **Manajemen Arsip**: Download arsip laporan lama langsung dari dashboard admin.
- **Tambah Pengeluaran Manual**: Catat pengeluaran operasional lain di luar pembelian stok.

### 5. 💳 Sistem Membership & Cashback
- **Registrasi Member**: Daftarkan pelanggan dengan nama dan nomor HP sebagai ID member.
- **Saldo Cashback Otomatis**: Cashback dihitung otomatis berdasarkan total transaksi (2%–5%) dan dikreditkan ke saldo saat pembayaran.
- **Redeem Cashback**: Member dapat menggunakan saldo cashback sebagai potongan harga saat checkout.
- **Kartu Member Digital**: Cetak kartu member digital langsung dari dashboard.

### 6. 🖨️ Cetak Struk Termal
- **Multi-format**: Mendukung printer 58mm dan 80mm.
- **Struk Kasir & Barista**: Cetak 2 jenis struk (kasir dengan harga, barista hanya qty & nama).
- **Logo Gambar**: Print logo toko di struk menggunakan ESC/POS raster (via OpenCV).
- **Bluetooth Printing**: Dukungan cetak via Bluetooth (COM port / RFCOMM socket) untuk printer nirkabel.
- **Reprint**: Cetak ulang struk pesanan lama kapan saja.

### 7. 📺 Display TV (Tanpa Login)
- **Display Menu**: Tampilan menu digital untuk layar TV/monitor pelanggan (`/display/menu`).
- **Display Antrian**: Tampilan nomor antrian real-time untuk pelanggan (`/display/queue`).

### 8. 👤 Absensi & Manajemen Karyawan
- **Data Karyawan**: Kelola data karyawan (nama, posisi, gaji bulanan, tanggal masuk).
- **Absensi Harian**: Catat kehadiran dengan status: Hadir, Double Shift, Izin, atau Alpha.
- **Shift Otomatis**: Sistem membedakan Shift 1 (06:00–16:59) dan Shift 2 (17:00–05:59) berdasarkan waktu absen.
- **Rekap Gaji Bulanan**: Hitung otomatis total upah berdasarkan jumlah hari hadir.

### 9. 🔐 Sistem Autentikasi
- **Login / Signup**: Sistem akun berbasis sesi (Flask session).
- **Role Admin**: Halaman admin hanya bisa diakses oleh akun dengan role `admin`.
- **Akun Default**: Admin dibuat otomatis saat pertama kali dijalankan.

---

## 🛠️ Teknologi yang Digunakan

| Layer | Teknologi |
|---|---|
| **Backend** | Python 3, Flask 3.x |
| **Server Produksi** | Waitress (Multi-threaded, Port 80) |
| **Database** | SQLite (`possystem.db`) |
| **Frontend** | HTML5, Vanilla CSS (Glassmorphism), JavaScript |
| **Laporan** | Pandas (Excel), FPDF (PDF), OpenCV (Gambar ESC/POS) |
| **Cetak Thermal** | pywin32 (Windows Printer API), PySerial (Bluetooth COM) |
| **PWA** | Service Worker + `manifest.json` |
| **Remote Access** | Cloudflare Tunnel + Ngrok |

---

## 🚀 Panduan Instalasi

### 1. Persyaratan Sistem
- Python 3.9+
- Windows (untuk fitur Thermal Printing via `pywin32`)
- Koneksi jaringan lokal (LAN/WiFi) untuk akses multi-perangkat

### 2. Langkah Instalasi

**Clone repositori:**
```bash
git clone https://github.com/cotobakartech/POS-System.git
cd POS-System
```

**Setup environment virtual:**
```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Dependensi (`requirements.txt`)
```
Flask, pandas, pywin32, fpdf, requests, Werkzeug
openpyxl, opencv-python, numpy, pyserial
google-auth, google-generativeai (opsional)
```

---

## 🖥️ Cara Menjalankan

### ⚡ Cara Cepat (Windows)
Klik dua kali file **`jalankan_kasir.bat`**.

Script ini secara otomatis menjalankan:
1. `server.py` — Server Waitress di Port 80
2. **Cloudflare Tunnel** — Akses remote aman
3. **Ngrok** — Tunnel alternatif

### 🐍 Cara Manual (Development)
```bash
python app.py
# Akses di http://localhost:5000
```

### 🔥 Cara Manual (Produksi, Port 80)
```bash
python server.py
# Akses dari HP lain: http://<IP-SERVER>
```

---

## 📂 Struktur Folder

```
POS-System/
├── app.py                  # Logika backend & semua API Routes (Flask)
├── server.py               # Server produksi Waitress (Port 80, 12 threads)
├── pdf_generator.py        # Modul pembuatan laporan PDF
├── jalankan_kasir.bat      # Script Windows one-click launcher
├── requirements.txt        # Daftar dependensi Python
├── possystem.db            # Database SQLite (dibuat otomatis)
├── templates/
│   ├── index.html          # Halaman kasir / pemesanan
│   ├── admin.html          # Dashboard admin lengkap
│   ├── login.html          # Halaman login
│   ├── signup.html         # Halaman registrasi akun
│   ├── absensi.html        # Halaman absensi & manajemen karyawan
│   ├── membership.html     # Halaman manajemen membership
│   ├── reports.html        # Halaman laporan (redirect ke admin)
│   ├── inventory.html      # Halaman inventaris (redirect ke admin)
│   ├── display_menu.html   # Display menu untuk TV pelanggan
│   └── display_queue.html  # Display antrian real-time untuk TV
├── static/
│   ├── css/                # File stylesheet
│   ├── images/             # Gambar aset (logo, dll)
│   ├── menu/               # Upload gambar menu
│   ├── manifest.json       # PWA manifest
│   └── sw.js               # Service Worker (PWA offline support)
└── docs/                   # Dokumentasi & screenshot
```

---

## 🔑 Akun Default

| Field | Value |
|---|---|
| **Username** | `admin` |
| **Password** | `admin123` |

> ⚠️ **Ganti password admin segera** setelah instalasi pertama untuk keamanan sistem.

---

## 📡 Endpoint Utama

| Route | Deskripsi |
|---|---|
| `/` | Halaman kasir / pemesanan |
| `/admin` | Dashboard admin |
| `/absensi` | Manajemen absensi karyawan |
| `/display/menu` | Display menu TV (tanpa login) |
| `/display/queue` | Display antrian TV (tanpa login) |
| `/api/active_orders` | API antrian aktif (JSON) |
| `/api/orders_dashboard` | API dashboard pesanan (JSON) |
| `/api/print` | API cetak struk |
| `/api/settings` | API pengaturan sistem |
| `/archive` | Arsip data ke Excel |
| `/login` | Halaman login |

---

© 2026 **Cotobakartech**.  
Developed & Supported by **Cotobakartech**.  
All Rights Reserved.
