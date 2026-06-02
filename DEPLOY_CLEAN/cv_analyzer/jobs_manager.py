import os
import uuid
from datetime import datetime
from typing import Dict, List

import pandas as pd

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

class JobsManager:
    def __init__(self, excel_path: str = None):
        if excel_path is None:
            excel_path = os.path.join(BASE_DIR, 'data', 'jobs.xlsx')
        self.excel_path = excel_path
        self.ensure_file_exists()

    def get_columns(self) -> List[str]:
        return [
            'Job ID',
            'Job Title',
            'Department / Category',
            'Job Type',
            'Work Mode',
            'Location',
            'Job Description',
            'Key Responsibilities',
            'Requirements / Qualifications',
            'Experience Level',
            'Application Deadline',
            'Post Date',
            'Status',
            'Is Active'
        ]

    def _empty_dataframe(self) -> pd.DataFrame:
        return pd.DataFrame(columns=self.get_columns())

    def _load_dataframe(self) -> pd.DataFrame:
        try:
            if not os.path.exists(self.excel_path):
                return self._empty_dataframe()

            df = pd.read_excel(self.excel_path)
            required = self.get_columns()
            for col in required:
                if col not in df.columns:
                    df[col] = 0 if col == 'Is Active' else ''
            return df[required]
        except Exception as e:
            print(f"Error loading jobs workbook; using empty dataframe: {e}")
            return self._empty_dataframe()

    def _save_dataframe(self, df: pd.DataFrame):
        os.makedirs(os.path.dirname(self.excel_path), exist_ok=True)
        df[self.get_columns()].to_excel(self.excel_path, index=False, sheet_name='Jobs')

    def _json_safe_records(self, df: pd.DataFrame) -> List[Dict]:
        if df.empty:
            return []

        safe_df = df.copy()
        if 'Post Date' in safe_df.columns:
            safe_df['Post Date'] = pd.to_datetime(safe_df['Post Date'], errors='coerce').dt.strftime('%Y-%m-%d %H:%M:%S')
            safe_df['Post Date'] = safe_df['Post Date'].where(pd.notnull(safe_df['Post Date']), '')

        safe_df = safe_df.where(pd.notnull(safe_df), None)
        records = safe_df.to_dict('records')

        def _to_py(value):
            if hasattr(value, 'item'):
                try:
                    return value.item()
                except Exception:
                    return str(value)
            if pd.isna(value):
                return None
            return value

        return [{key: _to_py(val) for key, val in row.items()} for row in records]

    def ensure_file_exists(self):
        os.makedirs(os.path.dirname(self.excel_path), exist_ok=True)
        if not os.path.exists(self.excel_path):
            df = pd.DataFrame(columns=self.get_columns())
            df.to_excel(self.excel_path, index=False, sheet_name='Jobs')
            return

        df = self._load_dataframe()
        required = self.get_columns()
        changed = False
        for col in required:
            if col not in df.columns:
                df[col] = ''
                changed = True
        if changed:
            df = df[required]
            df.to_excel(self.excel_path, index=False, sheet_name='Jobs')

    def _normalize_text(self, value: str) -> str:
        return str(value or '').strip()

    def add_job(self, job_data: Dict) -> Dict:
        try:
            df = self._load_dataframe()
            job_id = f"JOB-{str(uuid.uuid4())[:8].upper()}"
            post_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            deadline = self._normalize_text(job_data.get('Application Deadline', ''))
            new_row = {
                'Job ID': job_id,
                'Job Title': self._normalize_text(job_data.get('Job Title', '')),
                'Department / Category': self._normalize_text(job_data.get('Department / Category', '')),
                'Job Type': self._normalize_text(job_data.get('Job Type', '')),
                'Work Mode': self._normalize_text(job_data.get('Work Mode', '')),
                'Location': self._normalize_text(job_data.get('Location', '')),
                'Job Description': self._normalize_text(job_data.get('Job Description', '')),
                'Key Responsibilities': self._normalize_text(job_data.get('Key Responsibilities', '')),
                'Requirements / Qualifications': self._normalize_text(job_data.get('Requirements / Qualifications', '')),
                'Experience Level': self._normalize_text(job_data.get('Experience Level', '')),
                'Application Deadline': deadline,
                'Post Date': post_date,
                'Status': 'Active',
                'Is Active': 1,
            }

            if not df.empty:
                df['Status'] = 'Inactive'
                df['Is Active'] = 0

            df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
            self._save_dataframe(df)
            return {'success': True, 'job': new_row}
        except Exception as e:
            print(f"Error adding job: {e}")
            return {'success': False, 'error': str(e)}

    def get_all_jobs(self) -> List[Dict]:
        try:
            df = self._load_dataframe()
            if df.empty:
                return []
            df['Post Date'] = pd.to_datetime(df['Post Date'], errors='coerce')
            if 'Is Active' in df.columns:
                df['Is Active'] = pd.to_numeric(df['Is Active'], errors='coerce').fillna(0).astype(int)
            df = df.sort_values('Post Date', ascending=False, na_position='last')
            return self._json_safe_records(df)
        except Exception:
            return []

    def get_job_by_id(self, job_id: str) -> Dict:
        try:
            df = self._load_dataframe()
            result = df[df['Job ID'].fillna('').astype(str) == str(job_id)]
            if not result.empty:
                records = self._json_safe_records(result.head(1))
                return records[0] if records else {}
            return {}
        except Exception:
            return {}

    def get_active_job(self) -> Dict:
        try:
            df = self._load_dataframe()
            if df.empty:
                return {}

            if 'Is Active' in df.columns:
                active = df[pd.to_numeric(df['Is Active'], errors='coerce').fillna(0).astype(int) == 1]
                if not active.empty:
                    records = self._json_safe_records(active.head(1))
                    return records[0] if records else {}

            if 'Status' in df.columns:
                active = df[df['Status'].fillna('').astype(str).str.lower() == 'active']
                if not active.empty:
                    records = self._json_safe_records(active.head(1))
                    return records[0] if records else {}

            return {}
        except Exception:
            return {}

    def set_active_job(self, job_id: str) -> Dict:
        try:
            df = self._load_dataframe()
            if df.empty:
                return {'success': False, 'error': 'No jobs found'}

            target_mask = df['Job ID'].fillna('').astype(str) == str(job_id)
            if not target_mask.any():
                return {'success': False, 'error': 'Job not found'}

            df['Status'] = 'Inactive'
            df['Is Active'] = 0
            df.loc[target_mask, 'Status'] = 'Active'
            df.loc[target_mask, 'Is Active'] = 1

            self._save_dataframe(df)

            records = self._json_safe_records(df[target_mask].head(1))
            job = records[0] if records else {}
            return {'success': True, 'job': job}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def delete_job(self, job_id: str) -> Dict:
        try:
            df = self._load_dataframe()
            if df.empty:
                return {'success': False, 'error': 'No jobs found'}

            target_mask = df['Job ID'].fillna('').astype(str) == str(job_id)
            if not target_mask.any():
                return {'success': False, 'error': 'Job not found'}

            deleted_row = self._json_safe_records(df[target_mask].head(1))
            deleted_job = deleted_row[0] if deleted_row else {}
            active_value = pd.to_numeric(deleted_job.get('Is Active', 0), errors='coerce')
            was_active = (pd.notna(active_value) and int(active_value) == 1) or str(deleted_job.get('Status', '')).lower() == 'active'

            df = df[~target_mask].copy()
            if not df.empty:
                df['Status'] = df['Status'].fillna('Inactive')
                df['Is Active'] = pd.to_numeric(df['Is Active'], errors='coerce').fillna(0).astype(int)
            self._save_dataframe(df)

            return {'success': True, 'job': deleted_job, 'was_active': was_active}
        except Exception as e:
            return {'success': False, 'error': str(e)}