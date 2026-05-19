import sqlite3
import os

db_path = r'c:\Users\TafaraChitiyo-I-\Documents\CV Analysis\cv_analyzer\data\cv_analyzer.db'
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
tables = cursor.fetchall()
print(f'Tables: {tables}')

for table in tables:
    t_name = table[0]
    cursor.execute(f'SELECT COUNT(*) FROM {t_name}')
    count = cursor.fetchone()[0]
    print(f'Table {t_name} has {count} rows')

conn.close()
