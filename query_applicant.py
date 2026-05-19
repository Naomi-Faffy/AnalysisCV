import sqlite3
import os

db_path = r'c:\Users\TafaraChitiyo-I-\Documents\CV Analysis\cv_analyzer\data\cv_analyzer.db'
if not os.path.exists(db_path):
    print(f'Database not found at {db_path}')
    exit(1)

conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

email = 'nicolemazhambee@gmail.com'

print(f'--- Applicant Info ---')
cursor.execute('SELECT * FROM applicants WHERE email = ?', (email,))
applicant = cursor.fetchone()
if applicant:
    applicant_id = applicant['id']
    for key in applicant.keys():
        print(f'{key}: {applicant[key]}')
    
    print(f'\n--- Matching Uploaded Files ---')
    cursor.execute('SELECT * FROM uploaded_files WHERE applicant_id = ?', (applicant_id,))
    files = cursor.fetchall()
    if files:
        for file in files:
            print(f'File ID: {file["id"]}')
            for key in file.keys():
                print(f'  {key}: {file[key]}')
    else:
        print('No matching rows in uploaded_files for this applicant_id.')
else:
    print(f'No applicant found with email {email}')

conn.close()
