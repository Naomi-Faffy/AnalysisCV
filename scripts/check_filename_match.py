import os
import re
from pathlib import Path

base = Path(r"c:\Users\TafaraChitiyo-I-\Documents\CV Analysis")
up = base / "cv_analyzer" / "uploads"
requested = "CVs1_resume-362773107.pdf"


def norm(value):
    base_name = os.path.basename(str(value or '')).lower().strip()
    stem, ext = os.path.splitext(base_name)
    return re.sub(r'[^a-z0-9]+', '', stem), ext.lstrip('.')

requested_norm = norm(requested)
files = [p.name for p in up.iterdir() if p.is_file()]

matches = []
for name in files:
    candidate_norm = norm(name)
    if candidate_norm[0] == requested_norm[0] and (not requested_norm[1] or candidate_norm[1] == requested_norm[1]):
        matches = [name]
        break

if not matches and requested_norm[0]:
    matches = [name for name in files if norm(name)[0].startswith(requested_norm[0])]
if not matches and requested_norm[0]:
    matches = [name for name in files if requested_norm[0] in norm(name)[0]]
if not matches:
    matches = [name for name in files if name.lower() == requested.lower()]
if not matches:
    matches = [name for name in files if requested.lower() in name.lower()]

print(matches[:10])
