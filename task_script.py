import pandas as pd
import os
import re
import sys

# Add cv_analyzer to path to ensure imports work
sys.path.append(os.path.join(os.getcwd(), 'cv_analyzer'))

try:
    from cv_parser import CVParser
except ImportError:
    # Try direct import if path append didn't work as expected
    from cv_analyzer.cv_parser import CVParser

def get_tokens(text):
    if not text or not isinstance(text, str):
        return set()
    return set(re.findall(r'\w+', text.lower()))

# Load candidates
df = pd.read_excel(os.path.join('cv_analyzer', 'data', 'applicants.xlsx'))
candidate = df[df['Email'] == 'nicolemazhambee@gmail.com']

if candidate.empty:
    print('Candidate not found')
    sys.exit()

row = candidate.iloc[0]
components = [
    str(row.get('Profile Keywords', '')),
    str(row.get('Skills', '')),
    str(row.get('Education', '')),
    str(row.get('Current Role', '')),
    str(row.get('Applied Job Title', ''))
]
target_text = " ".join(components)
target_tokens = get_tokens(target_text)

parser = CVParser()
best_file = None
best_score = -1
results = []

uploads_dir = os.path.join('cv_analyzer', 'uploads')
for filename in os.listdir(uploads_dir):
    filepath = os.path.join(uploads_dir, filename)
    if os.path.isfile(filepath):
        try:
            parsed_data = parser.parse(filepath)
            if isinstance(parsed_data, tuple):
                resume_text = parsed_data[0]
            elif isinstance(parsed_data, dict):
                resume_text = parsed_data.get('text', '')
            else:
                resume_text = str(parsed_data)
                
            resume_tokens = get_tokens(resume_text)
            overlap = len(target_tokens.intersection(resume_tokens))
            
            results.append((filename, overlap))
            if overlap > best_score:
                best_score = overlap
                best_file = filename
        except Exception as e:
            continue

if not results:
    print('No files processed')
    sys.exit()

results.sort(key=lambda x: x[1], reverse=True)
best_file, best_score = results[0]

print(f'Best Match: {best_file}')
print(f'Overlap Score: {best_score}')
if best_score >= 5:
    print('Threshold Result: Success (>= 5 shared tokens)')
else:
    print('Threshold Result: No file qualifies (threshold 5)')
