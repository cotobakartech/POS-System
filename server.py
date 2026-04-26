from waitress import serve
from app import app 

if __name__ == "__main__":
    print("--------------------------------------------------")
    print("🔥 SERVER KASIR CAFE BOS AKTIF (MODE OPTIMASI) 🔥")
    print("Akses dari HP lain gunakan: 192.168.1.100")
    print("(Tanpa perlu tambahan :5000 di belakangnya)")
    print("--------------------------------------------------")
    
    # Konfigurasi Waitress untuk performa maksimal di jaringan lokal
    serve(
        app, 
        host='0.0.0.0', 
        port=80, 
        threads=12,              # Menangani hingga 12 proses sekaligus
        connection_limit=200,    # Batas koneksi masuk
        channel_timeout=30,      # Timeout untuk membebaskan koneksi yang menggantung
        url_scheme='http'
    )