from flask import Flask, render_template, request, redirect, url_for, session, send_file, jsonify, send_from_directory
from datetime import datetime, timedelta
from functools import wraps
import sqlite3
import pandas as pd
import win32print
import json
import os
import io
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from fpdf import FPDF
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import requests
import google.generativeai as genai
from pdf_generator import generate_report_pdf, generate_attendance_pdf


SCOPES = ['https://www.googleapis.com/auth/drive.file']

app = Flask(__name__)
# Gunakan secret key yang lebih kuat atau ambil dari environment
app.secret_key = os.environ.get('SECRET_KEY', 'cafe_bos_ultra_secure_key_2026_!@#')
app.config['UPLOAD_FOLDER'] = 'static/menu'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}



def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# --- KONFIGURASI GEMINI AI (CLOUD AI) ---
GEMINI_API_KEY = "AIzaSyA1yjJl9P2mLMKbXCYJDw_Ph2CovYo7UlQ"
genai.configure(api_key=GEMINI_API_KEY)
generation_config = {
  "temperature": 0.7,
  "top_p": 0.95,
  "top_k": 40,
  "max_output_tokens": 1024,
  "response_mime_type": "text/plain",
}
model = genai.GenerativeModel(
  model_name="gemini-3-flash-preview",
  generation_config=generation_config,
)

SYSTEM_PROMPT = """
Anda adalah AI Assistant resmi untuk Cafe BOS bagian dari (PT Bikin Orang Sukses).
Tugas Anda adalah melayani pelanggan dengan ramah, profesional, dan informatif.

Informasi Tentang Cafe BOS:
- Lokasi: Citraland Tallasa City Ruko A1 No.3, Kapasa, Tamalanrea, Makassar.
- Jam Operasional: Setiap hari pukul 08:00 - 22:00.
- Filosofi: Semangat Lebah (teliti, harmoni, kerja keras untuk sukses).
- Produk: Kopi pilihan, Milk Flavor Latte, Snack, dan produk-produk PT BOS.
- Reservasi Meeting Room: Tersedia dua tipe dengan sistem Minimum Order yaitu tipe Juragan (Rp 350.000) dan Sultan (Rp 500.000).
- Visi: Menjadi pilihan terbaik perusahaan network yang inovatif dan kreatif.
- Kontak: Email cafebos.indonesia@gmail.com, WhatsApp 0881 0806 88155.

Aturan Jawaban:
1. Gunakan Bahasa Indonesia yang sopan dan ramah.
2. Jawablah pertanyaan seputar Cafe BOS dengan akurat berdasarkan info di atas.
3. Jika ditanya menu, beri tahu bahwa menu lengkap dapat diunduh di website ini.
4. Jika ditanya di luar Cafe BOS, arahkan kembali dengan sopan ke topik cafe.
5. JANGAN gunakan format Markdown seperti simbol bintang (**) atau (*) untuk list. Gunakan teks biasa saja agar mudah dibaca.
6. Jawablah dengan singkat, padat, dan jelas. Hindari penjelasan yang terlalu panjang atau bertele-tele, namun tetap pertahankan kesopanan.
"""

@app.route('/chat_ai', methods=['POST'])
def chat_ai():
    data = request.json
    user_message = data.get('message')
    history = data.get('history', []) 
    
    if not user_message:
        return jsonify({'response': 'Maaf, saya tidak menangkap pesan Anda.'})

    try:
        # Ambil data menu dari database
        conn = get_db_connection()
        menus_db = conn.execute("SELECT nama, harga, kategori FROM menus").fetchall()
        conn.close()
        
        menu_context = "DAFTAR MENU TERBARU DI CAFE BOS:\n"
        for m in menus_db:
            menu_context += f"- {m['nama']} ({m['kategori']}): Rp {m['harga']:,}\n".replace(",", ".")
        
        # Format history untuk Gemini
        contents = []
        # Tambahkan system instructions sebagai bagian dari pesan pertama atau konteks
        system_instr = SYSTEM_PROMPT + f"\n\nDATA MENU TERBARU:\n{menu_context}"
        
        # Mulai chat session
        chat_session = model.start_chat(history=[])
        
        # Kirim pesan dengan konteks sistem di awal jika history kosong, 
        # atau selipkan di pesan pertama
        full_prompt = f"{system_instr}\n\nPesan User: {user_message}"
        
        # Jika ada history, kita bisa menyusunnya kembali
        # Namun untuk efisiensi, kita bisa kirim history yang ada
        gemini_history = []
        for turn in history:
            role = "user" if turn['role'] == "user" else "model"
            content = turn['parts'][0] if turn['parts'] else ""
            gemini_history.append({"role": role, "parts": [content]})
        
        chat_session = model.start_chat(history=gemini_history)
        
        # Jika ini pesan pertama (history kosong), masukkan system prompt
        if not gemini_history:
            final_prompt = full_prompt
        else:
            final_prompt = user_message

        response = chat_session.send_message(final_prompt)
        ai_response = response.text
        
        # Bersihkan respon dari simbol bintang jika masih ada
        clean_response = ai_response.replace('*', '')
        
        return jsonify({'response': clean_response})
    except Exception as e:
        print(f"Gemini Error: {e}")
        return jsonify({'response': 'Maaf, Tuan. Sepertinya koneksi AI sedang terganggu. Mohon coba lagi nanti! 🐝'})


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# --- FUNGSI HELPER CETAK THERMAL ---
THERMAL_WIDTH = 42

def fmt_idr(n):
    """Format angka ke Rupiah (Rp 10.000)"""
    return "{:,.0f}".format(n).replace(",", ".")

def thermal_line():
    return "-" * THERMAL_WIDTH

def thermal_center(text):
    return text.center(THERMAL_WIDTH)

def thermal_row(left, right):
    return left.ljust(THERMAL_WIDTH - len(right)) + right

def print_thermal(text):
    """Mengirim teks ke printer thermal default (Windows Only)"""
    try:
        printer_name = win32print.GetDefaultPrinter()
        hprinter = win32print.OpenPrinter(printer_name)
        hjob = win32print.StartDocPrinter(hprinter, 1, ("Struk_CafeBOS", None, "RAW"))
        win32print.StartPagePrinter(hprinter)
        win32print.WritePrinter(hprinter, text.encode('utf-8'))
        win32print.EndPagePrinter(hprinter)
        win32print.EndDocPrinter(hprinter)
        win32print.ClosePrinter(hprinter)
    except Exception as e:
        print(f"CRITICAL PRINT ERROR: {e}")
        # Jangan biarkan aplikasi crash hanya karena printer mati
        return False
    return True

