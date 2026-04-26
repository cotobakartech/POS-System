@echo off
title CAFE BOS - KASIR + CLOUDFLARE + NGROK
cd /d "C:\Users\BOS\Desktop\OrderCoffeeBOS"

echo ==================================================
echo 🚀 MEMULAI SISTEM KASIR CAFE BOS 🚀
echo (Server + Cloudflare + Ngrok)
echo ==================================================
echo.

:: 1. Jalankan Server
echo [1/3] Memulai Server di Port 80...
start "SERVER KASIR" cmd /c "python server.py"

:: Tunggu sebentar agar server benar-benar siap
timeout /t 5 /nobreak > nul

:: 2. Jalankan Cloudflare Tunnel
echo [2/3] Memulai Cloudflare Tunnel...
start "CLOUDFLARE TUNNEL" cmd /c "cloudflared.exe tunnel run"

:: 3. Jalankan Ngrok
echo [3/3] Memulai Ngrok di Port 80...
start "NGROK TUNNEL" cmd /c "ngrok http 80"

echo.
echo --------------------------------------------------
echo SEMUA SISTEM TELAH DIJALANKAN!
echo --------------------------------------------------
echo.
pause