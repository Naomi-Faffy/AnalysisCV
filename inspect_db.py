import sqlite3
import os

db_path = r"c:\Users\TafaraChitiyo-I-\Documents\CV Analysis\cv_analyzer\data\cv_analyzer.db"
if not os.path.exists(db_path):
    print(f"Database not found at {db_path}")
    exit(1)

conn = sqlite3.connect(db_path)
cur = conn.cursor()
tables = [t[0] for t in cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
print(f"TablesFound: {tables}")

for t in tables:
    print(f"\n--- Table: {t} ---")
    columns = cur.execute(f"PRAGMA table_info({t})").fetchall()
    for col in columns:
        print(f"Col: {col[1]} ({col[2]})")
conn.close()
