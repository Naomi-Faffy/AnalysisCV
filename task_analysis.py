import pandas as pd
import os
import re
from cv_analyzer.cv_parser import CVParser

def tokenize(text):
    if not isinstance(text, str):
        return set()
    return set(re.findall(r'\w+', text.lower()))

# Load applicants
df = pd.read_excel(r'cv_analyzer\data\applicants.xlsx')
target_email = 'nicolemazhambee@gmail.com'
applicant = df[df['Email'] == target_email]

if applicant.empty:
    print(f'Applicant with email {target_email} not found.')
    exit(1)

applicant = applicant.iloc[0]
target_tokens = set()
for col in ['Profile Keywords', 'Skills', 'Education', 'Current Role', 'Applied Job Title']:
    target_tokens.update(tokenize(applicant.get(col, '')))

print(f'Target tokens for {target_email}: {len(target_tokens)}')

best_file = None
max_overlap = -1
uploads_dir = r'cv_analyzer\uploads'
parser = CVParser()

for filename in os.listdir(uploads_dir):
    file_path = os.path.join(uploads_dir, filename)
    if not os.path.isfile(file_path):
        continue
    
    try:
        parsed_data = parser.parse_cv(file_path)
        raw_text = parsed_data.get('raw_text', '')
        file_tokens = tokenize(raw_text)
        overlap = len(target_tokens.intersection(file_tokens))
        
        if overlap > max_overlap:
            max_overlap = overlap
            best_file = filename
            
    except Exception as e:
        print(f'Error parsing {filename}: {e}')

if best_file:
    print(f'Best match: {best_file} with {max_overlap} overlapping tokens.')
    if max_overlap <= 5:
        print('The best overlap is quite low.')
else:
    print('No files were successfully processed or no overlap found.')

