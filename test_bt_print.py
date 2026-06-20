import serial
import serial.tools.list_ports
import time
import socket
import re

# List all ports
ports = serial.tools.list_ports.comports()
print("=== Semua Port yang Terdeteksi ===")
for p in ports:
    m = re.search(r'&([0-9A-Fa-f]{12})_', p.hwid or '')
    mac = ':'.join([m.group(1)[i:i+2] for i in range(0, 12, 2)]).upper() if m and m.group(1) != '000000000000' else 'N/A'
    print(f"  {p.device}: MAC={mac} | {p.hwid}")

print("\n=== Test Print via COM Port ===")
test_ports = ['COM5', 'COM3', 'COM4', 'COM8', 'COM9', 'COM6']
for com in test_ports:
    print(f"\nTesting {com}...")
    try:
        ser = serial.Serial(com, 9600, timeout=1, write_timeout=2)
        print(f"  Opened OK")
        result = ser.write(b'\x1B\x40TEST ' + com.encode() + b'\n\n\n')
        ser.flush()
        ser.close()
        print(f"  Wrote {result} bytes - SUCCESS!")
    except Exception as e:
        print(f"  FAILED: {e}")

print("\n=== Test via Bluetooth Socket ===")
# Try socket to MAC addresses found
macs_to_test = []
for p in ports:
    m = re.search(r'&([0-9A-Fa-f]{12})_', p.hwid or '')
    if m and m.group(1) != '000000000000':
        mac = ':'.join([m.group(1)[i:i+2] for i in range(0, 12, 2)]).upper()
        if mac not in macs_to_test:
            macs_to_test.append(mac)

for mac in macs_to_test:
    print(f"\nTesting socket to {mac}...")
    try:
        sock = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_STREAM, socket.BTPROTO_RFCOMM)
        sock.settimeout(4)
        sock.connect((mac, 1))
        sock.sendall(b'\x1B\x40SOCKET TEST ' + mac.encode() + b'\n\n\n')
        sock.close()
        print(f"  SUCCESS via socket!")
    except Exception as e:
        print(f"  FAILED: {e}")
