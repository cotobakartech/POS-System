"""
PDF Generator Module for Cafe BOS Reports - BULLETPROOF & MINIMALIST VERSION.
Focuses on absolute alignment stability and page efficiency.
"""
from fpdf import FPDF
from datetime import datetime
import pandas as pd
import os


class CafeBOSPDF(FPDF):
    def __init__(self, report_date="", *args, **kwargs):
        super().__init__(orientation='L', unit='mm', format='A4', *args, **kwargs)
        self.report_date = report_date
        self.set_auto_page_break(auto=True, margin=12)

    def header(self):
        # Header hanya muncul di halaman 1 secara lengkap
        if self.page_no() == 1:
            self.set_fill_color(212, 175, 55)
            self.rect(0, 0, self.w, 3, 'F')
            self.set_fill_color(15, 23, 42)
            self.rect(0, 3, self.w, 12, 'F')
            self.set_xy(10, 4)
            self.set_font("helvetica", "B", 11)
            self.set_text_color(212, 175, 55)
            self.cell(40, 10, "CAFE BOS", align='L')
            self.set_font("helvetica", "", 8)
            self.set_text_color(255, 255, 255)
            self.cell(0, 10, f"|  BUSINESS REPORT  |  TANGGAL: {self.report_date}", align='L')
            self.set_y(18)
        else:
            self.set_y(10)

    def footer(self):
        self.set_y(-10)
        self.set_font("helvetica", "I", 7)
        self.set_text_color(148, 163, 184)
        self.cell(0, 5, f"Hal {self.page_no()}/{{nb}}", align='R')

    def summary_box(self, x, y, w, h, label, value, clr):
        self.set_fill_color(250, 250, 250)
        self.set_draw_color(230, 230, 230)
        self.rect(x, y, w, h, 'DF')
        self.set_fill_color(*clr)
        self.rect(x, y, 1, h, 'F')
        
        # Label
        self.set_xy(x + 2, y + 1)
        self.set_font("helvetica", "B", 6)
        self.set_text_color(100, 116, 139)
        self.cell(w-3, 4, label)
        
        # Value
        self.set_xy(x + 2, y + 5)
        self.set_font("helvetica", "B", 9)
        self.set_text_color(*clr)
        self.cell(w-3, 5, value)

    def section_title(self, title, color=(15, 23, 42)):
        self.set_font("helvetica", "B", 10)
        self.set_text_color(*color)
        self.cell(0, 8, title.upper(), ln=True)
        # Underline accent - using gold color if text is default dark
        u_color = (212, 175, 55) if color == (15, 23, 42) else color
        self.set_fill_color(*u_color)
        self.rect(self.l_margin, self.get_y(), 20, 0.6, 'F')
        self.ln(3)

def fmt_idr(n):
    return "Rp {:,.0f}".format(n).replace(",", ".")

