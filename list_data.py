import sqlite3
import os

db_path = r'c:\Users\TafaraChitiyo-I-\Documents\CV Analysis\cv_analyzer\data\cv_analyzer.db'
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

print('--- Last 5 Applicants ---')
cursor.execute('SELECT id, email, cv_file_path FROM applicants ORDER BY id DESC LIMIT 5')
for row in cursor.fetchall():
    print(dict(row))

print('\n--- Last 5 Uploaded Files ---')
cursor.execute('SELECT id, applicant_id, filename FROM uploaded_files ORDER BY id DESC LIMIT 5')
for row in cursor.fetchall():
    print(dict(row))

conn.close()
