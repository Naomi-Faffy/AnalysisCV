import os
import re
import uuid
from typing import Dict, List

import pandas as pd

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

class ExcelManager:
    def __init__(self, excel_path: str = None):
        if excel_path is None:
            excel_path = os.path.join(BASE_DIR, 'data', 'applicants.xlsx')
        self.excel_path = excel_path
        self.skill_columns = [
            'Python', 'JavaScript', 'SQL', 'Git', 'Java', 'C++', 'HTML', 'CSS',
            'React', 'Node.js', 'Django', 'Flask', 'Docker', 'AWS', 'Azure',
            'Communication', 'Leadership', 'Project Management', 'Data Analysis', 'Machine Learning'
        ]
        self.ensure_file_exists()

    def _empty_dataframe(self) -> pd.DataFrame:
        return pd.DataFrame(columns=self.get_columns())

    def _load_dataframe(self) -> pd.DataFrame:
        """Load applicants workbook safely and normalize required columns."""
        try:
            if not os.path.exists(self.excel_path):
                return self._empty_dataframe()

            df = pd.read_excel(self.excel_path)
            required = self.get_columns()
            for col in required:
                if col not in df.columns:
                    df[col] = 0 if col in self.skill_columns else ""
            return df[required]
        except Exception as e:
            print(f"Error loading applicants workbook; using empty dataframe: {e}")
            return self._empty_dataframe()

    def _save_dataframe(self, df: pd.DataFrame):
        os.makedirs(os.path.dirname(self.excel_path), exist_ok=True)
        df[self.get_columns()].to_excel(self.excel_path, index=False, sheet_name='Applicants')

    def _json_safe_records(self, df: pd.DataFrame) -> List[Dict]:
        """Convert dataframe rows to plain JSON-serializable dictionaries."""
        if df.empty:
            return []

        safe_df = df.copy()
        safe_df = safe_df.where(pd.notnull(safe_df), None)

        datetime_cols = ['Upload Date', 'Matched On']
        for col in datetime_cols:
            if col in safe_df.columns:
                safe_df[col] = pd.to_datetime(safe_df[col], errors='coerce').dt.strftime('%Y-%m-%d %H:%M:%S')
                safe_df[col] = safe_df[col].where(pd.notnull(safe_df[col]), '')

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

    def _extract_profile_keywords(self, candidate_data: Dict) -> str:
        raw_text = str(candidate_data.get('raw_text', '') or '')
        skills = [str(skill).strip() for skill in (candidate_data.get('skills', []) or []) if str(skill).strip()]
        education = candidate_data.get('education', []) or []
        current_role = str(candidate_data.get('experience', {}).get('current_role', '') or '')

        combined = ' '.join([
            raw_text,
            ' '.join(skills),
            ' '.join(item.get('qualification', '') for item in education if item.get('qualification')),
            current_role
        ]).lower()

        tokens = re.findall(r'\b[a-zA-Z][a-zA-Z0-9+.#/-]{2,}\b', combined)
        stop_words = {
            'the', 'and', 'for', 'with', 'from', 'that', 'this', 'have', 'has', 'was', 'were', 'are', 'your', 'you',
            'but', 'not', 'can', 'will', 'our', 'their', 'they', 'them', 'into', 'about', 'using', 'used', 'use',
            'role', 'cv', 'resume', 'experience', 'skills', 'work', 'team', 'year', 'years', 'able', 'ability',
            'responsible', 'responsibilities', 'requirements', 'qualification', 'qualifications'
        }

        deduped = []
        seen = set()
        for token in tokens:
            token = token.strip().lower()
            if len(token) < 3 or token in stop_words or token in seen:
                continue
            seen.add(token)
            deduped.append(token)

        return ' '.join(deduped[:250])

    def _candidate_match_terms(self, row: pd.Series) -> set:
        keywords = set(re.findall(r'\b[a-zA-Z][a-zA-Z0-9+.#/-]{2,}\b', str(row.get('Profile Keywords', '')).lower()))
        skills = {s.strip().lower() for s in str(row.get('Skills', '')).split(',') if s.strip()}
        derived = set(re.findall(r'\b[a-zA-Z][a-zA-Z0-9+.#/-]{2,}\b', ' '.join([
            str(row.get('Education', '') or ''),
            str(row.get('Education Level', '') or ''),
            str(row.get('Current Role', '') or '')
        ]).lower()))
        return {term for term in (keywords | skills | derived) if len(term) > 2}

    def _job_keywords(self, job: Dict) -> set:
        job_text = ' '.join([
            str(job.get('Job Title', '')),
            str(job.get('Department / Category', '')),
            str(job.get('Job Description', '')),
            str(job.get('Requirements / Qualifications', '')),
            str(job.get('Key Responsibilities', '')),
            str(job.get('Experience Level', '')),
            str(job.get('Work Mode', '')),
            str(job.get('Location', '')),
        ]).lower()

        keywords = set(re.findall(r'\b[a-zA-Z][a-zA-Z0-9+.#/-]{2,}\b', job_text))
        stop_words = {
            'the', 'and', 'for', 'with', 'from', 'that', 'this', 'have', 'has', 'was', 'were', 'are', 'your', 'you',
            'but', 'not', 'can', 'will', 'our', 'their', 'they', 'them', 'into', 'about', 'using', 'used', 'use',
            'role', 'job', 'jobs', 'position', 'candidate', 'applicants', 'application', 'requirements',
            'responsibilities', 'responsibility', 'skills', 'experience', 'qualification', 'qualifications',
            'department', 'category', 'work', 'mode', 'location'
        }
        return {term for term in keywords if term not in stop_words}

    def get_columns(self) -> List[str]:
        return [
            'Applicant ID',
            'Candidate Key',
            'First Name',
            'Last Name',
            'Email',
            'Phone',
            'Gender',
            'Age/DOB',
            'Age',
            'City',
            'Country',
            'Education',
            'Education Level',
            'Years of Experience',
            'Current Role',
            'Skills',
            'Has Driver\'s License',
            *self.skill_columns,
            'Identity Score',
            'Address Score',
            'Education Score',
            'Experience Score',
            'Skills Score',
            'Total Candidate Score',
            'Max Score',
            'Final Score (%)',
            'Applied Job ID',
            'Applied Job Title',
            'Match Score (%)',
            'Match Source',
            'Matched On',
            'Profile Keywords',
            'Upload Date',
            'CV File Name'
        ]

    def ensure_file_exists(self):
        os.makedirs(os.path.dirname(self.excel_path), exist_ok=True)
        if not os.path.exists(self.excel_path):
            df = pd.DataFrame(columns=self.get_columns())
            df.to_excel(self.excel_path, index=False, sheet_name='Applicants')
            return

        df = self._load_dataframe()
        required = self.get_columns()
        changed = False
        for col in required:
            if col not in df.columns:
                df[col] = 0 if col in self.skill_columns else ""
                changed = True
        if changed:
            df = df[required]
            df.to_excel(self.excel_path, index=False, sheet_name='Applicants')

    def candidate_exists(self, email: str) -> bool:
        try:
            if isinstance(email, dict):
                identifier = self._candidate_key(email)
            else:
                identifier = str(email or '').strip()

            if not identifier:
                return False
            df = self._load_dataframe()
            return bool(self._match_identifier_mask(df, identifier).any())
        except Exception:
            return False

    def _new_candidate_row(
        self,
        candidate_data: Dict,
        scores: Dict,
        file_name: str = "",
        job_assignment: Dict = None
    ) -> Dict:
        skills = candidate_data.get('skills', []) or []
        skills_set = {skill.strip().lower() for skill in skills}
        education_items = candidate_data.get('education', []) or []
        education_str = "; ".join(item.get('qualification', '').strip() for item in education_items if item.get('qualification'))
        job_assignment = job_assignment or {}
        candidate_key = self._candidate_key(candidate_data)

        row = {
            'Applicant ID': f"APP-{str(uuid.uuid4())[:8].upper()}",
            'Candidate Key': candidate_key,
            'First Name': candidate_data.get('first_name', ''),
            'Last Name': candidate_data.get('last_name', ''),
            'Email': str(candidate_data.get('email', '')).strip().lower(),
            'Phone': candidate_data.get('phone', ''),
            'Gender': candidate_data.get('gender', 'Not specified'),
            'Age/DOB': candidate_data.get('age_dob', ''),
            'Age': candidate_data.get('age', 0) or 0,
            'City': candidate_data.get('city', ''),
            'Country': candidate_data.get('country', ''),
            'Education': education_str,
            'Education Level': candidate_data.get('education_level', 'Unknown'),
            'Years of Experience': candidate_data.get('experience', {}).get('years', 0),
            'Current Role': candidate_data.get('experience', {}).get('current_role', ''),
            'Skills': ", ".join(skills),
            'Has Driver\'s License': 1 if candidate_data.get('has_driver_license', False) else 0,
            'Identity Score': scores.get('identity', 0),
            'Address Score': scores.get('address', 0),
            'Education Score': scores.get('education', 0),
            'Experience Score': scores.get('experience', 0),
            'Skills Score': scores.get('skills', 0),
            'Total Candidate Score': scores.get('total_candidate_score', 0),
            'Max Score': scores.get('max_score', 0),
            'Final Score (%)': scores.get('final_score', 0),
            'Applied Job ID': job_assignment.get('job_id', ''),
            'Applied Job Title': job_assignment.get('job_title', ''),
            'Match Score (%)': job_assignment.get('match_score', 0),
            'Match Source': job_assignment.get('match_source', ''),
            'Matched On': pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S') if job_assignment.get('job_id') else '',
            'Profile Keywords': self._extract_profile_keywords(candidate_data),
            'Upload Date': pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S'),
            'CV File Name': file_name,
        }

        for skill_col in self.skill_columns:
            row[skill_col] = 1 if skill_col.lower() in skills_set else 0

        return row

    def add_candidate(
        self,
        candidate_data: Dict,
        scores: Dict,
        file_name: str = "",
        job_assignment: Dict = None
    ) -> bool:
        try:
            df = self._load_dataframe()
            if self.candidate_exists(candidate_data):
                return False

            new_row = self._new_candidate_row(candidate_data, scores, file_name, job_assignment)
            df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
            self._save_dataframe(df)
            return True
        except Exception as e:
            print(f"Error adding candidate: {e}")
            return False

    def get_all_candidates(self) -> List[Dict]:
        try:
            df = self._load_dataframe()
            if 'Final Score (%)' in df.columns:
                df['Final Score (%)'] = pd.to_numeric(df['Final Score (%)'], errors='coerce').fillna(0)
            df = df.sort_values('Final Score (%)', ascending=False)
            return self._json_safe_records(df)
        except Exception:
            return []

    def get_top_candidates(self, limit: int = 10) -> List[Dict]:
        try:
            df = self._load_dataframe()
            if df.empty:
                return []
            if 'Final Score (%)' in df.columns:
                df['Final Score (%)'] = pd.to_numeric(df['Final Score (%)'], errors='coerce').fillna(0)
            df = df.sort_values('Final Score (%)', ascending=False).head(limit)
            return self._json_safe_records(df)
        except Exception:
            return []

    def _score_distribution(self, df: pd.DataFrame) -> Dict:
        if 'Final Score (%)' not in df.columns:
            return {}
        scores = pd.to_numeric(df['Final Score (%)'], errors='coerce').fillna(0)
        return {
            '90-100%': int((scores >= 90).sum()),
            '80-89%': int(((scores >= 80) & (scores < 90)).sum()),
            '70-79%': int(((scores >= 70) & (scores < 80)).sum()),
            '60-69%': int(((scores >= 60) & (scores < 70)).sum()),
            'Below 60%': int((scores < 60).sum())
        }

    def _skills_frequency(self, df: pd.DataFrame) -> Dict:
        freq = {}
        for skill in self.skill_columns:
            if skill in df.columns:
                freq[skill] = int(df[skill].fillna(0).astype(int).sum())
        freq = {k: v for k, v in freq.items() if v > 0}
        return dict(sorted(freq.items(), key=lambda item: item[1], reverse=True))

    def _experience_years_series(self, series: pd.Series) -> pd.Series:
        extracted = series.fillna('').astype(str).str.extract(r'(\d+(?:\.\d+)?)')[0]
        return pd.to_numeric(extracted, errors='coerce').fillna(0)

    def _normalize_identifier(self, value: str) -> str:
        return re.sub(r'[^a-z0-9]+', '', str(value or '').strip().lower())

    def _candidate_key(self, candidate_data: Dict) -> str:
        email = str(candidate_data.get('email', '') or '').strip().lower()
        if email:
            return email

        first_name = str(candidate_data.get('first_name', '') or '').strip().lower()
        last_name = str(candidate_data.get('last_name', '') or '').strip().lower()
        phone = self._normalize_identifier(candidate_data.get('phone', ''))
        full_name = self._normalize_identifier(f'{first_name} {last_name}'.strip())

        if full_name and phone:
            return f'{full_name}:{phone[-6:]}'
        if full_name:
            return full_name
        if phone:
            return f'phone:{phone}'
        return ''

    def _match_identifier_mask(self, df: pd.DataFrame, identifier: str) -> pd.Series:
        normalized = self._normalize_identifier(identifier)
        if not normalized:
            return pd.Series([False] * len(df), index=df.index)

        email_series = df.get('Email', pd.Series(index=df.index, dtype=str)).fillna('').astype(str).str.lower().str.replace(r'[^a-z0-9]+', '', regex=True)
        key_series = df.get('Candidate Key', pd.Series(index=df.index, dtype=str)).fillna('').astype(str).str.lower().str.replace(r'[^a-z0-9]+', '', regex=True)
        full_name_series = (
            df.get('First Name', pd.Series(index=df.index, dtype=str)).fillna('').astype(str).str.strip() + ' ' +
            df.get('Last Name', pd.Series(index=df.index, dtype=str)).fillna('').astype(str).str.strip()
        ).str.lower().str.replace(r'[^a-z0-9]+', '', regex=True)
        phone_series = df.get('Phone', pd.Series(index=df.index, dtype=str)).fillna('').astype(str).str.lower().str.replace(r'[^a-z0-9]+', '', regex=True)

        return (
            (email_series == normalized)
            | (key_series == normalized)
            | (full_name_series == normalized)
            | full_name_series.str.contains(normalized, na=False)
            | phone_series.eq(normalized)
        )

    def _candidate_profile_from_row(self, row: pd.Series) -> Dict:
        education_items = []
        for item in str(row.get('Education', '') or '').split(';'):
            item = item.strip()
            if item:
                education_items.append({'qualification': item})

        skills = [skill.strip() for skill in str(row.get('Skills', '') or '').split(',') if skill.strip()]
        years = self._experience_years_series(pd.Series([row.get('Years of Experience', 0)])).iloc[0]

        return {
            'first_name': row.get('First Name', ''),
            'last_name': row.get('Last Name', ''),
            'email': row.get('Email', ''),
            'phone': row.get('Phone', ''),
            'city': row.get('City', ''),
            'country': row.get('Country', ''),
            'education_level': row.get('Education Level', 'Unknown'),
            'education': education_items,
            'experience': {
                'years': int(years) if pd.notna(years) else 0,
                'current_role': row.get('Current Role', ''),
            },
            'skills': skills,
            'raw_text': ' '.join([
                str(row.get('Profile Keywords', '') or ''),
                str(row.get('Skills', '') or ''),
                str(row.get('Education', '') or ''),
                str(row.get('Current Role', '') or ''),
                str(row.get('Applied Job Title', '') or ''),
            ]),
        }

    def refresh_candidate_scores(self, scoring_system, jobs_manager=None) -> int:
        try:
            df = self._load_dataframe()
            if df.empty:
                return 0

            updated_rows = 0
            for idx, row in df.iterrows():
                candidate = self._candidate_profile_from_row(row)
                job = {}

                applied_job_id = str(row.get('Applied Job ID', '') or '').strip()
                if jobs_manager and applied_job_id:
                    job = jobs_manager.get_job_by_id(applied_job_id) or {}

                scores = scoring_system.get_score_breakdown(candidate, job=job or None)
                df.at[idx, 'Identity Score'] = scores.get('identity', 0)
                df.at[idx, 'Address Score'] = scores.get('address', 0)
                df.at[idx, 'Education Score'] = scores.get('education', 0)
                df.at[idx, 'Experience Score'] = scores.get('experience', 0)
                df.at[idx, 'Skills Score'] = scores.get('skills', 0)
                df.at[idx, 'Total Candidate Score'] = scores.get('total_candidate_score', 0)
                df.at[idx, 'Max Score'] = scores.get('max_score', 100)
                df.at[idx, 'Final Score (%)'] = scores.get('final_score', 0)
                updated_rows += 1

            self._save_dataframe(df)
            return updated_rows
        except Exception as exc:
            print(f"Error refreshing candidate scores: {exc}")
            return 0

    def get_statistics(self) -> Dict:
        try:
            df = self._load_dataframe()
            if df.empty:
                return {
                    'total_applicants': 0,
                    'average_score': 0,
                    'gender_distribution': {},
                    'location_distribution': {},
                    'city_distribution': {},
                    'education_distribution': {},
                    'experience_distribution': {},
                    'score_distribution': {},
                    'skills_frequency': {}
                }

            if 'Final Score (%)' in df.columns:
                df['Final Score (%)'] = pd.to_numeric(df['Final Score (%)'], errors='coerce').fillna(0)
            if 'Years of Experience' in df.columns:
                df['Years of Experience'] = self._experience_years_series(df['Years of Experience'])

            def _plain_counts(series):
                return {str(key): int(value) for key, value in series.fillna('Unknown').value_counts().to_dict().items()}

            experience_distribution = {
                '0 years': int((df['Years of Experience'] <= 0).sum()) if 'Years of Experience' in df.columns else 0,
                '1-2 years': int(((df['Years of Experience'] > 0) & (df['Years of Experience'] <= 2)).sum()) if 'Years of Experience' in df.columns else 0,
                '3-5 years': int(((df['Years of Experience'] > 2) & (df['Years of Experience'] <= 5)).sum()) if 'Years of Experience' in df.columns else 0,
                '6+ years': int((df['Years of Experience'] > 5).sum()) if 'Years of Experience' in df.columns else 0,
            }

            requirements_fit_distribution = {
                'All Applicants': int(len(df)),
                'Meet >=80%': int((df['Final Score (%)'] >= 80).sum()) if 'Final Score (%)' in df.columns else 0
            }

            # Explicit count of all rows (no filtering by score)
            total_count = int(len(df))
            avg_score = float(round(df['Final Score (%)'].mean(), 2)) if 'Final Score (%)' in df.columns else 0

            stats = {
                'total_applicants': total_count,  # Count ALL rows regardless of score
                'average_score': avg_score,
                'gender_distribution': _plain_counts(df['Gender']) if 'Gender' in df.columns else {},
                'location_distribution': _plain_counts(df['Country']) if 'Country' in df.columns else {},
                'city_distribution': _plain_counts(df['City']) if 'City' in df.columns else {},
                'education_distribution': _plain_counts(df['Education Level']) if 'Education Level' in df.columns else {},
                'experience_distribution': experience_distribution,
                'requirements_fit_distribution': requirements_fit_distribution,
                'score_distribution': self._score_distribution(df),
                'skills_frequency': self._skills_frequency(df)
            }
            return stats
        except Exception as e:
            print(f"Error getting statistics: {e}")
            return {}

    def filter_candidates(self, filters: Dict) -> List[Dict]:
        try:
            df = self._load_dataframe()

            if not filters:
                if 'Final Score (%)' in df.columns:
                    df['Final Score (%)'] = pd.to_numeric(df['Final Score (%)'], errors='coerce').fillna(0)
                    df = df.sort_values('Final Score (%)', ascending=False)
                return self._json_safe_records(df)

            if 'min_score' in filters:
                df = df[pd.to_numeric(df['Final Score (%)'], errors='coerce').fillna(0) >= float(filters['min_score'])]
            if 'max_score' in filters:
                df = df[pd.to_numeric(df['Final Score (%)'], errors='coerce').fillna(0) <= float(filters['max_score'])]
            if 'gender' in filters:
                df = df[df['Gender'].fillna('').str.lower() == str(filters['gender']).lower()]
            if 'country' in filters:
                df = df[df['Country'].fillna('').str.contains(str(filters['country']), case=False, na=False)]
            if 'city' in filters:
                df = df[df['City'].fillna('').str.contains(str(filters['city']), case=False, na=False)]
            if 'education_level' in filters:
                df = df[df['Education Level'].fillna('').str.contains(str(filters['education_level']), case=False, na=False)]
            if 'min_experience' in filters:
                df = df[pd.to_numeric(df['Years of Experience'], errors='coerce').fillna(0) >= float(filters['min_experience'])]
            if 'applied_job_id' in filters:
                df = df[df['Applied Job ID'].fillna('').astype(str) == str(filters['applied_job_id'])]
            if 'applied_job_title' in filters:
                df = df[df['Applied Job Title'].fillna('').str.contains(str(filters['applied_job_title']), case=False, na=False)]
            if 'has_driver_license' in filters:
                license_value = str(filters['has_driver_license']).lower()
                if license_value in ['true', '1', 'yes']:
                    df = df[pd.to_numeric(df['Has Driver\'s License'], errors='coerce').fillna(0).astype(int) == 1]
                elif license_value in ['false', '0', 'no']:
                    df = df[pd.to_numeric(df['Has Driver\'s License'], errors='coerce').fillna(0).astype(int) == 0]
            if 'skill' in filters:
                skill_value = str(filters['skill']).strip().lower()
                matching_skill_cols = [col for col in self.skill_columns if col.lower() == skill_value]
                if matching_skill_cols:
                    col = matching_skill_cols[0]
                    df = df[df[col].fillna(0).astype(int) == 1]
                else:
                    df = df[df['Skills'].fillna('').str.contains(skill_value, case=False, na=False)]
            if 'search' in filters:
                query = str(filters['search'])
                df = df[
                    df['First Name'].fillna('').str.contains(query, case=False, na=False)
                    | df['Last Name'].fillna('').str.contains(query, case=False, na=False)
                    | df['Email'].fillna('').str.contains(query, case=False, na=False)
                    | df['Candidate Key'].fillna('').str.contains(query, case=False, na=False)
                ]

            df['Final Score (%)'] = pd.to_numeric(df['Final Score (%)'], errors='coerce').fillna(0)
            df = df.sort_values('Final Score (%)', ascending=False)
            return self._json_safe_records(df)
        except Exception as e:
            print(f"Error filtering candidates: {e}")
            return []

    def export_to_excel(self, data: List[Dict], filename: str) -> bool:
        try:
            if not data:
                return False
            os.makedirs("data", exist_ok=True)
            df = pd.DataFrame(data)
            path = os.path.join("data", f"{filename}.xlsx")
            df.to_excel(path, index=False)
            return True
        except Exception as e:
            print(f"Error exporting to Excel: {e}")
            return False

    def delete_candidate(self, email: str) -> bool:
        try:
            df = self._load_dataframe()
            df = df[~self._match_identifier_mask(df, email)]
            self._save_dataframe(df)
            return True
        except Exception as e:
            print(f"Error deleting candidate: {e}")
            return False

    def get_candidate_by_email(self, email: str) -> Dict:
        try:
            df = self._load_dataframe()
            result = df[self._match_identifier_mask(df, email)]
            if not result.empty:
                row = self._json_safe_records(result.head(1))
                return row[0] if row else {}
            return {}
        except Exception:
            return {}

    def assign_candidates_to_job(self, job: Dict, threshold: float = 30.0) -> int:
        try:
            if not job or not job.get('Job ID'):
                return 0

            df = self._load_dataframe()
            if df.empty:
                return 0

            job_keywords = self._job_keywords(job)
            if not job_keywords:
                return 0

            matched = 0
            for idx, row in df.iterrows():
                candidate_terms = self._candidate_match_terms(row)
                if not candidate_terms:
                    continue

                keyword_hits = candidate_terms & job_keywords
                keyword_score = (len(keyword_hits) / max(len(job_keywords), 1)) * 100

                title_terms = set(re.findall(r'\b[a-zA-Z][a-zA-Z0-9+.#/-]{2,}\b', str(job.get('Job Title', '')).lower()))
                title_terms = {term for term in title_terms if term not in {'the', 'and', 'for', 'with', 'from', 'that', 'this', 'have', 'has', 'was', 'were', 'are', 'your', 'you'}}
                title_score = (len(candidate_terms & title_terms) / max(len(title_terms), 1)) * 100 if title_terms else 0

                score = round((keyword_score * 0.75) + (title_score * 0.25), 2)

                if score >= threshold:
                    df.at[idx, 'Applied Job ID'] = job.get('Job ID', '')
                    df.at[idx, 'Applied Job Title'] = job.get('Job Title', '')
                    df.at[idx, 'Match Score (%)'] = score
                    df.at[idx, 'Match Source'] = 'CV Bank Match'
                    df.at[idx, 'Matched On'] = pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')
                    matched += 1

            self._save_dataframe(df)
            return matched
        except Exception as e:
            print(f"Error assigning candidates to job: {e}")
            return 0