def generate_report_pdf(filename, xls, bukti_cash_path=None, bukti_nota_path=None):
    try:
        dt = filename.split('_')[2]
        r_date = f"{dt[6:8]}/{dt[4:6]}/{dt[:4]}"
    except:
        r_date = datetime.now().strftime('%d/%m/%Y')

    pdf = CafeBOSPDF(report_date=r_date)
    pdf.alias_nb_pages()
    pdf.add_page()

    # --- DATA CALCULATION ---
    f_p = 0; f_c = 0; f_q = 0; f_e = 0; sheets = {}
    for sn in xls.sheet_names:
        df = pd.read_excel(xls, sheet_name=sn).fillna('')
        sheets[sn] = df
        df_c = df[~df[df.columns[0]].astype(str).str.contains('TOTAL', case=False, na=False)]
        if sn == "Pemasukan":
            if 'Total Bayar' in df_c.columns:
                n = pd.to_numeric(df_c['Total Bayar'].astype(str).str.replace('.', '', regex=False), errors='coerce').fillna(0)
                f_p = n.sum()
                if 'Metode' in df_c.columns:
                    f_c = n[df_c['Metode'].str.contains('CASH', na=False, case=False)].sum()
                    f_q = n[df_c['Metode'].str.contains('QRIS', na=False, case=False)].sum()
        elif sn == "Pengeluaran":
            c = 'Jumlah' if 'Jumlah' in df_c.columns else 'Total'
            if c in df_c.columns:
                f_e = pd.to_numeric(df_c[c].astype(str).str.replace('.', '', regex=False), errors='coerce').fillna(0).sum()

    # ============================================================
    # COMPACT SUMMARY (One Row) - Aligned with Table Width
    # ============================================================
    pw = pdf.w - 2 * pdf.l_margin # Total lebar tabel: 273mm
    g = 2.0 # Gap antar kotak
    cw = (pw - (5 * g)) / 6 # Hitung lebar kotak agar pas dengan lebar tabel
    ch = 11
    sx = pdf.l_margin
    sums = [
        ("PEMASUKAN", fmt_idr(f_p), (37, 99, 235)),
        ("CASH", fmt_idr(f_c), (30, 41, 59)),
        ("QRIS", fmt_idr(f_q), (139, 92, 246)),
        ("PENGELUARAN", fmt_idr(f_e), (239, 68, 68)),
        ("NET PROFIT", fmt_idr(f_p - f_e), (16, 185, 129)),
        ("CASH TERIMA", fmt_idr(f_c - f_e), (212, 175, 55)),
    ]
    y_start_summary = pdf.get_y()
    for i, (l, v, c) in enumerate(sums):
        pdf.summary_box(sx + i*(cw+g), y_start_summary, cw, ch, l, v, c)
    pdf.set_y(y_start_summary + ch + 6)

    # ============================================================
    # DATA TABLES (Stable Grid)
    # ============================================================
    for sn, df in sheets.items():
        if df.empty: continue
        
        pdf.section_title(f"DATA {sn}")

        pw = pdf.w - 2 * pdf.l_margin # Total lebar tersedia: 273mm
        if sn == "Pemasukan":
            # Waktu(26), Antrian(12), Pelanggan(40), Kasir(25), Metode(20), Menu(100), Total(50)
            widths = [26, 12, 40, 25, 20, 100, 50] # Total = 273mm
        elif sn == "Pengeluaran":
            widths = [pw*0.6, pw*0.2, pw*0.2] # Total = 273mm
        else:
            widths = [pw/len(df.columns)] * len(df.columns)

        def draw_header():
            pdf.set_font("helvetica", "B", 8)
            pdf.set_fill_color(15, 23, 42)
            pdf.set_text_color(255, 255, 255)
            pdf.set_draw_color(15, 23, 42)
            for i, col in enumerate(df.columns):
                pdf.cell(widths[i], 8, str(col).upper(), border=1, align='C', fill=True)
            pdf.ln()

        draw_header()

        # Rows
        for row_idx, (_, row) in enumerate(df.iterrows()):
            is_total = 'TOTAL' in str(row.iloc[0]).upper()
            
            # Row height estimation
            line_counts = []
            for i, item in enumerate(row):
                lines = pdf.multi_cell(widths[i], 5, str(item), split_only=True)
                line_counts.append(len(lines))
            h = max(line_counts) * 5
            if h < 7: h = 7

            if pdf.get_y() + h > pdf.page_break_trigger:
                pdf.add_page()
                draw_header()

            # Style
            if is_total:
                pdf.set_font("helvetica", "B", 7.5)
                pdf.set_fill_color(255, 252, 240)
            else:
                pdf.set_font("helvetica", "", 7)
                pdf.set_fill_color(255, 255, 255) if row_idx%2==0 else pdf.set_fill_color(250, 250, 250)
            
            pdf.set_text_color(51, 65, 85)
            pdf.set_draw_color(220, 220, 220)
            
            x_s, y_s = pdf.get_x(), pdf.get_y()
            
            for i, item in enumerate(row):
                txt = str(item)
                col_n = str(df.columns[i]).upper()
                
                # Format Rupiah HANYA untuk kolom keuangan
                is_money_col = any(x in col_n for x in ['TOTAL', 'JUMLAH', 'SUBTOTAL', 'PPN', 'PEMBULATAN'])
                if is_money_col:
                    try:
                        cv = txt.replace('.','').replace(',','')
                        if cv.isdigit() or (cv.startswith('-') and cv[1:].isdigit()):
                            txt = fmt_idr(float(cv))
                    except: pass
                
                # Alignment
                align = 'C'
                if any(x in col_n for x in ['MENU', 'KETERANGAN']): align = 'L'
                elif is_money_col: align = 'R'

                # Draw Cell
                pdf.set_xy(x_s + sum(widths[:i]), y_s)
                pdf.cell(widths[i], h, "", border=1, fill=True) # Border and Bg
                
                # Vertical Center for Text
                txt_h = len(pdf.multi_cell(widths[i], 5, txt, split_only=True)) * 5
                pdf.set_xy(x_s + sum(widths[:i]), y_s + (h - txt_h)/2)
                
                # Padding
                p = 1.5
                pdf.set_x(pdf.get_x() + (p if align == 'L' else (-p if align == 'R' else 0)))
                pdf.multi_cell(widths[i] - (p*2 if align != 'C' else 0), 5, txt, border=0, align=align)
            
            pdf.set_xy(x_s, y_s + h)
        pdf.ln(4)

    # ============================================================
    # ATTACHMENT SECTION (Bukti Cash)
    # ============================================================
    if bukti_cash_path and os.path.exists(bukti_cash_path):
        pdf.add_page()
        pdf.section_title("Lampiran Bukti Terima Cash", color=(212, 175, 55))
        pdf.ln(5)
        
        # Center the image
        img_w = 120
        x_img = (pdf.w - img_w) / 2
        try:
            pdf.image(bukti_cash_path, x=x_img, y=pdf.get_y(), w=img_w)
            pdf.ln(img_w + 10)
        except Exception as e:
            pdf.set_font("helvetica", "I", 8)
            pdf.set_text_color(239, 68, 68)
            pdf.cell(0, 10, f"Gagal memuat gambar bukti cash: {str(e)}", ln=True)

    # ============================================================
    # ATTACHMENT SECTION (Nota Pengeluaran)
    # ============================================================
    if bukti_nota_path and os.path.exists(bukti_nota_path):
        pdf.add_page()
        pdf.section_title("Lampiran Nota Pengeluaran", color=(239, 68, 68))
        pdf.ln(5)
        
        # Center the image
        img_w = 120
        x_img = (pdf.w - img_w) / 2
        try:
            pdf.image(bukti_nota_path, x=x_img, y=pdf.get_y(), w=img_w)
            pdf.ln(img_w + 10)
        except Exception as e:
            pdf.set_font("helvetica", "I", 8)
            pdf.set_text_color(239, 68, 68)
            pdf.cell(0, 10, f"Gagal memuat gambar nota pengeluaran: {str(e)}", ln=True)

    return pdf