def upload_to_gdrive(file_path, folder_id):
    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists('credentials.json'):
                print("WARNING: credentials.json tidak ditemukan. Gagal upload ke GDrive.")
                return False
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        with open('token.json', 'w') as token:
            token.write(creds.to_json())

    try:
        service = build('drive', 'v3', credentials=creds)
        file_metadata = {
            'name': os.path.basename(file_path),
            'parents': [folder_id]
        }
        media = MediaFileUpload(file_path, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', resumable=True)
        file = service.files().create(body=file_metadata, media_body=media, fields='id').execute()
        print(f"File berhasil diupload ke GDrive. ID: {file.get('id')}")
        return True
    except Exception as e:
        print(f"Terjadi kesalahan saat upload ke GDrive: {e}")
        return False

# --- INISIALISASI DATABASE ---
def init_db():
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    
    # Tabel Pesanan
    c.execute('''CREATE TABLE IF NOT EXISTS orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nama TEXT, 
        meja TEXT, 
        menu TEXT, 
        total INTEGER, 
        status TEXT DEFAULT 'pending', 
        waktu TEXT,
        is_archived INTEGER DEFAULT 0)''')
    
    # MIGRASI: Tambahkan is_archived ke orders jika belum ada
    try:
        c.execute('SELECT is_archived FROM orders LIMIT 1')
    except sqlite3.OperationalError:
        c.execute('ALTER TABLE orders ADD COLUMN is_archived INTEGER DEFAULT 0')
    
    # Tabel Settings
    c.execute('''CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT
    )''')
    
    # Inisialisasi default settings jika belum ada
    c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('modal_kembalian', '0')")
    
    # Tabel Menu
    c.execute('''CREATE TABLE IF NOT EXISTS menus (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nama TEXT, 
        harga INTEGER, 
        kategori TEXT,
        has_opt INTEGER,
        gambar TEXT,
        show_on_tv INTEGER DEFAULT 0)''')

    # Tabel Pengeluaran
    c.execute('''CREATE TABLE IF NOT EXISTS expenses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        keterangan TEXT,
        jumlah INTEGER,
        waktu TEXT,
        source TEXT DEFAULT 'cafe',
        is_archived INTEGER DEFAULT 0
    )''')
    
    # MIGRASI: Tambahkan is_archived ke expenses jika belum ada
    try:
        c.execute('SELECT is_archived FROM expenses LIMIT 1')
    except sqlite3.OperationalError:
        c.execute('ALTER TABLE expenses ADD COLUMN is_archived INTEGER DEFAULT 0')

    # Tabel Pemasukan Produk PT BOS
    c.execute('''CREATE TABLE IF NOT EXISTS pemasukan_ptbos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        keterangan TEXT,
        jumlah INTEGER,
        waktu TEXT,
        is_archived INTEGER DEFAULT 0
    )''')

    # MIGRASI: Tambahkan is_archived ke pemasukan_ptbos jika belum ada
    try:
        c.execute('SELECT is_archived FROM pemasukan_ptbos LIMIT 1')
    except sqlite3.OperationalError:
        c.execute('ALTER TABLE pemasukan_ptbos ADD COLUMN is_archived INTEGER DEFAULT 0')

    # Tabel Input Stok Cafe BOS
    c.execute('''CREATE TABLE IF NOT EXISTS input_stok (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        keterangan TEXT,
        qty INTEGER,
        jumlah INTEGER,
        waktu TEXT,
        is_archived INTEGER DEFAULT 0
    )''')
    
    # MIGRASI: Tambahkan is_archived ke input_stok jika belum ada
    try:
        c.execute('SELECT is_archived FROM input_stok LIMIT 1')
    except sqlite3.OperationalError:
        c.execute('ALTER TABLE input_stok ADD COLUMN is_archived INTEGER DEFAULT 0')
    
    # MIGRASI OTOMATIS: Tambahkan kolom kategori jika belum ada
    try:
        c.execute('SELECT kategori FROM menus LIMIT 1')
    except sqlite3.OperationalError:
        c.execute('ALTER TABLE menus ADD COLUMN kategori TEXT DEFAULT "Lainnya"')

    try:
        c.execute('SELECT topping FROM menus LIMIT 1')
    except sqlite3.OperationalError:
        c.execute('ALTER TABLE menus ADD COLUMN topping TEXT DEFAULT ""')

    try:
        c.execute('SELECT harga_topping FROM menus LIMIT 1')
    except sqlite3.OperationalError:
        c.execute('ALTER TABLE menus ADD COLUMN harga_topping TEXT DEFAULT ""')

    try:
        c.execute('ALTER TABLE orders ADD COLUMN metode TEXT DEFAULT "cash"')
        c.execute('ALTER TABLE orders ADD COLUMN kasir TEXT DEFAULT "Admin"')
    except sqlite3.OperationalError:
        # Jika kolom sudah ada, abaikan errornya
        pass

    try:
        c.execute('SELECT harga FROM input_stok LIMIT 1')
    except sqlite3.OperationalError:
        c.execute('ALTER TABLE input_stok ADD COLUMN harga INTEGER DEFAULT 0')

    # Tabel Users untuk Login Aman
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        password TEXT
    )''')

    # Tambahkan admin default jika belum ada
    admin_user = "@SuksesBOS"
    admin_pass = "123456789"
    c.execute("SELECT * FROM users WHERE username=?", (admin_user,))
    if not c.fetchone():
        hashed_pw = generate_password_hash(admin_pass)
        c.execute("INSERT INTO users (username, password) VALUES (?, ?)", (admin_user, hashed_pw))

    # Tabel Raw Materials (Bahan Baku)
    c.execute('''CREATE TABLE IF NOT EXISTS raw_materials (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nama TEXT UNIQUE,
        stok REAL DEFAULT 0,
        satuan TEXT
    )''')

    # Tabel Recipes (Resep Menu)
    c.execute('''CREATE TABLE IF NOT EXISTS recipes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        menu_id INTEGER,
        material_id INTEGER,
        jumlah REAL,
        FOREIGN KEY (menu_id) REFERENCES menus (id),
        FOREIGN KEY (material_id) REFERENCES raw_materials (id)
    )''')

    # Tabel Karyawan
    c.execute('''CREATE TABLE IF NOT EXISTS employees (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nama TEXT UNIQUE,
        pin TEXT,
        face_descriptor TEXT
    )''')

    # Tabel Absensi
    c.execute('''CREATE TABLE IF NOT EXISTS attendance (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        employee_id INTEGER,
        tanggal TEXT,
        jam_masuk TEXT,
        jam_pulang TEXT,
        FOREIGN KEY (employee_id) REFERENCES employees (id)
    )''')
        
    conn.commit()
    conn.close()

# Jalankan inisialisasi
init_db()

def get_db_connection():
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row 
    return conn

# --- ROUTE WAITER (HALAMAN DEPAN) ---
@app.route('/')
def index():
    conn = get_db_connection()
    daftar_menu = conn.execute('SELECT * FROM menus ORDER BY kategori ASC').fetchall()
    conn.close()
    return render_template('index.html', menus=daftar_menu)

@app.route('/order', methods=['POST'])
def order():
    nama_customer = "Customer"
    meja = request.form.get('meja')
    waktu = datetime.now().strftime("%d-%m-%Y %H:%M:%S")
    cart_data = request.form.get('cart_data')

    if not cart_data:
        return redirect('/')

    try:
        cart = json.loads(cart_data)
    except Exception as e:
        print(f"Order Parsing Error: {e}")
        return redirect('/?status=error_data')

    conn = get_db_connection()

    # 1. CEK APAKAH SUDAH ADA PESANAN PENDING DI MEJA INI
    existing = conn.execute(
        "SELECT * FROM orders WHERE meja=? AND status='pending'", (meja,)
    ).fetchone()

    # Ambil status PPN semua menu untuk referensi cepat
    menu_ppn_map = {m['nama']: m['use_ppn'] for m in conn.execute("SELECT nama, use_ppn FROM menus").fetchall()}

    if existing:
        menu_db = existing['menu'].split('|')
        order_map = {}

        for item in menu_db:
            if "TOTAL_QTY:" in item or not item.strip(): continue
            parts = item.split('\n')
            if len(parts) < 2: continue
            
            nama_opsi = parts[0]
            details = parts[1].split('  ')
            
            order_map[nama_opsi] = {
                'qty': int(details[0]),
                'harga': int(details[1])
            }

        total_harga_baru = existing['total']
        for item in cart:
            nama_menu = item['nama']
            # Cek PPN
            ppn_tag = "" if menu_ppn_map.get(nama_menu, 1) == 1 else " {NON_PPN}"
            
            detail_opsi = f"({item['ice']}, {item['sugar']})"
            if item['topping']: detail_opsi += f" +{item['topping']}"
            
            key = f"{nama_menu}{ppn_tag} {detail_opsi}"
            qty_baru = int(item['qty'])
            harga_satuan = int(item['harga'])

            if key in order_map:
                order_map[key]['qty'] += qty_baru
            else:
                order_map[key] = {'qty': qty_baru, 'harga': harga_satuan}
            
            total_harga_baru += (qty_baru * harga_satuan)

        list_final = []
        total_qty_final = 0
        for key, val in order_map.items():
            subtotal = val['qty'] * val['harga']
            total_qty_final += val['qty']
            list_final.append(f"{key}\n{val['qty']}  {val['harga']}  {subtotal}")

        menu_final = "|".join(list_final) + f"|TOTAL_QTY:{total_qty_final}"
        conn.execute("UPDATE orders SET menu=?, total=? WHERE id=?", (menu_final, total_harga_baru, existing['id']))

    else:
        items = []
        total_harga = 0
        total_qty = 0
        for item in cart:
            nama_menu = item['nama']
            ppn_tag = "" if menu_ppn_map.get(nama_menu, 1) == 1 else " {NON_PPN}"
            
            qty = int(item['qty'])
            harga = int(item['harga'])
            detail = f"({item['ice']}, {item['sugar']})"
            if item['topping']: detail += f" +{item['topping']}"
            
            subtotal = qty * harga
            total_harga += subtotal
            total_qty += qty
            items.append(f"{nama_menu}{ppn_tag} {detail}\n{qty}  {harga}  {subtotal}")

        menu_final = "|".join(items) + f"|TOTAL_QTY:{total_qty}"
        conn.execute("INSERT INTO orders (nama, meja, menu, total, waktu) VALUES (?, ?, ?, ?, ?)",
                     (nama_customer, meja, menu_final, total_harga, waktu))

    conn.commit()
    conn.close()
    return redirect('/?status=sent')

# --- ROUTE KASIR (ADMIN) ---
@app.route('/admin')
@login_required
def admin():
    conn = get_db_connection()
    # Hanya tampilkan pesanan pending ATAU pesanan selesai yang BELUM DIARSIP
    orders = conn.execute("""
        SELECT * FROM orders 
        WHERE status='pending' 
        OR (status='selesai' AND is_archived=0)
        ORDER BY CASE WHEN status='pending' THEN 0 ELSE 1 END, id DESC
    """).fetchall()
    
    menus = conn.execute("SELECT * FROM menus ORDER BY kategori ASC").fetchall()
    conn.close()
    return render_template('admin.html', orders=orders, menus=menus)

@app.route('/add_menu', methods=['POST'])
@login_required
def add_menu():
    nama = request.form.get('nama')
    harga = int(request.form.get('harga'))
    kategori = request.form.get('kategori')
    has_opt = 1 if request.form.get('has_opt') else 0
    topping = request.form.get('topping')
    harga_topping = request.form.get('harga_topping')
    show_on_tv = 1 if request.form.get('show_on_tv') else 0
    use_ppn = 1 if request.form.get('use_ppn') else 0
    # Handle File Upload
    gambar_filename = ""
    if 'file_gambar' in request.files:
        file = request.files['file_gambar']
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            gambar_filename = filename
    
    conn = get_db_connection()
    conn.execute("INSERT INTO menus (nama, harga, kategori, has_opt, topping, harga_topping, gambar, show_on_tv, use_ppn) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", 
                 (nama, harga, kategori, has_opt, topping, harga_topping, gambar_filename, show_on_tv, use_ppn))
    conn.commit()
    conn.close()
    return redirect('/admin')

@app.route('/update_menu/<int:id>', methods=['POST'])
@login_required
def update_menu(id):
    nama = request.form['nama']
    harga = request.form['harga'].replace('.', '').replace('Rp', '').strip()
    kategori = request.form['kategori']
    gambar = request.form.get('gambar', '')
    show_on_tv = 1 if request.form.get('show_on_tv') else 0
    use_ppn = 1 if request.form.get('use_ppn') else 0
    has_opt = 1 if request.form.get('has_opt') else 0
    topping = request.form.get('topping', '')
    harga_topping = request.form.get('harga_topping', '')
    
    if 'file_gambar' in request.files:
        file = request.files['file_gambar']
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            gambar = filename

    conn = get_db_connection()
    conn.execute('UPDATE menus SET nama=?, harga=?, kategori=?, gambar=?, show_on_tv=?, has_opt=?, topping=?, harga_topping=?, use_ppn=? WHERE id=?',
                 (nama, harga, kategori, gambar, show_on_tv, has_opt, topping, harga_topping, use_ppn, id))
    conn.commit()
    conn.close()
    return redirect('/admin')

# --- SISTEM INVENTORY & RESEP ---
@app.route('/inventory')
@login_required
def inventory():
    conn = get_db_connection()
    materials = conn.execute("SELECT * FROM raw_materials ORDER BY nama ASC").fetchall()
    menus = conn.execute("SELECT * FROM menus ORDER BY kategori ASC").fetchall()
    conn.close()
    return render_template('inventory.html', materials=materials, menus=menus)

@app.route('/add_material', methods=['POST'])
@login_required
def add_material():
    nama = request.form.get('nama')
    satuan = request.form.get('satuan')
    stok = float(request.form.get('stok', 0))
    
    conn = get_db_connection()
    try:
        conn.execute("INSERT INTO raw_materials (nama, satuan, stok) VALUES (?, ?, ?)", (nama, satuan, stok))
        conn.commit()
    except Exception as e: 
        print(f"Error adding material: {e}")
    conn.close()
    return redirect('/inventory')

@app.route('/update_material', methods=['POST'])
@login_required
def update_material():
    mat_id = request.form.get('id')
    nama = request.form.get('nama')
    satuan = request.form.get('satuan')
    stok_tambah = float(request.form.get('stok_tambah', 0))
    
    conn = get_db_connection()
    conn.execute("UPDATE raw_materials SET nama=?, satuan=?, stok=stok+? WHERE id=?", 
                 (nama, satuan, stok_tambah, mat_id))
    conn.commit()
    conn.close()
    return redirect('/inventory')

@app.route('/delete_order/<int:id>', methods=['POST'])
@login_required
def delete_order(id):
    conn = get_db_connection()
    conn.execute("DELETE FROM orders WHERE id=?", (id,))
    conn.commit()
    conn.close()
    return redirect('/admin')

@app.route('/del_material/<int:id>', methods=['POST'])
@login_required
def del_material(id):
    conn = get_db_connection()
    conn.execute("DELETE FROM raw_materials WHERE id=?", (id,))
    conn.execute("DELETE FROM recipes WHERE material_id=?", (id,))
    conn.commit()
    conn.close()
    return redirect('/inventory')

@app.route('/manage_recipe/<int:menu_id>', methods=['GET', 'POST'])
@login_required
def manage_recipe(menu_id):
    conn = get_db_connection()
    menu = conn.execute("SELECT * FROM menus WHERE id=?", (menu_id,)).fetchone()
    recipe = conn.execute("""
        SELECT r.*, rm.nama, rm.satuan 
        FROM recipes r 
        JOIN raw_materials rm ON r.material_id = rm.id 
        WHERE r.menu_id = ?
    """, (menu_id,)).fetchall()
    materials = conn.execute("SELECT * FROM raw_materials ORDER BY nama ASC").fetchall()
    conn.close()
    return render_template('recipes.html', menu=menu, recipe=recipe, materials=materials)

@app.route('/add_recipe_item', methods=['POST'])
@login_required
def add_recipe_item():
    menu_id = request.form.get('menu_id')
    material_id = request.form.get('material_id')
    jumlah = float(request.form.get('jumlah'))
    
    conn = get_db_connection()
    conn.execute("INSERT INTO recipes (menu_id, material_id, jumlah) VALUES (?, ?, ?)", 
                 (menu_id, material_id, jumlah))
    conn.commit()
    conn.close()
    return redirect(f'/manage_recipe/{menu_id}')

@app.route('/del_recipe_item/<int:id>', methods=['POST'])
@login_required
def del_recipe_item(id):
    menu_id = request.args.get('menu_id')
    conn = get_db_connection()
    conn.execute("DELETE FROM recipes WHERE id=?", (id,))
    conn.commit()
    conn.close()
    return redirect(f'/manage_recipe/{menu_id}')


@app.route('/del_menu/<int:id>', methods=['POST'])
@login_required
def del_menu(id):
    conn = get_db_connection()
    conn.execute("DELETE FROM menus WHERE id=?", (id,))
    conn.commit()
    conn.close()
    return redirect('/admin')

@app.route('/done/<int:id>', methods=['POST'])
@login_required
def done(id):
    kasir = request.form.get('kasir', 'Admin')
    bayar = int(request.form.get('bayar', 0))
    metode = request.form.get('metode', 'cash')
    total_akhir = int(request.form.get('total_akhir', 0))
    diskon = int(request.form.get('diskon', 0))

    conn = get_db_connection()
    order = conn.execute("SELECT * FROM orders WHERE id=?", (id,)).fetchone()
    
    if not order:
        conn.close()
        return redirect('/admin')
    
    # Simpan total_akhir ke DB (Sudah termasuk PPN & Pembulatan)
    conn.execute("UPDATE orders SET status='selesai', total=?, metode=?, kasir=? WHERE id=?", (total_akhir, metode, kasir, id))
    
    # --- LOGIKA OTOMATIS POTONG STOK ---
    try:
        data_order = order['menu'].split('|')
        for item_str in data_order:
            if "TOTAL_QTY:" in item_str or not item_str.strip(): continue
            parts = item_str.split('\n')
            if len(parts) < 2: continue
            
            # Bersihkan nama menu (hilangkan opsi dalam kurung)
            nama_menu_full = parts[0]
            nama_menu_clean = nama_menu_full.split(' (')[0].strip()
            
            # Ambil Qty
            details = parts[1].split('  ')
            qty_pesanan = float(details[0])
            
            # Cari menu_id di database
            menu_db = conn.execute("SELECT id FROM menus WHERE nama=?", (nama_menu_clean,)).fetchone()
            if menu_db:
                menu_id = menu_db['id']
                # Cari resep untuk menu ini
                recipe_items = conn.execute("SELECT * FROM recipes WHERE menu_id=?", (menu_id,)).fetchall()
                for r in recipe_items:
                    # Kurangi stok bahan baku
                    conn.execute("UPDATE raw_materials SET stok = stok - ? WHERE id = ?", 
                                 (r['jumlah'] * qty_pesanan, r['material_id']))
    except Exception as e:
        print(f"Inventory Deduction Error: {e}")

    conn.commit()
    conn.close()

    lines = []
    lines.append(thermal_center("CAFE BOS"))
    lines.append(thermal_center("Citraland Tallasa City"))
    lines.append(thermal_center("Ruko A1 No.3, Kapasa"))
    lines.append(thermal_center("Tamalanrea, Kota Makassar"))
    lines.append(thermal_line())
    lines.append(f"Meja  : {order['meja']}")
    lines.append(f"Kasir : {kasir}")
    lines.append(thermal_line())

    data = order['menu'].split('|')
    for item in data:
        if "TOTAL_QTY:" not in item:
            parts = item.split('\n')
            lines.append(parts[0])
            if len(parts) > 1:
                sub = parts[1].split('  ')
                try:
                    lines.append(thermal_row(f"{sub[0]} x {fmt_idr(int(sub[1]))}", fmt_idr(int(sub[2]))))
                except Exception:
                    pass

    lines.append(thermal_line())

    subtotal_asal = order['total'] 
    ppn = int(subtotal_asal * 0.10)
    
    lines.append(thermal_row("Subtotal", fmt_idr(subtotal_asal)))
    lines.append(thermal_row("PPN 10%", fmt_idr(ppn)))
    
    lines.append(thermal_line())
    lines.append(thermal_row("TOTAL", fmt_idr(total_akhir)))
    lines.append(thermal_row("Metode", metode.upper()))
    lines.append(thermal_row("Tunai", fmt_idr(bayar)))
    lines.append(thermal_row("Kembali", fmt_idr(bayar - total_akhir)))

    lines.append(thermal_line())
    lines.append(thermal_center(order['waktu']))
    lines.append("")
    lines.append(thermal_center("Terima Kasih!"))
    lines.append("\n\n\n")

    text = "\n".join(lines)
    try:
        print_thermal(text)
    except Exception as e:
        print("PRINT ERROR:", e)

    return redirect('/admin')

@app.route('/print_struk/<int:id>')
@login_required
def print_struk(id):
    conn = get_db_connection()
    order = conn.execute("SELECT * FROM orders WHERE id=?", (id,)).fetchone()
    conn.close()
    
    kasir = request.args.get('kasir', 'Admin')
    bayar = int(request.args.get('bayar', order['total'] if order else 0))
    metode = request.args.get('metode', 'cash').upper() # Ambil metode (CASH/QRIS)
    
    return render_template('struk.html', o=order, kasir=kasir, bayar=bayar, metode=metode)

@app.route('/print_barista/<int:id>')
@login_required
def print_barista(id):
    conn = get_db_connection()
    order = conn.execute("SELECT * FROM orders WHERE id=?", (id,)).fetchone()
    conn.close()

    if not order:
        return redirect('/admin')

    WIDTH = 42
    def thermal_center(t): return t.center(WIDTH)
    def thermal_line(): return "-" * WIDTH

    lines = []
    lines.append(thermal_center("ORDER BARISTA"))
    lines.append(thermal_line())
    lines.append(f"Meja : {order['meja']}")
    lines.append(thermal_line())

    data = order['menu'].split('|')
    for item in data:
        if "TOTAL_QTY:" not in item:
            parts = item.split('\n')
            lines.append(parts[0])
            if len(parts) > 1:
                sub = parts[1].split('  ')
                try:
                    lines.append(f"  x{sub[0]}")
                except Exception:
                    pass

    lines.append(thermal_line())
    lines.append(thermal_center(order['waktu']))
    lines.append("\n\n\n")

    text = "\n".join(lines)

    try:
        print_thermal(text)
    except Exception as e:
        print("PRINT BARISTA ERROR:", e)

    return redirect('/admin')

@app.route('/archive', methods=['POST'])
@login_required
def archive():
    conn = get_db_connection()
    # Mengambil semua data yang BELUM PERNAH DIARSIP (Tanpa batasan jam 12 malam)
    orders = conn.execute("SELECT * FROM orders WHERE status='selesai' AND is_archived=0").fetchall()
    expenses = conn.execute("SELECT * FROM expenses WHERE is_archived=0 AND source='cafe'").fetchall()
    pemasukan_ptbos = conn.execute("SELECT * FROM pemasukan_ptbos WHERE is_archived=0").fetchall()
    stok_data = conn.execute("SELECT * FROM input_stok WHERE is_archived=0").fetchall()

    # Jika tidak ada data sama sekali, jangan buat file
    if not orders and not expenses and not pemasukan_ptbos:
        conn.close()
        return redirect('/admin?msg=no_data')

    # Membuat nama file dengan stempel waktu
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f"Laporan_CafeBos_{timestamp}.xlsx"

    # --- PROSES GENERATE EXCEL ---
    try:
        with pd.ExcelWriter(filename, engine='openpyxl') as writer:
            # --- SHEET PEMASUKAN ---
            if orders:
                data_pemasukan = []
                for row in orders:
                    order_dict = dict(row)
                    
                    # Parsing rincian menu dari string database (format: Nama\nQty Harga Subtotal)
                    menu_data = order_dict['menu'].split('|')
                    subtotal_asli = 0
                    total_dikenakan_ppn = 0
                    list_menu_untuk_excel = []
                    
                    for item in menu_data:
                        if "TOTAL_QTY:" not in item and "\n" in item:
                            try:
                                parts = item.split('\n')
                                nama_menu_lengkap = parts[0]
                                
                                # Cek apakah item kena PPN
                                kena_ppn = "{NON_PPN}" not in nama_menu_lengkap
                                
                                values = parts[1].split('  ')
                                qty_item = values[0]
                                sub_item = int(values[2])
                                
                                subtotal_asli += sub_item
                                if kena_ppn:
                                    total_dikenakan_ppn += sub_item
                                    
                                list_menu_untuk_excel.append(f"{nama_menu_lengkap.replace('{NON_PPN}', '').strip()} (x{qty_item})")
                            except:
                                pass
                    
                    # Hitung PPN hanya dari item yang kena pajak
                    ppn_10 = int(total_dikenakan_ppn * 0.10)
                    total_akhir_bayar = order_dict['total']
                    selisih_bulat = (subtotal_asli + ppn_10) - total_akhir_bayar

                    data_pemasukan.append({
                        'Waktu': order_dict['waktu'],
                        'Meja': order_dict['meja'],
                        'Kasir': order_dict.get('kasir', 'Admin'),
                        'Metode': order_dict.get('metode', 'CASH').upper(),
                        'Menu Orderan': ", ".join(list_menu_untuk_excel),
                        'Subtotal (Asli)': subtotal_asli,
                        'PPN (10%)': ppn_10,
                        'Pembulatan': -selisih_bulat if selisih_bulat != 0 else 0,
                        'Total Bayar': total_akhir_bayar
                    })
                
                df_orders = pd.DataFrame(data_pemasukan)

                # --- LOGIKA AUTO-SUM PEMASUKAN ---
                total_row = {
                    'Waktu': 'TOTAL KESELURUHAN',
                    'Meja': '',
                    'Kasir': '',
                    'Metode': '',
                    'Menu Orderan': '',
                    'Subtotal (Asli)': df_orders['Subtotal (Asli)'].sum(),
                    'PPN (10%)': df_orders['PPN (10%)'].sum(),
                    'Pembulatan': df_orders['Pembulatan'].sum(),
                    'Total Bayar': df_orders['Total Bayar'].sum()
                }
                
                df_orders = pd.concat([df_orders, pd.DataFrame([total_row])], ignore_index=True)
                df_orders.to_excel(writer, sheet_name='Pemasukan', index=False)

            # --- SHEET PENGELUARAN ---
            if expenses:
                data_exp = []
                for row in expenses:
                    exp_dict = dict(row)
                    data_exp.append({
                        'Keterangan': exp_dict['keterangan'],
                        'Jumlah': exp_dict['jumlah'],
                        'Waktu': exp_dict['waktu']
                    })
                    
                df_exp = pd.DataFrame(data_exp)

                # --- LOGIKA AUTO-SUM PENGELUARAN ---
                total_exp_row = {
                    'Keterangan': 'TOTAL PENGELUARAN',
                    'Jumlah': df_exp['Jumlah'].sum(),
                    'Waktu': ''
                }
                df_exp = pd.concat([df_exp, pd.DataFrame([total_exp_row])], ignore_index=True)
                df_exp.to_excel(writer, sheet_name='Pengeluaran', index=False)

            # --- SHEET PEMASUKAN PT BOS ---
            if pemasukan_ptbos:
                data_ptbos = []
                for row in pemasukan_ptbos:
                    r = dict(row)
                    data_ptbos.append({
                        'Keterangan': r['keterangan'],
                        'Jumlah': r['jumlah'],
                        'Waktu': r['waktu']
                    })

                df_ptbos = pd.DataFrame(data_ptbos)

                total_row = {
                    'Keterangan': 'TOTAL PEMASUKAN PT BOS',
                    'Jumlah': df_ptbos['Jumlah'].sum(),
                    'Waktu': ''
                }

                df_ptbos = pd.concat([df_ptbos, pd.DataFrame([total_row])], ignore_index=True)
                df_ptbos.to_excel(writer, sheet_name='Pemasukan PT BOS', index=False)

        
        # Verifikasi file berhasil disimpan sebelum menghapus data
        if not os.path.exists(filename) or os.path.getsize(filename) < 100:
            print(f"WARNING: File {filename} tidak valid, data TIDAK dihapus dari database.")
            conn.close()
            return redirect('/admin?msg=archive_error')
        
        # Upload ke Google Drive
        try:
            folder_id = '1d67utdtLdJbmvNwAVqMPcoYJsqA6K9W5'
            upload_to_gdrive(filename, folder_id)
        except Exception as e:
            print(f"Gagal memanggil fungsi upload: {e}")
                
        # TANDAI DATA SEBAGAI SUDAH DIARSIP
        conn.execute("UPDATE orders SET is_archived=1 WHERE status='selesai' AND is_archived=0")
        conn.execute("UPDATE expenses SET is_archived=1 WHERE is_archived=0")
        conn.execute("UPDATE pemasukan_ptbos SET is_archived=1 WHERE is_archived=0")
        conn.execute("UPDATE input_stok SET is_archived=1 WHERE is_archived=0")
        
        conn.commit()

    except Exception as e:
        print(f"Error saat archive: {e}")
        return f"Terjadi kesalahan saat memproses laporan: {e}"
    finally:
        conn.close()

    return redirect('/admin?status=archived')

@app.route('/delete_archive/<filename>', methods=['POST'])
@login_required
def delete_archive(filename):
    path = os.path.join('.', filename)
    if os.path.exists(path) and filename.startswith('Laporan_CafeBos_') and filename.endswith('.xlsx'):
        import time
        for i in range(5): # Retry up to 5 times
            try:
                os.remove(path)
                
                # Hapus juga bukti yang berpasangan jika ada
                bukti_filename = filename.replace('.xlsx', '.jpg')
                bukti_cash_path = os.path.join('static/uploads/bukti_cash', bukti_filename)
                bukti_nota_path = os.path.join('static/uploads/bukti_nota', bukti_filename)
                
                if os.path.exists(bukti_cash_path):
                    os.remove(bukti_cash_path)
                if os.path.exists(bukti_nota_path):
                    os.remove(bukti_nota_path)
                    
                return redirect('/reports?tab=archive&status=deleted')
            except OSError as e:
                if i == 4: # Last attempt
                    print(f"Error deleting archive {filename}: {e}")
                    return f"Gagal menghapus file (sedang digunakan proses lain): {e}", 500
                time.sleep(0.5) # Wait half a second before retry
        
    return "File tidak valid", 400


@app.route('/rename_archive/<filename>', methods=['POST'])
@login_required
def rename_archive(filename):
    new_name = request.form.get('new_name')
    if not new_name:
        return redirect('/reports?tab=archive&status=error_no_name')
    
    # Pastikan extensi .xlsx tetap ada
    if not new_name.endswith('.xlsx'):
        new_name += '.xlsx'
        
    old_path = os.path.join('.', filename)
    new_path = os.path.join('.', new_name)
    
    if os.path.exists(old_path) and filename.startswith('Laporan_CafeBos_') and filename.endswith('.xlsx'):
        import time
        for i in range(5): # Retry up to 5 times
            try:
                # Rename file Excel
                os.rename(old_path, new_path)
                
                # Rename juga bukti yang berpasangan jika ada
                old_bukti = filename.replace('.xlsx', '.jpg')
                new_bukti = new_name.replace('.xlsx', '.jpg')
                
                bukti_cash_old = os.path.join('static/uploads/bukti_cash', old_bukti)
                bukti_cash_new = os.path.join('static/uploads/bukti_cash', new_bukti)
                
                bukti_nota_old = os.path.join('static/uploads/bukti_nota', old_bukti)
                bukti_nota_new = os.path.join('static/uploads/bukti_nota', new_bukti)
                
                if os.path.exists(bukti_cash_old):
                    os.rename(bukti_cash_old, bukti_cash_new)
                if os.path.exists(bukti_nota_old):
                    os.rename(bukti_nota_old, bukti_nota_new)
                    
                return redirect('/reports?tab=archive&status=renamed')
            except OSError as e:
                if i == 4: # Last attempt
                    print(f"Error renaming archive {filename} to {new_name}: {e}")
                    return f"Gagal mengganti nama file (sedang digunakan proses lain): {e}", 500
                time.sleep(0.5)
    return "File tidak valid atau tidak ditemukan", 400




@app.route('/add_expense', methods=['POST'])
@login_required
def add_expense():
    keterangan = request.form.get('keterangan')
    jumlah_raw = (request.form.get('jumlah'))
    jumlah = int(jumlah_raw.replace('.', ''))
    source = request.form.get('source', 'cafe')
    waktu = datetime.now().strftime("%d-%m-%Y %H:%M:%S")

    conn = get_db_connection()
    conn.execute(
        "INSERT INTO expenses (keterangan, jumlah, waktu, source) VALUES (?, ?, ?, ?)",
        (keterangan, jumlah, waktu, source)
    )
    conn.commit()
    conn.close()

    # Check for redirect parameter
    redirect_target = request.form.get('redirect')
    if redirect_target == 'reports':
        return redirect('/reports')
        
    return redirect('/admin')

@app.route('/add_stok', methods=['POST'])
@login_required
def add_stok():
    keterangan = request.form.get('keterangan')
    qty = int(request.form.get('qty', 0))
    
    # Ambil Harga dan bersihkan format
    harga_raw = request.form.get('harga', '0')
    harga = int(harga_raw.replace('.', '').replace('Rp', '').strip())
    
    waktu = datetime.now().strftime("%d-%m-%Y %H:%M:%S")

    conn = get_db_connection()
    # Ubah 'harga' menjadi 'jumlah' agar sinkron dengan init_db()
    conn.execute(
        "INSERT INTO input_stok (keterangan, qty, jumlah, waktu) VALUES (?, ?, ?, ?)",
        (keterangan, qty, harga, waktu)
    )
    conn.commit()
    conn.close()

    return redirect('/admin')

@app.route('/add_pemasukan_ptbos', methods=['POST'])
@login_required
def add_pemasukan_ptbos():
    nama = request.form.get('nama_pembeli')
    barang = request.form.get('nama_barang')
    nominal_raw = request.form.get('jumlah_nominal')

    jumlah = int(nominal_raw.replace('.', ''))
    waktu = datetime.now().strftime("%d-%m-%Y %H:%M:%S")

    keterangan = f"{nama} | {barang}"

    conn = get_db_connection()
    conn.execute(
        "INSERT INTO pemasukan_ptbos (keterangan, jumlah, waktu) VALUES (?, ?, ?)",
        (keterangan, jumlah, waktu)
    )
    conn.commit()
    conn.close()

    # 🔥 TAMBAHAN: PRINT OTOMATIS
    print_ptbos(keterangan, jumlah, waktu)

    return redirect('/admin')

@app.route('/del_item_order/<int:order_id>/<int:item_index>')
@login_required
def del_item_order(order_id, item_index):
    conn = get_db_connection()
    
    # 1. Ambil data pesanan
    order = conn.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
    
    if order:
        # 2. Sesuai format Anda, menu dipisah menggunakan karakter '|'
        menu_items = order['menu'].split('|')
        
        if 0 <= item_index < len(menu_items):
            # 3. Ambil data item yang akan dihapus untuk mengurangi total harga
            # Format item Anda: "Nama\nQty Harga Subtotal"
            item_to_remove = menu_items[item_index]
            
            # Cek jika bukan tag TOTAL_QTY
            if "TOTAL_QTY:" not in item_to_remove:
                try:
                    # Ambil subtotal dari baris kedua item tersebut
                    # parts[1] biasanya berisi "2  15000  30000"
                    parts = item_to_remove.split('\n')
                    if len(parts) > 1:
                        # Split berdasarkan spasi ganda sesuai format order() Anda
                        values = parts[1].split('  ')
                        subtotal_item = int(values[2])
                        
                        # Update total harga di database
                        new_total = order['total'] - subtotal_item
                        
                        # 4. Hapus item dari list
                        menu_items.pop(item_index)
                        
                        # 5. Gabungkan kembali dengan '|'
                        new_menu = "|".join(menu_items)
                        
                        conn.execute("UPDATE orders SET menu=?, total=? WHERE id=?", 
                                     (new_menu, new_total, order_id))
                except Exception as e:
                    print("Error parsing price:", e)
                    # Jika gagal hitung harga, hapus item saja tanpa ubah total
                    menu_items.pop(item_index)
                    new_menu = "|".join(menu_items)
                    conn.execute("UPDATE orders SET menu=? WHERE id=?", (new_menu, order_id))

        conn.commit()
    
    conn.close()
    # Kembali ke halaman admin (kasir) setelah hapus
    return redirect('/admin')

@app.route('/update_item_qty/<int:order_id>/<int:item_index>', methods=['POST'])
@login_required
def update_item_qty(order_id, item_index):
    """Edit qty item dalam pesanan. Jika qty jadi 0, item dihapus."""
    new_qty = int(request.form.get('new_qty', 0))
    
    conn = get_db_connection()
    order = conn.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
    
    if order and order['status'] == 'pending':
        menu_items = order['menu'].split('|')
        # Filter out empty items but keep TOTAL_QTY
        real_items = []
        total_qty_tag = ""
        for mi in menu_items:
            if "TOTAL_QTY:" in mi:
                total_qty_tag = mi
            elif mi.strip():
                real_items.append(mi)
        
        if 0 <= item_index < len(real_items):
            target_item = real_items[item_index]
            parts = target_item.split('\n')
            
            if len(parts) >= 2:
                try:
                    values = parts[1].split('  ')
                    old_qty = int(values[0])
                    harga_satuan = int(values[1])
                    old_subtotal = int(values[2])
                    
                    if new_qty <= 0:
                        # Hapus item sepenuhnya
                        real_items.pop(item_index)
                        new_total = order['total'] - old_subtotal
                    else:
                        # Update qty dan subtotal
                        new_subtotal = new_qty * harga_satuan
                        selisih = new_subtotal - old_subtotal
                        parts[1] = f"{new_qty}  {harga_satuan}  {new_subtotal}"
                        real_items[item_index] = '\n'.join(parts)
                        new_total = order['total'] + selisih
                    
                    # Hitung ulang total_qty
                    total_qty_final = 0
                    for ri in real_items:
                        ri_parts = ri.split('\n')
                        if len(ri_parts) >= 2:
                            try:
                                total_qty_final += int(ri_parts[1].split('  ')[0])
                            except:
                                pass
                    
                    # Susun kembali menu string
                    if real_items:
                        new_menu = "|".join(real_items) + f"|TOTAL_QTY:{total_qty_final}"
                    else:
                        new_menu = ""
                        new_total = 0
                    
                    conn.execute("UPDATE orders SET menu=?, total=? WHERE id=?",
                                 (new_menu, max(new_total, 0), order_id))
                    
                    # Hapus pesanan jika tidak ada item tersisa
                    if not real_items:
                        conn.execute("DELETE FROM orders WHERE id=?", (order_id,))
                        
                except Exception as e:
                    print(f"Error updating item qty: {e}")
    
    conn.commit()
    conn.close()
    return redirect('/admin')

@app.route('/edit_meja/<int:order_id>')
@login_required
def edit_meja(order_id):
    meja_baru = request.args.get('meja_baru')

    if meja_baru:
        conn = get_db_connection()
        conn.execute(
            "UPDATE orders SET meja=? WHERE id=?",
            (meja_baru, order_id)
        )
        conn.commit()
        conn.close()

    return redirect('/admin')

@app.route('/reprint_thermal/<int:id>')
@login_required
def reprint_thermal(id):
    kasir = request.args.get('kasir', 'Admin')
    conn = get_db_connection()
    order = conn.execute("SELECT * FROM orders WHERE id=?", (id,)).fetchone()
    conn.close()

    if not order: return redirect('/admin')

    # Menggunakan fungsi helper global: thermal_center, thermal_line, fmt_idr, thermal_row

    lines = []
    lines.append(thermal_center("CAFE BOS"))
    lines.append(thermal_center("Citraland Tallasa City"))
    lines.append(thermal_center("Ruko A1 No.3, Kapasa"))
    lines.append(thermal_center("Tamalanrea, Kota Makassar")) 
    lines.append(thermal_line())
    lines.append(f"Meja  : {order['meja']}")
    lines.append(f"Kasir : {kasir}")
    lines.append(thermal_line())

    data = order['menu'].split('|')
    subtotal_hitung = 0
    for item in data:
        if "TOTAL_QTY:" not in item:
            parts = item.split('\n')
            lines.append(parts[0])
            if len(parts) > 1:
                sub = parts[1].split('  ')
                try:
                    price_item = int(sub[2])
                    subtotal_hitung += price_item
                    lines.append(thermal_row(f"{sub[0]} x {fmt_idr(int(sub[1]))}", fmt_idr(price_item)))
                except: pass

    lines.append(thermal_line())
    
    # Hitung PPN 10% dari rincian menu
    ppn_hitung = int(subtotal_hitung * 0.10)
    total_seharusnya = subtotal_hitung + ppn_hitung
    total_di_db = order['total'] # Ini angka final yang dibayar dulu
    selisih = total_seharusnya - total_di_db

    lines.append(thermal_row("Subtotal", fmt_idr(subtotal_hitung)))
    lines.append(thermal_row("PPN 10%", fmt_idr(ppn_hitung)))
    
    if selisih > 0:
        lines.append(thermal_row("Disc", f"-{fmt_idr(selisih)}"))
    elif selisih < 0:
        lines.append(thermal_row("Add", f"+{fmt_idr(abs(selisih))}"))

    lines.append(thermal_line())
    lines.append(thermal_row("TOTAL BAYAR", "Rp " + fmt_idr(total_di_db)))
    
    lines.append(thermal_line())
    lines.append(thermal_center(order['waktu']))
    lines.append("")
    lines.append(thermal_center("DICETAK ULANG"))
    lines.append("\n\n\n")

    text_final = "\n".join(lines)
    try:
        print_thermal(text_final)
    except Exception as e:
        print("PRINT ERROR:", e)

    return redirect('/admin')

def print_ptbos(keterangan, jumlah, waktu):
    WIDTH = 42  # cocok untuk thermal 80mm

    def thermal_center(t): return t.center(WIDTH)
    def thermal_line(): return "-" * WIDTH
    def fmt_idr(n): return "{:,.0f}".format(n).replace(",", ".")

    lines = []
    lines.append(thermal_center("PT. BIKIN ORANG SUKSES"))
    lines.append(thermal_center("Citraland Tallasa City"))
    lines.append(thermal_center("Ruko A1 No.3, Kapasa"))
    lines.append(thermal_center("Tamalanrea, Kota Makassar")) 
    lines.append(thermal_line())

    # Pecah keterangan
    try:
        nama, barang = keterangan.split(" | ")
    except Exception:
        nama, barang = keterangan, ""

    lines.append(f"Nama   : {nama}")
    lines.append(f"barang : {barang}")

    lines.append(thermal_line())
    lines.append(f"TOTAL  : Rp {fmt_idr(jumlah)}")
    lines.append(thermal_line())

    lines.append(thermal_center(waktu))
    lines.append("")
    lines.append(thermal_center("Terima Kasih"))
    lines.append("\n\n\n")

    text = "\n".join(lines)

    try:
        print_thermal(text)
    except Exception as e:
        print("PRINT PT BOS ERROR:", e)

@app.route('/reports')
@login_required
def reports():
    conn = get_db_connection()
    # --- PART 1: ANALYTICS LOGIC (Live DB) ---
    # Ambil data LIVE (Belum diarsip)
    revenue_cafe = conn.execute("SELECT SUM(total) FROM orders WHERE status='selesai' AND is_archived=0").fetchone()[0] or 0
    revenue_ptbos = conn.execute("SELECT SUM(jumlah) FROM pemasukan_ptbos WHERE is_archived=0").fetchone()[0] or 0
    total_pemasukan_gabungan = revenue_cafe + revenue_ptbos
    
    # 1. KAS LACI CAFE SAAT INI (LIVE)
    # Ambil pengeluaran cafe (source='cafe') dan stok yang BELUM DIARSIP
    expenses_cafe_today_list = conn.execute("SELECT * FROM expenses WHERE source='cafe' AND is_archived=0").fetchall()
    stock_today_list = conn.execute("SELECT * FROM input_stok WHERE is_archived=0").fetchall()
    
    expenses_cafe_sum = sum(e['jumlah'] for e in expenses_cafe_today_list)
    stock_sum = sum(s['jumlah'] * s['qty'] for s in stock_today_list)
    
    # Revenue Cafe (Cash Only) yang BELUM DIARSIP
    cash_cafe_today_raw = conn.execute("SELECT SUM(total) FROM orders WHERE status='selesai' AND LOWER(metode)='cash' AND is_archived=0").fetchone()[0] or 0
    total_cash_cafe_live = cash_cafe_today_raw - expenses_cafe_sum - stock_sum

    # 2. KAS LACI RESEPSIONIS SAAT INI (LIVE)
    # Ambil pengeluaran resepsionis (source='reception') yang BELUM DIARSIP
    expenses_reception_today_list = conn.execute("SELECT * FROM expenses WHERE source='reception' AND is_archived=0").fetchall()
    expenses_reception_sum = sum(e['jumlah'] for e in expenses_reception_today_list)
    
    # Revenue PT BOS yang BELUM DIARSIP
    revenue_ptbos_unarchived = conn.execute("SELECT SUM(jumlah) FROM pemasukan_ptbos WHERE is_archived=0").fetchone()[0] or 0
    total_cash_reception_live = revenue_ptbos_unarchived - expenses_reception_sum
    
    # Data lainnya untuk Analytics (Gunakan data UNARCHIVED agar konsisten dengan dashboard)
    revenue_cafe_unarchived = conn.execute("SELECT SUM(total) FROM orders WHERE status='selesai' AND is_archived=0").fetchone()[0] or 0
    total_pemasukan_gabungan = revenue_cafe_unarchived + revenue_ptbos_unarchived
    
    profit = revenue_cafe_unarchived - (expenses_cafe_sum + stock_sum) # Laba Cafe sesi ini
    
    total_orders = conn.execute("SELECT COUNT(id) FROM orders WHERE status='selesai' AND is_archived=0").fetchone()[0] or 0
    total_qris_live = conn.execute("SELECT SUM(total) FROM orders WHERE status='selesai' AND LOWER(metode)='qris' AND is_archived=0").fetchone()[0] or 0
    avg_order = revenue_cafe_unarchived / total_orders if total_orders > 0 else 0
    
    all_sales = conn.execute("SELECT total, waktu FROM orders WHERE status='selesai'").fetchall()
    # DATA MANUAL TREN PENJUALAN (April 2026)
    daily_sales = {
        "01-04-2026": 98000, "02-04-2026": 317500, "03-04-2026": 646000,
        "04-04-2026": 292000, "05-04-2026": 188000, "06-04-2026": 1004000,
        "07-04-2026": 327500, "08-04-2026": 595000, "09-04-2026": 647500,
        "10-04-2026": 192950, "11-04-2026": 681220, "12-04-2026": 544050,
        "13-04-2026": 697900, "14-04-2026": 478360, "15-04-2026": 299720,
        "16-04-2026": 774600, "17-04-2026": 657540, "18-04-2026": 573790,
        "19-04-2026": 239100, "20-04-2026": 297700, "21-04-2026": 1171150,
        "22-04-2026": 851150, "23-04-2026": 723000, "24-04-2026": 1510150,
        "25-04-2026": 927100, "26-04-2026": 709650
    }
    
    manual_dates = set(daily_sales.keys())
    for s in all_sales:
        try:
            date_part = s['waktu'].split(' ')[0]
            if date_part not in manual_dates:
                daily_sales[date_part] = daily_sales.get(date_part, 0) + s['total']
        except: pass
    
    today_dt = datetime.now()
    chart_labels = []
    chart_data = []
    for i in range(29, -1, -1):
        day_str = (today_dt - timedelta(days=i)).strftime("%d-%m-%Y")
        chart_labels.append(day_str)
        chart_data.append(daily_sales.get(day_str, 0))
    
    metode_stats = conn.execute("SELECT LOWER(metode) as metode_clean, COUNT(id) as jumlah FROM orders WHERE status='selesai' AND is_archived=0 GROUP BY metode_clean").fetchall()
    pay_labels = [str(m['metode_clean']).upper() if m['metode_clean'] else 'CASH' for m in metode_stats]
    pay_data = [int(m['jumlah']) for m in metode_stats]

    # --- PART 2: ARCHIVE LOGIC (Excel Files) ---
    folder_path = '.' 
    files = [f for f in os.listdir(folder_path) if f.endswith('.xlsx') and f.startswith('Laporan_CafeBos_')]
    archive_data = []
    rekap_bulanan = {}
    rekap_tahunan = {}

    for file in sorted(files, reverse=True):
        path = os.path.join(folder_path, file)
        try:
            with pd.ExcelFile(path) as xls:
                sheets_data = []
                total_pemasukan_cafe = 0
                total_cash_cafe = 0
                total_qris_cafe = 0
                total_pengeluaran = 0

                for sheet_name in xls.sheet_names:
                    df = pd.read_excel(xls, sheet_name=sheet_name)
                    if not df.empty:
                        kolom_pertama = df.columns[0]
                        df_clean = df[~df[kolom_pertama].astype(str).str.contains('TOTAL', case=False, na=False)].copy()
                    else: df_clean = df.copy()

                    if sheet_name == "Pemasukan":
                        if 'Total Bayar' in df_clean.columns:
                            val_series = df_clean['Total Bayar'].astype(str).str.replace('.', '', regex=False).str.replace(',', '', regex=False)
                            numeric_vals = pd.to_numeric(val_series, errors='coerce').fillna(0)
                            total_pemasukan_cafe = numeric_vals.sum()
                            if 'Metode' in df_clean.columns:
                                total_cash_cafe = numeric_vals[df_clean['Metode'].str.contains('CASH', na=False, case=False)].sum()
                                total_qris_cafe = numeric_vals[df_clean['Metode'].str.contains('QRIS', na=False, case=False)].sum()
                            else:
                                total_cash_cafe = total_pemasukan_cafe
                                total_qris_cafe = 0
                    elif sheet_name == "Pemasukan PT BOS":
                        kolom_jml = 'Jumlah' if 'Jumlah' in df_clean.columns else 'Nominal'
                        if kolom_jml in df_clean.columns:
                            val_pt = df_clean[kolom_jml].astype(str).str.replace('.', '', regex=False).str.replace(',', '', regex=False)
                            total_ptbos_file = pd.to_numeric(val_pt, errors='coerce').fillna(0).sum()
                            # PT BOS dianggap cash masuk ke Resepsionis
                            total_pemasukan_cafe += total_ptbos_file
                            total_cash_cafe += total_ptbos_file
                    elif sheet_name == "Pengeluaran":
                        kolom_out = 'Jumlah' if 'Jumlah' in df_clean.columns else 'Total'
                        if kolom_out in df_clean.columns:
                            val_out = df_clean[kolom_out].astype(str).str.replace('.', '', regex=False).str.replace(',', '', regex=False)
                            total_pengeluaran = pd.to_numeric(val_out, errors='coerce').fillna(0).sum()

                    sheets_data.append({'nama_sheet': sheet_name, 'kolom': df.columns.tolist(), 'data': df.fillna('').values.tolist()})

            summary = {
                'total_pemasukan': total_pemasukan_cafe,
                'total_cash': total_cash_cafe - total_pengeluaran,
                'total_qris': total_qris_cafe,
                'total_pengeluaran': total_pengeluaran,
                'total_pendapatan': total_pemasukan_cafe - total_pengeluaran,
                'total_cash_raw': total_cash_cafe
            }
            bukti_filename = file.replace('.xlsx', '.jpg')
            has_bukti_cash = os.path.exists(os.path.join('static/uploads/bukti_cash', bukti_filename))
            has_bukti_nota = os.path.exists(os.path.join('static/uploads/bukti_nota', bukti_filename))

            archive_data.append({'nama_file': file, 'sheets': sheets_data, 'summary': summary, 'has_bukti_cash': has_bukti_cash, 'has_bukti_nota': has_bukti_nota})

            try:
                date_str = file.split('_')[2]
                year, month = date_str[:4], date_str[:6]
                if month not in rekap_bulanan: 
                    rekap_bulanan[month] = {'total_pemasukan': 0, 'total_pengeluaran': 0, 'total_pendapatan': 0, 'total_cash': 0, 'total_qris': 0, 'files_count': 0}
                rekap_bulanan[month]['total_pemasukan'] += summary['total_pemasukan']
                rekap_bulanan[month]['total_pengeluaran'] += summary['total_pengeluaran']
                rekap_bulanan[month]['total_pendapatan'] += summary['total_pendapatan']
                rekap_bulanan[month]['total_cash'] += summary['total_cash']
                rekap_bulanan[month]['total_qris'] += summary['total_qris']
                rekap_bulanan[month]['files_count'] += 1

                if year not in rekap_tahunan: 
                    rekap_tahunan[year] = {'total_pemasukan': 0, 'total_pengeluaran': 0, 'total_pendapatan': 0, 'total_cash': 0, 'total_qris': 0, 'files_count': 0}
                rekap_tahunan[year]['total_pemasukan'] += summary['total_pemasukan']
                rekap_tahunan[year]['total_pengeluaran'] += summary['total_pengeluaran']
                rekap_tahunan[year]['total_pendapatan'] += summary['total_pendapatan']
                rekap_tahunan[year]['total_cash'] += summary['total_cash']
                rekap_tahunan[year]['total_qris'] += summary['total_qris']
                rekap_tahunan[year]['files_count'] += 1
            except: pass
        except Exception as e: print(f"Error baca file {file}: {e}")

    # HITUNG SALDO AKHIR
    total_archive_cash = sum(f['summary']['total_cash'] for f in archive_data)
    total_archive_qris = sum(f['summary']['total_qris'] for f in archive_data)
    total_archive_income = sum(f['summary']['total_pemasukan'] for f in archive_data)
    total_archive_expense = sum(f['summary']['total_pengeluaran'] for f in archive_data)
    total_archive_profit = sum(f['summary']['total_pendapatan'] for f in archive_data)
    
    # Ambil SEMUA pengeluaran khusus dari Dana/Vault (akumulatif)
    expenses_dana_list = conn.execute("SELECT * FROM expenses WHERE source IN ('dana', 'reception') ORDER BY id DESC").fetchall()
    expenses_dana_sum = sum(e['jumlah'] for e in expenses_dana_list if e['source'] == 'dana' or (e['source'] == 'reception' and e['is_archived'] == 1))
    
    # Saldo Dana Tersimpan (Vault) = Total Net Cash (Arsip) - Pengeluaran dari Dana masa lalu
    # Pengeluaran resepsionis hari ini tidak memotong Vault yang sudah tersimpan, tapi memotong Kas Resepsionis Live.
    saldo_dana_tersimpan = total_archive_cash - sum(e['jumlah'] for e in expenses_dana_list if e['source'] == 'dana')
    
    if saldo_dana_tersimpan < 0: saldo_dana_tersimpan = 0

    # Ambil Modal Kembalian dari Settings
    modal_kembalian_row = conn.execute("SELECT value FROM settings WHERE key='modal_kembalian'").fetchone()
    modal_kembalian = int(modal_kembalian_row['value']) if modal_kembalian_row else 0
    
    conn.close()
    
    return render_template('reports.html', 
                           total_revenue=revenue_cafe,
                           revenue_ptbos=revenue_ptbos,
                           total_pemasukan_gabungan=total_pemasukan_gabungan,
                           expenses=expenses_cafe_sum + stock_sum, # Hanya beban cafe
                           profit=profit,
                           saldo_dana_tersimpan=saldo_dana_tersimpan,
                           modal_kembalian=modal_kembalian,
                           total_cash_cafe_live=total_cash_cafe_live,
                           total_cash_reception_live=total_cash_reception_live,
                           total_qris_live=total_qris_live,
                           expenses_live_list=expenses_cafe_today_list,
                           expenses_dana_list=expenses_dana_list,
                           stock_expenses_live_list=stock_today_list,
                           total_orders=total_orders, avg_order=avg_order, 
                           chart_labels=chart_labels, chart_data=chart_data, 
                           pay_labels=pay_labels, pay_data=pay_data,
                           archive_data=archive_data, rekap_bulanan=rekap_bulanan, rekap_tahunan=rekap_tahunan,
                           total_archive_cash=total_archive_cash, total_archive_qris=total_archive_qris,
                           total_archive_income=total_archive_income, total_archive_expense=total_archive_expense,
                           total_archive_profit=total_archive_profit)

@app.route('/settle_dana', methods=['POST'])
@login_required
def settle_dana():
    conn = get_db_connection()
    # 1. Hitung total cash dari arsip
    files = [f for f in os.listdir('.') if f.endswith('.xlsx') and f.startswith('Laporan_CafeBos_')]
    total_archive_cash = 0
    for file in files:
        try:
            with pd.ExcelFile(file) as xls:
                pemasukan_df = pd.read_excel(xls, 'Pemasukan')
                pengeluaran_df = pd.read_excel(xls, 'Pengeluaran')
                
                # Pemasukan Cash
                cash_vals = pd.to_numeric(pemasukan_df[pemasukan_df['Metode'].str.contains('CASH', na=False, case=False)]['Total Bayar'].astype(str).str.replace('.', ''), errors='coerce').fillna(0)
                total_cash = cash_vals.sum()
                
                # Pengeluaran
                kolom_out = 'Jumlah' if 'Jumlah' in pengeluaran_df.columns else 'Total'
                out_vals = pd.to_numeric(pengeluaran_df[kolom_out].astype(str).str.replace('.', ''), errors='coerce').fillna(0)
                total_out = out_vals.sum()
                
                total_archive_cash += (total_cash - total_out)
        except: pass
    
    # 2. Kurangi dengan pengeluaran dana yang sudah ada
    expenses_dana_sum = conn.execute("SELECT SUM(jumlah) FROM expenses WHERE source='dana'").fetchone()[0] or 0
    
    saldo_sekarang = total_archive_cash - expenses_dana_sum
    
    if saldo_sekarang > 0:
        waktu = datetime.now().strftime("%d-%m-%Y %H:%M:%S")
        keterangan = "PEMBUKUAN (Reset Saldo ke Nol)"
        conn.execute(
            "INSERT INTO expenses (keterangan, jumlah, waktu, source) VALUES (?, ?, ?, ?)",
            (keterangan, int(saldo_sekarang), waktu, 'dana')
        )
        conn.commit()
    
    conn.close()
    return redirect('/reports?tab=dana&status=settled')

@app.route('/update_settings', methods=['POST'])
@login_required
def update_settings():
    conn = get_db_connection()
    for key, value in request.form.items():
        # Bersihkan format rupiah jika ada
        clean_value = value.replace('.', '').replace('Rp', '').strip()
        conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, clean_value))
    conn.commit()
    conn.close()
    
    # Check for redirect
    redirect_target = request.form.get('redirect', 'reports')
    if redirect_target == 'reports':
        return redirect('/reports?tab=dana&status=updated')
    return redirect('/admin')


@app.route('/download_pdf/<filename>')
@login_required
def download_pdf(filename):
    path = os.path.join('.', filename)
    if not os.path.exists(path):
        return "File tidak ditemukan", 404

    try:
        with pd.ExcelFile(path) as xls:
            # Cari bukti yang berpasangan
            bukti_cash_path = os.path.join('static/uploads/bukti_cash', filename.replace('.xlsx', '.jpg'))
            bukti_nota_path = os.path.join('static/uploads/bukti_nota', filename.replace('.xlsx', '.jpg'))
            
            bukti_c_full = bukti_cash_path if os.path.exists(bukti_cash_path) else None
            bukti_n_full = bukti_nota_path if os.path.exists(bukti_nota_path) else None
            
            pdf = generate_report_pdf(filename, xls, bukti_cash_path=bukti_c_full, bukti_nota_path=bukti_n_full)

            # Output to buffer
            pdf_output = io.BytesIO()
            pdf_bytes = pdf.output(dest='S')
            pdf_output.write(pdf_bytes)
            pdf_output.seek(0)
            
            pdf_filename = filename.replace('.xlsx', '.pdf')
            return send_file(pdf_output, as_attachment=True, download_name=pdf_filename, mimetype='application/pdf')

    except Exception as e:
        print(f"Error generate PDF: {e}")
        import traceback
        traceback.print_exc()
        return f"Gagal membuat PDF: {e}", 500

@app.route('/upload_lampiran/<filename>', methods=['POST'])
@login_required
def upload_lampiran(filename):
    file_cash = request.files.get('bukti_cash')
    file_nota = request.files.get('bukti_nota')
    
    if not file_cash and not file_nota:
        return redirect('/arsip_laporan?status=error_no_file')

    # Buat folder jika belum ada
    if not os.path.exists('static/uploads/bukti_cash'):
        os.makedirs('static/uploads/bukti_cash', exist_ok=True)
    if not os.path.exists('static/uploads/bukti_nota'):
        os.makedirs('static/uploads/bukti_nota', exist_ok=True)
    
    # Nama file bukti (excel -> jpg)
    bukti_filename = filename.replace('.xlsx', '.jpg')
    
    if file_cash:
        file_cash.save(os.path.join('static/uploads/bukti_cash', bukti_filename))
    
    if file_nota:
        file_nota.save(os.path.join('static/uploads/bukti_nota', bukti_filename))
    
    return redirect('/arsip_laporan?status=uploaded')

# Tetap pertahankan route lama agar tidak break jika ada form yang masih mengarah ke sini
@app.route('/upload_bukti_cash/<filename>', methods=['POST'])
@login_required
def upload_bukti_cash(filename):
    return upload_lampiran(filename)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        conn = get_db_connection()
        user = conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
        conn.close()

        if user and check_password_hash(user['password'], password):
            session['user'] = username
            return redirect('/admin')
        else:
            return render_template('login.html', error="Username atau Password salah!")

    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect('/login')

@app.route('/profile')
def profile():
    return render_template('profile.html')

@app.route('/ptbos')
@login_required
def ptbos():
    return render_template('ptbos.html')

@app.route('/submit_pembelian', methods=['POST'])
@login_required
def submit_pembelian():
    tanggal = request.form.get('tanggal', '')
    nama_member = request.form.get('nama_member', '')
    jenis_order = request.form.get('jenis_order', '')
    keterangan_extra = request.form.get('keterangan', '')
    
    produk_list = request.form.getlist('produk[]')
    jumlah_list = request.form.getlist('jumlah[]')
    paket_list = request.form.getlist('paket[]')
    
    total_semua = 0
    detail_items = []
    
    for i in range(len(produk_list)):
        harga_satuan = int(produk_list[i])
        qty = int(jumlah_list[i]) if i < len(jumlah_list) else 1
        paket = paket_list[i] if i < len(paket_list) else '-'
        subtotal = harga_satuan * qty
        total_semua += subtotal
        detail_items.append(f"{paket} Rp{fmt_idr(harga_satuan)} x{qty}")
    
    waktu = datetime.now().strftime("%d-%m-%Y %H:%M:%S")
    keterangan = f"{nama_member} | {jenis_order} | {', '.join(detail_items)}"
    if keterangan_extra and keterangan_extra.strip() != '-':
        keterangan += f" | {keterangan_extra}"
    
    conn = get_db_connection()
    conn.execute(
        "INSERT INTO pemasukan_ptbos (keterangan, jumlah, waktu) VALUES (?, ?, ?)",
        (keterangan, total_semua, waktu)
    )
    conn.commit()
    conn.close()
    
    # Print struk otomatis
    print_ptbos(keterangan, total_semua, waktu)
    
    return redirect('/admin')

@app.route('/menu_display')
def menu_display():
    conn = get_db_connection()
    # Hanya tampilkan menu yang ditandai untuk TV
    daftar_menu = conn.execute('SELECT * FROM menus WHERE show_on_tv = 1 ORDER BY kategori ASC').fetchall()
    conn.close()
    return render_template('menu_display.html', menus=daftar_menu)

@app.route('/menu')
def menu():
    conn = get_db_connection()
    daftar_menu = conn.execute('SELECT * FROM menus ORDER BY kategori ASC').fetchall()
    conn.close()
    return render_template('menu.html', menus=daftar_menu)

# --- MODUL ABSENSI KARYAWAN (PORTAL MANDIRI) ---
@app.route('/absensi')
@login_required
def absensi_portal():
    conn = get_db_connection()
    employees = conn.execute("SELECT * FROM employees ORDER BY nama ASC").fetchall()
    
    today = datetime.now().strftime("%d-%m-%Y")
    attendance_today = conn.execute("""
        SELECT a.*, e.nama 
        FROM attendance a 
        JOIN employees e ON a.employee_id = e.id 
        WHERE a.tanggal = ?
    """, (today,)).fetchall()
    
    rekap_all = conn.execute("""
        SELECT a.*, e.nama 
        FROM attendance a 
        JOIN employees e ON a.employee_id = e.id 
        ORDER BY a.id DESC LIMIT 100
    """).fetchall()
    
    conn.close()
    return render_template('absensi.html', 
                         employees=employees, 
                         attendance_today=attendance_today, 
                         rekap_all=rekap_all)

@app.route('/add_employee', methods=['POST'])
@login_required
def add_employee():
    nama = request.form.get('nama')
    pin = request.form.get('pin')
    conn = get_db_connection()
    try:
        conn.execute("INSERT INTO employees (nama, pin) VALUES (?, ?)", (nama, pin))
        conn.commit()
    except: pass
    conn.close()
    return redirect('/absensi')

@app.route('/del_employee/<int:id>', methods=['POST'])
@login_required
def del_employee(id):
    conn = get_db_connection()
    conn.execute("DELETE FROM employees WHERE id=?", (id,))
    conn.execute("DELETE FROM attendance WHERE employee_id=?", (id,))
    conn.commit()
    conn.close()
    return redirect('/absensi')

@app.route('/register_face', methods=['POST'])
@login_required
def register_face():
    employee_id = request.form.get('employee_id')
    descriptor = request.form.get('descriptor') # JSON string of face embedding
    
    conn = get_db_connection()
    conn.execute("UPDATE employees SET face_descriptor=? WHERE id=?", (descriptor, employee_id))
    conn.commit()
    conn.close()
    return jsonify({'status': 'success', 'message': 'Wajah berhasil didaftarkan!'})

def handle_attendance_logic(employee_id, emp_name):
    now = datetime.now()
    today = now.strftime("%d-%m-%Y")
    waktu_now = now.strftime("%H:%M:%S")
    hour = now.hour
    
    conn = get_db_connection()
    existing = conn.execute("SELECT * FROM attendance WHERE employee_id=? AND tanggal=?", 
                           (employee_id, today)).fetchone()
    
    status = 'success'
    msg = ""

    # Logika Fleksibel:
    # 1. Masuk: Bisa kapan saja (disarankan jam operasional)
    # 2. Pulang: Jika jam 00:00 - 04:00 pagi, cari absen masuk kemarin. 
    #    Jika jam > 04:00, cari absen masuk hari ini.
    
    if 0 <= hour <= 4:
        # Sedang lewat tengah malam, cari absen masuk kemarin
        target_date = (now - timedelta(days=1)).strftime("%d-%m-%Y")
    else:
        target_date = today

    existing = conn.execute("SELECT * FROM attendance WHERE employee_id=? AND tanggal=?", 
                           (employee_id, target_date)).fetchone()

    if not existing:
        # Jika belum ada absen di tanggal target, maka ini dianggap Absen Masuk baru
        conn.execute("INSERT INTO attendance (employee_id, tanggal, jam_masuk) VALUES (?, ?, ?)",
                     (employee_id, today, waktu_now))
        msg = f"Selamat Bekerja, {emp_name}! (Masuk: {waktu_now})"
    elif not existing['jam_pulang']:
        # Jika sudah masuk tapi belum pulang, maka ini Absen Pulang
        conn.execute("UPDATE attendance SET jam_pulang=? WHERE id=?", (waktu_now, existing['id']))
        msg = f"Hati-hati di jalan, {emp_name}! (Pulang: {waktu_now} - Sesi {target_date})"
    else:
        # Jika sudah masuk dan sudah pulang
        msg = f"Anda sudah menyelesaikan absensi untuk sesi {target_date}."
        status = 'error'
        
    conn.commit()
    conn.close()
    return {'status': status, 'message': msg}

@app.route('/submit_absensi', methods=['POST'])
def submit_absensi():
    employee_id = request.form.get('employee_id')
    pin = request.form.get('pin')
    
    conn = get_db_connection()
    emp = conn.execute("SELECT * FROM employees WHERE id=? AND pin=?", (employee_id, pin)).fetchone()
    conn.close()
    
    if not emp:
        return jsonify({'status': 'error', 'message': 'PIN Salah!'})
    
    result = handle_attendance_logic(employee_id, emp['nama'])
    return jsonify(result)

@app.route('/submit_absensi_face', methods=['POST'])
def submit_absensi_face():
    employee_id = request.form.get('employee_id')
    
    conn = get_db_connection()
    emp = conn.execute("SELECT * FROM employees WHERE id=?", (employee_id,)).fetchone()
    conn.close()
    
    if not emp:
        return jsonify({'status': 'error', 'message': 'Karyawan tidak ditemukan!'})
    
    result = handle_attendance_logic(employee_id, emp['nama'])
    return jsonify(result)

@app.route('/export_absensi')
@login_required
def export_absensi():
    conn = get_db_connection()
    # Ambil semua data untuk laporan
    data = conn.execute("""
        SELECT a.*, e.nama 
        FROM attendance a 
        JOIN employees e ON a.employee_id = e.id 
        ORDER BY a.id ASC
    """).fetchall()
    
    if not data:
        conn.close()
        return "Tidak ada data untuk direkap.", 400
        
    # Generate PDF
    today_str = datetime.now().strftime("%d-%m-%Y")
    filename = generate_attendance_pdf(data, today_str)
    
    # HAPUS DATA SETELAH REKAP
    conn.execute("DELETE FROM attendance")
    conn.commit()
    conn.close()
    
    return send_from_directory('static', filename, as_attachment=True)

# Routes analytics dan arsip_laporan lama telah digabung ke /reports
@app.route('/analytics')
@login_required
def old_analytics(): return redirect(url_for('reports'))

@app.route('/arsip_laporan')
@login_required
def old_arsip(): return redirect(url_for('reports'))

if __name__ == '__main__':
    # Jalankan aplikasi (Akses via IP lokal jika ingin dibuka lewat HP lain)
    app.run(host='0.0.0.0', port=5000, debug=True)