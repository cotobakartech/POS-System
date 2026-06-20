import sqlite3
conn = sqlite3.connect('possystem.db')
print("Employees Schema:", conn.execute("SELECT sql FROM sqlite_master WHERE name='employees'").fetchone()[0])
print("Attendance Schema:", conn.execute("SELECT sql FROM sqlite_master WHERE name='attendance'").fetchone()[0])
conn.close()
