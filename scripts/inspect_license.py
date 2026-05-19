import pandas as pd, os, sys
path=r"c:\Users\TafaraChitiyo-I-\Documents\CV Analysis\cv_analyzer\data\applicants.xlsx"
if not os.path.exists(path):
    print('MISSING')
    sys.exit(0)
df=pd.read_excel(path)
col="Has Driver's License"
if col not in df.columns:
    print('NO_COL')
    sys.exit(0)
vals=df[col].fillna('<<NA>>').astype(str).value_counts().to_dict()
for k,v in vals.items():
    print(repr(k), v)