def generate_attendance_pdf(data, date_str):
    """Generates a clean attendance report PDF."""
    pdf = CafeBOSPDF(report_date=date_str)
    pdf.add_page()
    pdf.set_font("helvetica", "B", 14)
    pdf.set_text_color(15, 23, 42)
    pdf.cell(0, 10, "LAPORAN ABSENSI KARYAWAN", align='C', ln=True)
    pdf.ln(5)
    
    # Table Header
    pdf.set_fill_color(241, 245, 249)
    pdf.set_font("helvetica", "B", 10)
    pdf.cell(70, 10, " NAMA KARYAWAN", 1, 0, 'L', True)
    pdf.cell(40, 10, " TANGGAL", 1, 0, 'C', True)
    pdf.cell(40, 10, " JAM MASUK", 1, 0, 'C', True)
    pdf.cell(40, 10, " JAM PULANG", 1, 1, 'C', True)
    
    # Table Data
    pdf.set_font("helvetica", "", 10)
    for row in data:
        pdf.cell(70, 10, f" {row['nama']}", 1, 0, 'L')
        pdf.cell(40, 10, f" {row['tanggal']}", 1, 0, 'C')
        pdf.cell(40, 10, f" {row['jam_masuk']}", 1, 0, 'C')
        pdf.cell(40, 10, f" {row['jam_pulang'] or '-'}", 1, 1, 'C')
    
    filename = f"Laporan_Absensi_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    output_path = os.path.join("static", filename)
    pdf.output(output_path)
    return filename
