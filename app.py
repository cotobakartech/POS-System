from flask import Flask, render_template, request, redirect, url_for, session, send_file, jsonify, send_from_directory
from datetime import datetime, timedelta
from functools import wraps
import sqlite3
import pandas as pd
import win32print
import json
import os
import io
import cv2
# Google dependencies removed for pure POS simplicity
from fpdf import FPDF
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import requests
from pdf_generator import generate_report_pdf

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'pos_system_ultra_secure_key_2026')
app.config['UPLOAD_FOLDER'] = 'static/menu'
DATABASE = 'possystem.db'

def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def get_setting(key, default=None):
    conn = get_db_connection()
    row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    conn.close()
    return row['value'] if row else default

def save_setting(key, value):
    conn = get_db_connection()
    exists = conn.execute("SELECT 1 FROM settings WHERE key=?", (key,)).fetchone()
    if exists:
        conn.execute("UPDATE settings SET value=? WHERE key=?", (value, key))
    else:
        conn.execute("INSERT INTO settings (key, value) VALUES (?, ?)", (key, value))
    conn.commit()
    conn.close()

def list_printers():
    try:
        flags = win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
        printers = [printer[2] for printer in win32print.EnumPrinters(flags)]
        return printers
    except Exception:
        return []

def get_width_chars(width):
    return 32 if str(width) == '58' else 48

def pad_receipt_line(left, right, width_chars):
    left_text = str(left)
    right_text = str(right)
    space = width_chars - len(left_text) - len(right_text)
    if space < 1:
        return (left_text + ' ' + right_text)[:width_chars]
    return left_text + (' ' * space) + right_text

