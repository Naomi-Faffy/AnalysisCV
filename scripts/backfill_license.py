import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'cv_analyzer'))
from cv_parser import CVParser
from excel_manager import ExcelManager
import os

BASE_DIR = r"c:\Users\TafaraChitiyo-I-\Documents\CV Analysis"
UPLOADS = os.path.join(BASE_DIR, 'cv_analyzer', 'uploads')
EXCEL = os.path.join(BASE_DIR, 'cv_analyzer', 'data', 'applicants.xlsx')

parser = CVParser()
manager = ExcelManager(EXCEL)

df = manager._load_dataframe()
if df.empty:
    print('No applicants to update')
    exit(0)

updated = 0
for idx, row in df.iterrows():
    cvname = str(row.get('CV File Name', '') or '').strip()
    if not cvname:
        continue
    candidate_path = os.path.join(UPLOADS, cvname)
    if not os.path.exists(candidate_path):
        # try tolerant matching
        for f in os.listdir(UPLOADS):
            if cvname.lower() in f.lower():
                candidate_path = os.path.join(UPLOADS, f)
                break
    if not os.path.exists(candidate_path):
        continue
    try:
        parsed = parser.parse_cv(candidate_path)
        has_license = 1 if parsed.get('has_driver_license') else 0
        prev = df.at[idx, "Has Driver's License"]
        if int(prev) != int(has_license):
            df.at[idx, "Has Driver's License"] = has_license
            updated += 1
    except Exception as e:
        print('Failed to parse', candidate_path, e)

if updated:
    manager._save_dataframe(df)

print(f'Backfill complete, updated {updated} rows')
