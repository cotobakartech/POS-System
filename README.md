# ☕ Cafe BOS - Order & Management System

**Cafe BOS (Bikin Orang Sukses)** adalah sistem manajemen kafe terintegrasi yang dirancang khusus untuk efisiensi operasional, mulai dari pemesanan pelanggan hingga laporan keuangan otomatis dan absensi berbasis AI.

---

## 🌟 Fitur Utama

### 1. 📋 Sistem Pemesanan (Waiter & Customer)
- **Interface Responsif**: Dapat diakses melalui smartphone pelanggan atau tablet waiter.
- **Customization**: Pilihan tingkat gula, es, dan topping untuk setiap menu.
- **Real-time Pending Orders**: Pesanan yang masuk akan langsung muncul di dashboard kasir.

### 2. 🤖 AI Assistant (Gemini AI Integration)
- Fitur chatbot cerdas untuk melayani pertanyaan pelanggan seputar menu, reservasi, dan informasi Cafe BOS.
- Terintegrasi langsung dengan data menu terbaru dari database.

### 3. 👤 Sistem Absensi Wajah (Face Recognition)
- Menggunakan **MediaPipe** untuk pengenalan wajah karyawan yang akurat.
- **Auto-Mirroring**: Tampilan kamera yang natural saat absen.
- **Smart Window**: Pembatasan jam masuk (08:00-21:59) dan jam pulang (22:00-23:59).

### 4. 📊 Manajemen Inventaris & Resep
- Pelacakan stok bahan baku secara real-time.
- **Potong Stok Otomatis**: Setiap pesanan yang selesai akan otomatis mengurangi stok bahan baku berdasarkan resep yang telah diatur.

### 5. 💰 Laporan Keuangan & Cloud Backup
- **Multi-Metode Pembayaran**: Mendukung Cash dan QRIS.
- **Generate Report**: Laporan harian dalam format **Excel** dan **PDF** yang estetik.
- **Auto-Sync Google Drive**: Mencadangkan laporan harian secara otomatis ke cloud.

### 6. 🖨️ Thermal Printing
- Cetak struk otomatis ke printer thermal default Windows.
- Format struk yang profesional dengan detail PPN dan pembulatan.

---

## 🛠️ Teknologi yang Digunakan

- **Backend**: Python (Flask Framework)
- **Server**: Waitress (Mode Produksi di Port 80)
- **Database**: SQLite
- **AI/ML**: MediaPipe (Face Mesh), Google Gemini AI API
- **Cloud**: Google Drive API, Cloudflare Tunnel, Ngrok
- **Frontend**: HTML5, Vanilla CSS, JavaScript

---

## 🚀 Panduan Instalasi

### 1. Persyaratan Sistem
- Python 3.9 atau lebih baru.
- Koneksi internet (untuk API Gemini & GDrive).
- Printer Thermal (Opsional).

### 2. Langkah-Langkah Instalasi
1. **Clone Repositori**:
   ```bash
   git clone https://github.com/cotobakartech/cafe_bos.git
   cd cafe_bos
   ```

2. **Buat Virtual Environment**:
   ```bash
   python -m venv venv
   venv\Scripts\activate
   ```

3. **Install Dependensi**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Inisialisasi Database**:
   Jalankan script `app.py` sekali untuk membuat file `database.db` secara otomatis.
   ```bash
   python app.py
   ```

---

## ⚙️ Konfigurasi API

### 1. Gemini AI
Dapatkan API Key di [Google AI Studio](https://aistudio.google.com/) dan masukkan ke dalam variabel `GEMINI_API_KEY` di `app.py`.

### 2. Google Drive Backup
1. Aktifkan Drive API di Google Cloud Console.
2. Unduh `credentials.json` dan letakkan di root folder.
3. Saat dijalankan pertama kali, sistem akan meminta otorisasi dan menyimpan `token.json`.

---

## 🖥️ Cara Menjalankan

### Mode Windows (Rekomendasi)
Klik dua kali pada file `jalankan_kasir.bat`. File ini akan otomatis menjalankan:
1. Server Flask (Waitress) di Port 80.
2. Cloudflare Tunnel untuk akses remote.
3. Ngrok sebagai backup akses remote.

### Mode Manual
```bash
python server.py
```

---

## 📂 Struktur Folder Utama
- `app.py`: Logika utama aplikasi, route, dan integrasi AI.
- `server.py`: Konfigurasi production server menggunakan Waitress.
- `pdf_generator.py`: Modul khusus pembuat laporan PDF.
- `templates/`: File HTML untuk antarmuka pengguna.
- `static/`: Aset gambar, CSS, JS, dan hasil laporan.
- `database.db`: Database SQLite (Auto-generated).

---

## 👤 Akun Admin Default
- **Username**: `@SuksesBOS`
- **Password**: `123456789`

---

## 📝 Catatan Penting
- **Port 80**: Pastikan tidak ada aplikasi lain (seperti XAMPP/Apache) yang menggunakan port 80 agar `server.py` bisa berjalan.
- **Thermal Printer**: Pastikan printer sudah di-set sebagai **Default Printer** di Windows.

---
© 2026 **PT Bikin Orang Sukses (BOS)**.
Developed & Supported by **Cotobakartech (Muh Alif Arkan)**.
All Rights Reserved.
