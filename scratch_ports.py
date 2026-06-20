import serial.tools.list_ports

ports = serial.tools.list_ports.comports()
for p in ports:
    print(f"Device: {p.device}")
    print(f"Name: {p.name}")
    print(f"Description: {p.description}")
    print(f"HWID: {p.hwid}")
    print("-" * 20)
