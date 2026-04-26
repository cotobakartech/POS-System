import sqlite3
conn = sqlite3.connect('database.db')
cursor = conn.cursor()
try:
    cursor.execute('ALTER TABLE employees ADD COLUMN face_descriptor TEXT')
    conn.commit()
    print('Column face_descriptor added successfully.')
except sqlite3.OperationalError:
    print('Column face_descriptor already exists.')
except Exception as e:
    print(f'Error: {e}')
finally:
    conn.close()