def image_to_escpos_raster(image_path, max_width=384):
    if not image_path or not os.path.exists(image_path):
        return b''

    image = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
    if image is None:
        return b''

    height, width = image.shape
    if width > max_width:
        ratio = max_width / width
        image = cv2.resize(image, (max_width, int(height * ratio)), interpolation=cv2.INTER_AREA)
        height, width = image.shape

    _, image = cv2.threshold(image, 127, 255, cv2.THRESH_BINARY)
    image = 255 - image
    padded_width = ((width + 7) // 8) * 8
    if padded_width != width:
        image = cv2.copyMakeBorder(image, 0, 0, 0, padded_width - width, cv2.BORDER_CONSTANT, value=0)
        width = padded_width

    bytes_per_line = width // 8
    xL = bytes_per_line & 0xFF
    xH = (bytes_per_line >> 8) & 0xFF
    yL = height & 0xFF
    yH = (height >> 8) & 0xFF
    raster_cmd = bytearray(b'\x1d\x76\x30\x00' + bytes([xL, xH, yL, yH]))

    for row in image:
        for x in range(0, width, 8):
            byte = 0
            for bit in range(8):
                if row[x + bit] > 0:
                    byte |= 1 << (7 - bit)
            raster_cmd.append(byte)

    return bytes(raster_cmd)


def center_receipt_line(text, width_chars):
    if len(text) >= width_chars:
        return text[:width_chars]
    padding = (width_chars - len(text)) // 2
    return ' ' * padding + text


def wrap_text(text, width_chars):
    words = text.split()
    if not words:
        return ['']

    lines = []
    current = ''
    for word in words:
        if current:
            candidate = current + ' ' + word
        else:
            candidate = word

        if len(candidate) <= width_chars:
            current = candidate
        else:
            if current:
                lines.append(current)
            while len(word) > width_chars:
                lines.append(word[:width_chars])
                word = word[width_chars:]
            current = word

    if current:
        lines.append(current)
    return lines


def format_rupiah(amount):
    return f'{int(amount):,}'.replace(',', '.')


def generate_thermal_receipt_bytes(order, width_chars, receipt_type=None):
    body_text = generate_thermal_receipt(order, width_chars, receipt_type)
    return body_text.encode('utf-8')


def generate_thermal_receipt(order, width_chars, receipt_type=None):
    lines = []
    if receipt_type:
        lines.append(center_receipt_line(receipt_type, width_chars))
    lines.append(center_receipt_line('KAPIO', width_chars))
    lines.append(center_receipt_line('Kedainya Kita Semua', width_chars))
    lines.append('')
    lines.append('-' * width_chars)
    lines.append(f'NO. PESANAN: #{order["id"]}')
    lines.append(f'TANGGAL: {order["waktu"]}')
    lines.append(f'PELANGGAN: {order["pelanggan"] or "-"}')
    lines.append('-' * width_chars)
    cart = json.loads(order['cart_json'] or '[]')
    show_prices = receipt_type != 'BARISTA'
    for item in cart:
        name = item.get('nama', '')
        qty = item.get('qty', 0)
        price = item.get('harga', 0)
        original_price = item.get('original_harga', price)
        discount_pct = int(item.get('diskon', 0) or 0)
        subtotal = qty * price
        for line in wrap_text(name, width_chars):
            lines.append(line)
        if show_prices and discount_pct > 0:
            lines.append(f'DISKON {discount_pct}%')
            lines.append(pad_receipt_line('Hrg asli', f'Rp {format_rupiah(original_price)}', width_chars))
        if show_prices:
            lines.append(pad_receipt_line(f'{qty} x {format_rupiah(price)}', f'Rp {format_rupiah(subtotal)}', width_chars))
        else:
            lines.append(f'QTY: {qty}')
    lines.append('-' * width_chars)
    if show_prices:
        lines.append(pad_receipt_line('TOTAL', f'Rp {format_rupiah(order["total"])}', width_chars))
    lines.append('')
    lines.append('')
    lines.append('-' * width_chars)
    lines.append(center_receipt_line('TERIMA KASIH TELAH BERBELANJA!', width_chars))
    lines.append('')
    lines.append('')
    return '\n'.join(lines) + '\n'

def print_to_printer(printer_name, content):
    if isinstance(content, str):
        data = content.encode('utf-8')
    else:
        data = content

    if not printer_name:
        printer_name = win32print.GetDefaultPrinter()
    hPrinter = win32print.OpenPrinter(printer_name)
    try:
        hJob = win32print.StartDocPrinter(hPrinter, 1, ("POS Receipt", None, "RAW"))
        win32print.StartPagePrinter(hPrinter)
        win32print.WritePrinter(hPrinter, data)
        win32print.EndPagePrinter(hPrinter)
        win32print.EndDocPrinter(hPrinter)
    finally:
        win32print.ClosePrinter(hPrinter)

def init_db():
    conn = get_db_connection()
    conn.executescript('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            password TEXT,
            role TEXT,
            fullname TEXT
        );
        CREATE TABLE IF NOT EXISTS menus (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nama TEXT,
            harga INTEGER,
            kategori TEXT,
            gambar TEXT,
            has_opt INTEGER DEFAULT 0,
            topping TEXT,
            harga_topping TEXT,
            use_ppn INTEGER DEFAULT 1,
            show_on_tv INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            meja TEXT,
            pelanggan TEXT,
            menu TEXT,
            total INTEGER,
            status TEXT DEFAULT 'pending',
            waktu TEXT,
            metode TEXT,
            kasir TEXT,
            is_archived INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            keterangan TEXT,
            jumlah INTEGER,
            waktu TEXT,
            source TEXT,
            is_archived INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS raw_materials (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nama TEXT,
            stok REAL,
            satuan TEXT
        );
        CREATE TABLE IF NOT EXISTS input_stok (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            keterangan TEXT,
            jumlah INTEGER,
            qty INTEGER,
            waktu TEXT,
            is_archived INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        );
        CREATE TABLE IF NOT EXISTS menu_recipes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            menu_id INTEGER,
            material_id INTEGER,
            qty_used REAL,
            FOREIGN KEY (menu_id) REFERENCES menus(id),
            FOREIGN KEY (material_id) REFERENCES raw_materials(id)
        );
        CREATE TABLE IF NOT EXISTS membership (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nama TEXT,
            nomor_member TEXT UNIQUE,
            poin INTEGER DEFAULT 0,
            created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS membership_transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            membership_id INTEGER,
            order_id INTEGER,
            poin_earned INTEGER DEFAULT 0,
            poin_redeemed INTEGER DEFAULT 0,
            reward_type TEXT,
            waktu TEXT,
            FOREIGN KEY (membership_id) REFERENCES membership(id),
            FOREIGN KEY (order_id) REFERENCES orders(id)
        );
    ''')
    
    # Migrasi: Tambah kolom pelanggan jika belum ada
    try:
        conn.execute("ALTER TABLE orders ADD COLUMN pelanggan TEXT")
    except sqlite3.OperationalError:
        pass 

    try:
        conn.execute("ALTER TABLE menus ADD COLUMN diskon INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass

    try:
        conn.execute("ALTER TABLE menus ADD COLUMN has_note INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass

    try:
        conn.execute("ALTER TABLE menus ADD COLUMN has_variant INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass

    try:
        conn.execute("ALTER TABLE menus ADD COLUMN variant_nama TEXT")
    except sqlite3.OperationalError:
        pass

    try:
        conn.execute("ALTER TABLE menus ADD COLUMN variant_list TEXT")
    except sqlite3.OperationalError:
        pass

    try:
        conn.execute("ALTER TABLE menus ADD COLUMN variants_json TEXT")
    except sqlite3.OperationalError:
        pass

    try:
        conn.execute("ALTER TABLE orders ADD COLUMN cart_json TEXT")
    except sqlite3.OperationalError:
        pass

    # Migrasi: tambah kolom untuk membership dan student discount
    try:
        conn.execute("ALTER TABLE orders ADD COLUMN is_dine_in INTEGER DEFAULT 1")
    except sqlite3.OperationalError:
        pass

    try:
        conn.execute("ALTER TABLE orders ADD COLUMN membership_id INTEGER")
    except sqlite3.OperationalError:
        pass

    try:
        conn.execute("ALTER TABLE orders ADD COLUMN is_student_discount INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass

    try:
        conn.execute("ALTER TABLE orders ADD COLUMN points_earned INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass

    try:
        conn.execute("ALTER TABLE orders ADD COLUMN points_redeemed INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass

    # Migrasi: tambah kolom fullname pada users jika belum ada
    try:
        conn.execute("ALTER TABLE users ADD COLUMN fullname TEXT")
    except sqlite3.OperationalError:
        pass

    # Migrasi: tambah kolom nomor_telepon pada membership jika belum ada
    try:
        conn.execute("ALTER TABLE membership ADD COLUMN nomor_telepon TEXT UNIQUE")
        conn.commit()
    except sqlite3.OperationalError:
        pass

    # Default Admin
    admin_exists = conn.execute("SELECT * FROM users WHERE username='admin'").fetchone()
    if not admin_exists:
        conn.execute("INSERT INTO users (username, password, role, fullname) VALUES (?, ?, ?, ?)",
                     ('admin', generate_password_hash('admin123'), 'admin', 'Administrator'))
    
    # Default Settings
    if not conn.execute("SELECT * FROM settings WHERE key='modal_kembalian'").fetchone():
        conn.execute("INSERT INTO settings (key, value) VALUES (?, ?)", ('modal_kembalian', '500000'))
    if not conn.execute("SELECT * FROM settings WHERE key='thermal_printer_width'").fetchone():
        conn.execute("INSERT INTO settings (key, value) VALUES (?, ?)", ('thermal_printer_width', '58'))
    if not conn.execute("SELECT * FROM settings WHERE key='thermal_printer_name'").fetchone():
        conn.execute("INSERT INTO settings (key, value) VALUES (?, ?)", ('thermal_printer_name', ''))
    
    conn.commit()
    conn.close()

init_db()

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# --- ROUTES ---

@app.route('/')
@login_required
def index():
    conn = get_db_connection()
    menus = conn.execute("SELECT * FROM menus ORDER BY kategori, nama").fetchall()
    conn.close()
    return render_template('index.html', menus=menus)

@app.route('/admin')
@login_required
def admin():
    conn = get_db_connection()
    orders = conn.execute("SELECT * FROM orders WHERE is_archived=0 ORDER BY id DESC").fetchall()
    menus = conn.execute("SELECT * FROM menus ORDER BY kategori, nama").fetchall()
    materials = conn.execute("SELECT * FROM raw_materials").fetchall()
    
    # Ambil semua resep dan grupkan berdasarkan menu
    raw_recipes = conn.execute("""
        SELECT r.*, m.nama as menu_nama, mat.nama as material_nama, mat.satuan
        FROM menu_recipes r
        JOIN menus m ON r.menu_id = m.id
        JOIN raw_materials mat ON r.material_id = mat.id
    """).fetchall()
    
    recipes_grouped = {}
    for r in raw_recipes:
        m_id = r['menu_id']
        if m_id not in recipes_grouped:
            recipes_grouped[m_id] = {
                'menu_nama': r['menu_nama'],
                'ingredients': []
            }
        recipes_grouped[m_id]['ingredients'].append(r)
        
    conn.close()
    printer_list = list_printers()
    selected_printer = get_setting('thermal_printer_name', '')
    selected_width = get_setting('thermal_printer_width', '58')
    return render_template('admin.html', orders=orders, menus=menus, materials=materials,
                           recipes=recipes_grouped, printer_list=printer_list,
                           selected_printer=selected_printer, selected_width=selected_width)

@app.route('/order', methods=['POST'])
@login_required
def order():
    antrian = request.form.get('antrian')
    pelanggan = request.form.get('pelanggan')
    cart_data = json.loads(request.form.get('cart_data'))
    is_dine_in = 1 if request.form.get('is_dine_in') == 'true' or request.form.get('is_dine_in') == '1' else 0
    is_student_discount = 1 if request.form.get('is_student_discount') == 'true' or request.form.get('is_student_discount') == '1' else 0
    member_number_raw = request.form.get('member_number', '').strip()
    
    conn = get_db_connection()
    
    # Auto-increment antrian jika tidak ada atau untuk memastikan unik hari ini
    if not antrian or antrian == "" or antrian == "0":
        last_antrian = conn.execute("SELECT MAX(CAST(meja AS INTEGER)) FROM orders WHERE is_archived=0").fetchone()[0] or 0
        antrian = str(int(last_antrian) + 1)

    waktu = datetime.now().strftime("%d-%m-%Y %H:%M:%S")
    menu_str_list = []
    total_semua = 0
    
    for item in cart_data:
        subtotal = item['qty'] * item['harga']
        total_semua += subtotal
        menu_str_list.append(f"{item['nama']}\n{item['qty']}  {item['harga']}  {subtotal}")
    
    # Apply student discount if applicable (10% diskon, hanya untuk dine in)
    if is_student_discount and is_dine_in:
        total_semua = int(total_semua * 0.9)

    member_id = None
    points_earned = 0
    if member_number_raw:
        member_number_clean = ''.join(filter(str.isdigit, member_number_raw))
        if member_number_clean:
            member = conn.execute("SELECT id FROM membership WHERE nomor_telepon=? OR nomor_member=?", (member_number_clean, member_number_clean)).fetchone()
            if member:
                member_id = member['id']
                if total_semua >= 65000:
                    points_earned = 1
                    conn.execute("UPDATE membership SET poin = poin + ? WHERE id=?", (points_earned, member_id))
    
    menu_final = " | ".join(menu_str_list)
    cart_json = json.dumps(cart_data)
    
    conn.execute("INSERT INTO orders (meja, pelanggan, menu, total, waktu, status, cart_json, is_dine_in, is_student_discount, membership_id, points_earned) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                 (antrian, pelanggan, menu_final, total_semua, waktu, 'belum_bayar', cart_json, is_dine_in, is_student_discount, member_id, points_earned))
    conn.commit()
    conn.close()
    return redirect(url_for('index'))

@app.route('/pay/<int:order_id>', methods=['POST'])
@login_required
def pay(order_id):
    kasir = request.form.get('kasir', 'Admin')
    bayar = int(request.form.get('bayar', 0))
    metode = request.form.get('metode', 'cash')
    total_akhir = int(request.form.get('total_akhir', 0))
    
    conn = get_db_connection()
    conn.execute("UPDATE orders SET status='pending', metode=?, kasir=?, total=? WHERE id=?",
                 (metode, kasir, total_akhir, order_id))
    conn.commit()
    order = conn.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
    conn.close()

    if order:
        try:
            printer_name = get_setting('thermal_printer_name', '')
            printer_width = get_setting('thermal_printer_width', '58')
            width_chars = get_width_chars(printer_width)
            receipt_data = generate_thermal_receipt_bytes(order, width_chars)
            print_to_printer(printer_name, receipt_data)
        except Exception:
            pass

    return redirect(url_for('admin'))

@app.route('/finish/<int:order_id>', methods=['POST'])
@login_required
def finish(order_id):
    conn = get_db_connection()
    order = conn.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
    
    if order and order['cart_json']:
        cart = json.loads(order['cart_json'])
        for item in cart:
            # item['id'] is menu_id
            recipes = conn.execute("SELECT * FROM menu_recipes WHERE menu_id=?", (item['id'],)).fetchall()
            for r in recipes:
                deduct_qty = float(item['qty']) * float(r['qty_used'])
                conn.execute("UPDATE raw_materials SET stok = stok - ? WHERE id = ?", (deduct_qty, r['material_id']))
    
    conn.execute("UPDATE orders SET status='selesai' WHERE id=?", (order_id,))
    conn.commit()
    conn.close()
    return redirect(url_for('admin'))

@app.route('/print_barista/<int:order_id>')
@login_required
def print_barista(order_id):
    conn = get_db_connection()
    order = conn.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
    conn.close()

    if order:
        try:
            printer_name = get_setting('thermal_printer_name', '')
            printer_width = get_setting('thermal_printer_width', '58')
            width_chars = get_width_chars(printer_width)
            receipt_data = generate_thermal_receipt_bytes(order, width_chars, receipt_type='BARISTA')
            print_to_printer(printer_name, receipt_data)
        except Exception:
            pass

    return redirect(url_for('admin'))

@app.route('/save_printer_settings', methods=['POST'])
@login_required
def save_printer_settings():
    printer_name = request.form.get('thermal_printer_name', '')
    printer_width = request.form.get('thermal_printer_width', '58')
    save_setting('thermal_printer_name', printer_name)
    save_setting('thermal_printer_width', printer_width)
    return redirect(url_for('admin'))

@app.route('/reprint_thermal/<int:order_id>')
@login_required
def reprint_thermal(order_id):
    conn = get_db_connection()
    order = conn.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
    conn.close()
    if not order:
        return redirect(url_for('admin'))

    printer_name = get_setting('thermal_printer_name', '')
    printer_width = get_setting('thermal_printer_width', '58')
    width_chars = get_width_chars(printer_width)
    receipt_data = generate_thermal_receipt_bytes(order, width_chars)
    try:
        print_to_printer(printer_name, receipt_data)
    except Exception:
        pass
    return redirect(url_for('admin'))

@app.route('/add_recipe', methods=['POST'])
@login_required
def add_recipe():
    menu_id = request.form.get('menu_id')
    recipe_json = request.form.get('recipe_json')
    
    conn = get_db_connection()
    # Hapus resep lama untuk menu ini agar tidak duplikat saat update
    conn.execute("DELETE FROM menu_recipes WHERE menu_id=?", (menu_id,))
    
    if recipe_json:
        ingredients = json.loads(recipe_json)
        for ing in ingredients:
            conn.execute("INSERT INTO menu_recipes (menu_id, material_id, qty_used) VALUES (?, ?, ?)",
                         (menu_id, ing['matId'], ing['qty']))
    
    conn.commit()
    conn.close()
    return redirect(url_for('admin'))

@app.route('/del_recipe/<int:rid>', methods=['POST'])
@login_required
def del_recipe(rid):
    conn = get_db_connection()
    conn.execute("DELETE FROM menu_recipes WHERE id=?", (rid,))
    conn.commit()
    conn.close()
    return redirect(url_for('admin'))

@app.route('/reports')
@login_required
def reports():
    conn = get_db_connection()
    revenue = conn.execute("SELECT SUM(total) FROM orders WHERE status='selesai' AND is_archived=0").fetchone()[0] or 0
    expenses = conn.execute("SELECT SUM(jumlah) FROM expenses WHERE is_archived=0").fetchone()[0] or 0
    stocks = conn.execute("SELECT SUM(jumlah * qty) FROM input_stok WHERE is_archived=0").fetchone()[0] or 0
    total_exp = expenses + stocks
    profit = revenue - total_exp
    
    orders_count = conn.execute("SELECT COUNT(id) FROM orders WHERE status='selesai' AND is_archived=0").fetchone()[0] or 0
    
    # Chart Data
    sales_raw = conn.execute("SELECT total, waktu FROM orders WHERE status='selesai'").fetchall()
    daily_sales = {}
    for s in sales_raw:
        try:
            d = s['waktu'].split(' ')[0]
            daily_sales[d] = daily_sales.get(d, 0) + s['total']
        except: pass
    
    today = datetime.now()
    chart_labels = [(today - timedelta(days=i)).strftime("%d-%m-%Y") for i in range(29, -1, -1)]
    chart_data = [daily_sales.get(l, 0) for l in chart_labels]
    
    # Archives
    files = [f for f in os.listdir('.') if f.endswith('.xlsx') and f.startswith('Laporan_')]
    archive_data = [{'nama_file': f, 'summary': {'total_pemasukan': 0}} for f in sorted(files, reverse=True)]
    
    conn.close()
    return render_template('reports.html', total_revenue=revenue, expenses=total_exp, profit=profit,
                           total_orders=orders_count, chart_labels=chart_labels, chart_data=chart_data,
                           archive_data=archive_data)

@app.route('/inventory')
@login_required
def inventory():
    conn = get_db_connection()
    materials = conn.execute("SELECT * FROM raw_materials").fetchall()
    conn.close()
    return render_template('inventory.html', materials=materials)

@app.route('/add_material', methods=['POST'])
@login_required
def add_material():
    nama = request.form.get('nama')
    satuan = request.form.get('satuan')
    stok = request.form.get('stok', 0)
    conn = get_db_connection()
    conn.execute("INSERT INTO raw_materials (nama, satuan, stok) VALUES (?, ?, ?)", (nama, satuan, stok))
    conn.commit()
    conn.close()
    return redirect(url_for('inventory'))

@app.route('/update_material', methods=['POST'])
@login_required
def update_material():
    mid = request.form.get('id')
    tambah = float(request.form.get('stok_tambah', 0))
    conn = get_db_connection()
    conn.execute("UPDATE raw_materials SET stok = stok + ? WHERE id = ?", (tambah, mid))
    conn.commit()
    conn.close()
    return redirect(url_for('inventory'))

@app.route('/add_menu', methods=['POST'])
@login_required
def add_menu():
    nama = request.form.get('nama')
    harga = int(request.form.get('harga'))
    kategori = request.form.get('kategori')
    
    gambar = ""
    if 'gambar' in request.files:
        file = request.files['gambar']
        if file and file.filename != '':
            filename = secure_filename(file.filename)
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            gambar = filename

    has_opt = 1 if request.form.get('has_opt') else 0
    has_note = 1 if request.form.get('has_note') else 0
    has_variant = 1 if request.form.get('has_variant') else 0
    variants_json = request.form.get('variants_json', '[]')
    diskon = int(request.form.get('diskon', 0))
    conn = get_db_connection()
    conn.execute("INSERT INTO menus (nama, harga, kategori, gambar, has_opt, diskon, has_note, has_variant, variants_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                 (nama, harga, kategori, gambar, has_opt, diskon, has_note, has_variant, variants_json))
    conn.commit()
    conn.close()
    return redirect(url_for('admin'))

@app.route('/update_menu', methods=['POST'])
@login_required
def update_menu():
    mid = request.form.get('id')
    nama = request.form.get('nama')
    harga = int(request.form.get('harga'))
    kategori = request.form.get('kategori')
    
    has_opt = 1 if request.form.get('has_opt') else 0
    has_note = 1 if request.form.get('has_note') else 0
    has_variant = 1 if request.form.get('has_variant') else 0
    variants_json = request.form.get('variants_json', '[]')
    diskon = int(request.form.get('diskon', 0))
    conn = get_db_connection()
    if 'gambar' in request.files and request.files['gambar'].filename != '':
        file = request.files['gambar']
        filename = secure_filename(file.filename)
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        conn.execute("UPDATE menus SET nama=?, harga=?, kategori=?, gambar=?, has_opt=?, diskon=?, has_note=?, has_variant=?, variants_json=? WHERE id=?",
                     (nama, harga, kategori, filename, has_opt, diskon, has_note, has_variant, variants_json, mid))
    else:
        conn.execute("UPDATE menus SET nama=?, harga=?, kategori=?, has_opt=?, diskon=?, has_note=?, has_variant=?, variants_json=? WHERE id=?",
                     (nama, harga, kategori, has_opt, diskon, has_note, has_variant, variants_json, mid))
    conn.commit()
    conn.close()
    return redirect(url_for('admin'))

@app.route('/del_menu/<int:mid>', methods=['POST'])
@login_required
def del_menu(mid):
    conn = get_db_connection()
    conn.execute("DELETE FROM menus WHERE id=?", (mid,))
    conn.commit()
    conn.close()
    return redirect(url_for('admin'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = request.form.get('username')
        pw = request.form.get('password')
        conn = get_db_connection()
        row = conn.execute("SELECT * FROM users WHERE username=?", (user,)).fetchone()
        conn.close()
        if row and check_password_hash(row['password'], pw):
            session['user'] = user
            session['role'] = row['role'] if 'role' in row.keys() else 'crew'
            session['fullname'] = row['fullname'] if 'fullname' in row.keys() else ''
            if session.get('role') == 'admin':
                return redirect(url_for('admin'))
            return redirect(url_for('index'))
        return "Login Gagal", 401
    return render_template('login.html')


@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        fullname = request.form.get('fullname')
        username = request.form.get('username')
        password = request.form.get('password')
        if not fullname or not username or not password:
            return "Semua field harus diisi", 400
        conn = get_db_connection()
        exists = conn.execute("SELECT 1 FROM users WHERE username=?", (username,)).fetchone()
        if exists:
            conn.close()
            return "Username sudah digunakan", 400
        conn.execute("INSERT INTO users (username, password, role, fullname) VALUES (?, ?, ?, ?)",
                     (username, generate_password_hash(password), 'crew', fullname))
        conn.commit()
        conn.close()
        return redirect(url_for('login'))
    return render_template('signup.html')

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('login'))

@app.route('/membership')
@login_required
def membership():
    conn = get_db_connection()
    members = conn.execute("SELECT * FROM membership ORDER BY created_at DESC").fetchall()
    conn.close()
    return render_template('membership.html', members=members)

@app.route('/register_membership', methods=['POST'])
@login_required
def register_membership():
    nama = request.form.get('nama')
    nomor_telepon = request.form.get('nomor_telepon')
    
    if not nama or not nomor_telepon:
        return "Nama dan nomor telepon harus diisi", 400
    
    # Normalisasi nomor telepon (hapus spasi, karakter khusus)
    nomor_telepon_clean = ''.join(filter(str.isdigit, nomor_telepon))
    
    if len(nomor_telepon_clean) < 10:
        return "Nomor telepon tidak valid (minimal 10 digit)", 400
    
    conn = get_db_connection()
    
    # Pastikan kolom nomor_telepon ada
    try:
        cursor = conn.execute("PRAGMA table_info(membership)")
        columns = [row[1] for row in cursor.fetchall()]
        if 'nomor_telepon' not in columns:
            conn.execute("ALTER TABLE membership ADD COLUMN nomor_telepon TEXT UNIQUE")
            conn.commit()
    except:
        pass
    
    # Cek apakah nomor telepon sudah terdaftar (coba pakai nomor_telepon, fallback ke nomor_member)
    try:
        exists = conn.execute("SELECT 1 FROM membership WHERE nomor_telepon=?", (nomor_telepon_clean,)).fetchone()
    except:
        # Jika kolom tidak ada, cek nomor_member saja
        exists = conn.execute("SELECT 1 FROM membership WHERE nomor_member=?", (nomor_telepon_clean,)).fetchone()
    
    if exists:
        conn.close()
        return "Nomor telepon sudah terdaftar", 400
    
    created_at = datetime.now().strftime("%d-%m-%Y %H:%M:%S")
    # Gunakan nomor telepon sebagai nomor_member untuk kemudahan customer mengingat
    try:
        conn.execute("INSERT INTO membership (nama, nomor_member, nomor_telepon, poin, created_at) VALUES (?, ?, ?, ?, ?)",
                     (nama, nomor_telepon_clean, nomor_telepon_clean, 0, created_at))
    except:
        # Fallback jika kolom nomor_telepon tidak ada
        conn.execute("INSERT INTO membership (nama, nomor_member, poin, created_at) VALUES (?, ?, ?, ?)",
                     (nama, nomor_telepon_clean, 0, created_at))
    
    conn.commit()
    conn.close()
    return redirect(url_for('membership'))

@app.route('/membership_lookup/<member_number>')
def membership_lookup(member_number):
    member_number_clean = ''.join(filter(str.isdigit, member_number or ''))
    if not member_number_clean:
        return jsonify({'found': False}), 404

    conn = get_db_connection()
    try:
        cursor = conn.execute("PRAGMA table_info(membership)")
        columns = [row[1] for row in cursor.fetchall()]
        if 'nomor_telepon' not in columns:
            conn.execute("ALTER TABLE membership ADD COLUMN nomor_telepon TEXT")
            conn.commit()
    except Exception:
        pass

    member = None
    try:
        member = conn.execute(
            "SELECT id, nama, nomor_member, nomor_telepon FROM membership WHERE nomor_telepon=? OR nomor_member=?",
            (member_number_clean, member_number_clean)
        ).fetchone()
    except sqlite3.OperationalError:
        member = conn.execute(
            "SELECT id, nama, nomor_member FROM membership WHERE nomor_member=?",
            (member_number_clean,)
        ).fetchone()
    conn.close()

    if not member:
        return jsonify({'found': False}), 404

    return jsonify({
        'found': True,
        'id': member['id'],
        'nama': member['nama'],
        'nomor_member': member['nomor_member']
    })

@app.route('/print_membership_card/<int:member_id>')
@login_required
def print_membership_card(member_id):
    """Display membership card for printing"""
    conn = get_db_connection()
    member = conn.execute("SELECT * FROM membership WHERE id=?", (member_id,)).fetchone()
    conn.close()
    
    if not member:
        return "Member tidak ditemukan", 404
    
    # Return HTML page for printing instead of PDF
    html_content = f"""
    <!DOCTYPE html>
    <html lang="id">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Kartu Membership - {member['nama']}</title>
        <style>
            * {{
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }}
            
            body {{
                display: flex;
                justify-content: center;
                align-items: center;
                min-height: 100vh;
                background: #f0f0f0;
                font-family: Arial, sans-serif;
                padding: 20px;
            }}
            
            .card {{
                width: 85.6mm;
                height: 53.98mm;
                background: linear-gradient(135deg, #FFB600 0%, #FFA500 100%);
                border-radius: 10px;
                padding: 8mm;
                box-shadow: 0 10px 30px rgba(0,0,0,0.3);
                color: #000;
                position: relative;
                overflow: hidden;
                display: flex;
                flex-direction: column;
                justify-content: space-between;
            }}
            
            .card::before {{
                content: '';
                position: absolute;
                top: -50%;
                right: -50%;
                width: 200%;
                height: 200%;
                background: radial-gradient(circle, rgba(255,255,255,0.15) 0%, transparent 70%);
                animation: shine 3s infinite;
            }}
            
            @keyframes shine {{
                0% {{ transform: translate(0, 0); }}
                100% {{ transform: translate(20px, 20px); }}
            }}
            
            .card-content {{
                position: relative;
                z-index: 2;
                display: flex;
                flex-direction: column;
                height: 100%;
                justify-content: space-between;
            }}
            
            .card-header {{
                display: flex;
                justify-content: space-between;
                align-items: flex-start;
                border-bottom: 1px solid rgba(0,0,0,0.2);
                padding-bottom: 3mm;
                margin-bottom: 3mm;
            }}
            
            .brand {{
                font-weight: bold;
                font-size: 10pt;
                line-height: 1.2;
            }}
            
            .brand-title {{
                font-size: 12pt;
                font-weight: bold;
                margin-top: 1mm;
            }}
            
            .logo {{
                font-size: 14pt;
            }}
            
            .member-name {{
                font-size: 14pt;
                font-weight: bold;
                margin-bottom: 2mm;
                text-transform: uppercase;
            }}
            
            .member-number {{
                font-size: 18pt;
                font-weight: bold;
                letter-spacing: 1px;
                font-family: 'Courier New', monospace;
                background: rgba(0,0,0,0.1);
                padding: 2mm 3mm;
                border-radius: 3mm;
                margin-bottom: 3mm;
                display: inline-block;
            }}
            
            .footer {{
                display: flex;
                justify-content: space-between;
                align-items: flex-end;
                border-top: 1px solid rgba(0,0,0,0.2);
                padding-top: 2mm;
            }}
            
            .points {{
                font-size: 16pt;
                font-weight: bold;
            }}
            
            .points-label {{
                font-size: 8pt;
            }}
            
            .valid-date {{
                font-size: 8pt;
                text-align: right;
            }}
            
            .valid-date-label {{
                font-size: 7pt;
            }}
            
            @media print {{
                body {{
                    background: white;
                    padding: 0;
                    display: block;
                }}
                
                .card {{
                    box-shadow: none;
                    margin: 0;
                    page-break-after: always;
                }}
                
                .print-button {{
                    display: none;
                }}
            }}
            
            .print-button {{
                position: fixed;
                bottom: 20px;
                right: 20px;
                padding: 12px 24px;
                background: #FFB600;
                color: #000;
                border: none;
                border-radius: 8px;
                font-weight: bold;
                cursor: pointer;
                z-index: 1000;
            }}
            
            .print-button:hover {{
                opacity: 0.9;
                background: #FFA500;
            }}
        </style>
    </head>
    <body>
        <div class="card">
            <div class="card-content">
                <div class="card-header">
                    <div>
                        <div class="brand">KAPIO</div>
                        <div class="brand-title">MEMBERSHIP</div>
                    </div>
                    <div class="logo">💳</div>
                </div>
                
                <div>
                    <div class="member-name">{member['nama'][:20]}</div>
                    <div class="member-number">{member['nomor_member']}</div>
                </div>
                
                <div class="footer">
                    <div>
                        <div class="points-label">POIN</div>
                        <div class="points">{member['poin']}</div>
                    </div>
                    <div class="valid-date">
                        <div class="valid-date-label">Since</div>
                        {member['created_at'][:10]}
                    </div>
                </div>
            </div>
        </div>
        
        <button class="print-button" onclick="window.print();">🖨️ Cetak</button>
    </body>
    </html>
    """
    
    return html_content, 200, {'Content-Type': 'text/html; charset=utf-8'}

@app.route('/add_points_to_member/<int:member_id>/<int:points>', methods=['POST'])
@login_required
def add_points_to_member(member_id, points):
    conn = get_db_connection()
    conn.execute("UPDATE membership SET poin = poin + ? WHERE id = ?", (points, member_id))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/redeem_points/<int:member_id>/<int:points>/<reward_type>', methods=['POST'])
@login_required
def redeem_points(member_id, points, reward_type):
    conn = get_db_connection()
    member = conn.execute("SELECT poin FROM membership WHERE id=?", (member_id,)).fetchone()
    if not member or member['poin'] < points:
        conn.close()
        return "Poin tidak cukup", 400
    
    conn.execute("UPDATE membership SET poin = poin - ? WHERE id = ?", (points, member_id))
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'message': f'Reward {reward_type} berhasil ditukarkan'})

@app.route('/add_membership_to_order/<int:order_id>/<int:member_id>', methods=['POST'])
@login_required
def add_membership_to_order(order_id, member_id):
    conn = get_db_connection()
    order = conn.execute("SELECT total FROM orders WHERE id=?", (order_id,)).fetchone()
    if not order:
        conn.close()
        return "Order tidak ditemukan", 400
    
    # Calculate points: minimum Rp65.000 = 1 point, tidak berlaku kelipatan
    if order['total'] >= 65000:
        points = 1
        conn.execute("UPDATE orders SET membership_id=?, points_earned=? WHERE id=?", (member_id, points, order_id))
        conn.execute("UPDATE membership SET poin = poin + ? WHERE id=?", (points, member_id))
    
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/delete_member/<int:member_id>', methods=['POST'])
@login_required
def delete_member(member_id):
    """Delete a member from the membership database"""
    conn = get_db_connection()
    conn.execute("DELETE FROM membership WHERE id=?", (member_id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/archive', methods=['POST'])
@login_required
def archive():
    conn = get_db_connection()
    # 1. Ambil data yang akan diarsip
    orders = conn.execute("SELECT * FROM orders WHERE is_archived=0").fetchall()
    expenses = conn.execute("SELECT * FROM expenses WHERE is_archived=0").fetchall()
    stocks = conn.execute("SELECT * FROM input_stok WHERE is_archived=0").fetchall()
    
    if not orders and not expenses and not stocks:
        conn.close()
        return redirect(url_for('admin'))
        
    # 2. Buat Excel (Sederhana)
    filename = f"Laporan_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    with pd.ExcelWriter(filename) as writer:
        if orders:
            df_orders = pd.DataFrame(orders, columns=orders[0].keys())
            # Pilih dan urutkan kolom yang relevan untuk laporan
            cols = ['waktu', 'meja', 'pelanggan', 'kasir', 'metode', 'menu', 'total']
            df_orders[cols].rename(columns={'meja': 'Antrian', 'pelanggan': 'Nama Pelanggan'}).to_excel(writer, sheet_name='Pemasukan', index=False)
        if expenses: pd.DataFrame(expenses, columns=expenses[0].keys()).to_excel(writer, sheet_name='Pengeluaran', index=False)
        if stocks: pd.DataFrame(stocks, columns=stocks[0].keys()).to_excel(writer, sheet_name='Stok', index=False)
    
    # 3. Tandai sebagai terarsip
    conn.execute("UPDATE orders SET is_archived=1")
    conn.execute("UPDATE expenses SET is_archived=1")
    conn.execute("UPDATE input_stok SET is_archived=1")
    conn.commit()
    conn.close()
    return redirect(url_for('admin'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)