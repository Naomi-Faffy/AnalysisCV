from flask import Flask, render_template, request, jsonify, send_file, Response
import mimetypes
from flask_cors import CORS
import os
import re
import shutil
import json
from io import BytesIO
from functools import lru_cache
from werkzeug.utils import secure_filename
from cv_parser import CVParser
from scoring import ScoringSystem
from excel_manager import ExcelManager
from jobs_manager import JobsManager
from blob_storage import BlobStorageClient
import pandas as pd
from datetime import datetime
try:
    import mammoth
except Exception:
    mammoth = None

app = Flask(__name__)
CORS(app)

# Security settings
app.secret_key = os.environ.get('SECRET_KEY', os.urandom(24))

# Configuration
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RUNTIME_BASE_DIR = BASE_DIR
DEFAULT_STORAGE_ROOT = '/var/data/cv-analyzer' if os.getenv('RENDER') else RUNTIME_BASE_DIR
STORAGE_ROOT = os.getenv('CV_ANALYZER_STORAGE_DIR', DEFAULT_STORAGE_ROOT)
DATA_FOLDER = os.getenv('CV_ANALYZER_DATA_DIR', os.path.join(STORAGE_ROOT, 'data'))
UPLOAD_FOLDER = os.getenv('CV_ANALYZER_UPLOAD_DIR', os.path.join(STORAGE_ROOT, 'uploads'))
ALLOWED_EXTENSIONS = {'pdf', 'docx'}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB per individual file
MAX_BATCH_SIZE = 300 * 1024 * 1024  # 300MB for batch uploads (~20 CVs)
APPLICANTS_FILE = os.path.join(DATA_FOLDER, 'applicants.xlsx')
JOBS_FILE = os.path.join(DATA_FOLDER, 'jobs.xlsx')

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_BATCH_SIZE

# Initialize components
cv_parser = CVParser()
scoring_system = ScoringSystem()
excel_manager = ExcelManager(os.path.join(DATA_FOLDER, 'applicants.xlsx'))
jobs_manager = JobsManager(os.path.join(DATA_FOLDER, 'jobs.xlsx'))
blob_storage_client = BlobStorageClient()

# Ensure folders exist
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(DATA_FOLDER, exist_ok=True)


def _migrate_legacy_storage_once():
    """Migrate old local data/uploads into configured storage if destination is empty."""
    legacy_data_dir = os.path.join(RUNTIME_BASE_DIR, 'data')
    legacy_upload_dir = os.path.join(RUNTIME_BASE_DIR, 'uploads')

    if os.path.abspath(DATA_FOLDER) != os.path.abspath(legacy_data_dir):
        for filename in ['applicants.xlsx', 'jobs.xlsx', 'master_skills.json']:
            legacy_file = os.path.join(legacy_data_dir, filename)
            target_file = os.path.join(DATA_FOLDER, filename)
            if os.path.exists(legacy_file) and not os.path.exists(target_file):
                try:
                    shutil.copy2(legacy_file, target_file)
                except Exception as exc:
                    print(f"Warning: failed to migrate {legacy_file} -> {target_file}: {exc}")

    if os.path.abspath(UPLOAD_FOLDER) != os.path.abspath(legacy_upload_dir):
        try:
            target_has_files = any(
                os.path.isfile(os.path.join(UPLOAD_FOLDER, name))
                for name in os.listdir(UPLOAD_FOLDER)
            )
        except Exception:
            target_has_files = False

        if not target_has_files and os.path.exists(legacy_upload_dir):
            for filename in os.listdir(legacy_upload_dir):
                legacy_file = os.path.join(legacy_upload_dir, filename)
                target_file = os.path.join(UPLOAD_FOLDER, filename)
                if os.path.isfile(legacy_file) and not os.path.exists(target_file):
                    try:
                        shutil.copy2(legacy_file, target_file)
                    except Exception as exc:
                        print(f"Warning: failed to migrate {legacy_file} -> {target_file}: {exc}")


_migrate_legacy_storage_once()

print(
    "[startup] storage configured "
    f"render={bool(os.getenv('RENDER'))} "
    f"storage_root={STORAGE_ROOT} "
    f"data_dir={DATA_FOLDER} "
    f"upload_dir={UPLOAD_FOLDER}"
)

try:
    excel_manager.refresh_candidate_scores(scoring_system, jobs_manager)
except Exception as exc:
    print(f"Warning: could not refresh candidate scores on startup: {exc}")


def get_effective_job(job_id: str = "") -> dict:
    """Return explicit job by id, else active job if available."""
    if job_id:
        return jobs_manager.get_job_by_id(job_id) or {}
    return jobs_manager.get_active_job() or {}


def build_job_assignment(candidate_data: dict, job: dict) -> dict:
    """Create candidate-to-job assignment metadata using skill keyword matching."""
    if not job or not job.get('Job ID'):
        return {}

    def normalize_terms(text: str) -> set:
        tokens = set(re.findall(r'\b[a-zA-Z][a-zA-Z0-9+.#/-]{2,}\b', text.lower()))
        stop_words = {
            'the', 'and', 'for', 'with', 'from', 'that', 'this', 'have', 'has', 'was', 'were', 'are', 'your', 'you',
            'but', 'not', 'can', 'will', 'our', 'their', 'they', 'them', 'into', 'about', 'using', 'used', 'use',
            'role', 'job', 'jobs', 'position', 'candidate', 'applicants', 'application', 'requirements',
            'responsibilities', 'responsibility', 'skills', 'experience', 'qualification', 'qualifications',
            'department', 'category', 'work', 'mode', 'location'
        }
        return {token for token in tokens if token not in stop_words}

    job_text = " ".join([
        str(job.get('Job Title', '')),
        str(job.get('Department / Category', '')),
        str(job.get('Job Description', '')),
        str(job.get('Requirements / Qualifications', '')),
        str(job.get('Key Responsibilities', '')),
        str(job.get('Experience Level', '')),
        str(job.get('Work Mode', '')),
        str(job.get('Location', '')),
    ])
    job_terms = normalize_terms(job_text)

    cv_text = " ".join([
        str(candidate_data.get('raw_text', '') or ''),
        ' '.join(candidate_data.get('skills', []) or []),
        ' '.join(item.get('qualification', '') for item in (candidate_data.get('education', []) or []) if item.get('qualification')),
        str(candidate_data.get('experience', {}).get('current_role', '') or ''),
    ])
    candidate_terms = normalize_terms(cv_text)

    if not candidate_terms or not job_terms:
        return {
            'job_id': job.get('Job ID', ''),
            'job_title': job.get('Job Title', ''),
            'match_score': 0,
            'match_source': 'Active Job'
        }

    keyword_score = (len(candidate_terms & job_terms) / max(len(job_terms), 1)) * 100
    title_terms = normalize_terms(str(job.get('Job Title', '')))
    title_score = (len(candidate_terms & title_terms) / max(len(title_terms), 1)) * 100 if title_terms else 0
    match_score = round((keyword_score * 0.75) + (title_score * 0.25), 2)
    return {
        'job_id': job.get('Job ID', ''),
        'job_title': job.get('Job Title', ''),
        'match_score': match_score,
        'match_source': 'Active Job'
    }


def _clear_directory_contents(directory_path: str):
    if not os.path.exists(directory_path):
        return

    for entry_name in os.listdir(directory_path):
        entry_path = os.path.join(directory_path, entry_name)
        try:
            if os.path.isdir(entry_path):
                shutil.rmtree(entry_path)
            else:
                os.remove(entry_path)
        except Exception as exc:
            print(f"Warning: could not remove {entry_path}: {exc}")


def _normalize_file_token(value: str) -> tuple:
    base_name = os.path.basename(str(value or '')).lower().strip()
    stem, ext = os.path.splitext(base_name)
    normalized_stem = re.sub(r'[^a-z0-9]+', '', stem)
    return normalized_stem, ext.lstrip('.')


def _normalize_text_tokens(value: str) -> set:
    tokens = set(re.findall(r'\b[a-zA-Z][a-zA-Z0-9+.#/-]{2,}\b', str(value or '').lower()))
    stop_words = {
        'the', 'and', 'for', 'with', 'from', 'that', 'this', 'have', 'has', 'was', 'were', 'are', 'your', 'you',
        'but', 'not', 'can', 'will', 'our', 'their', 'they', 'them', 'into', 'about', 'using', 'used', 'use',
        'role', 'job', 'jobs', 'position', 'candidate', 'applicants', 'application', 'requirements',
        'responsibilities', 'responsibility', 'skills', 'experience', 'qualification', 'qualifications',
        'department', 'category', 'work', 'mode', 'location'
    }
    return {token for token in tokens if token not in stop_words}


@lru_cache(maxsize=1)
def _get_uploaded_file_index():
    upload_folder = app.config.get('UPLOAD_FOLDER', '')
    try:
        candidate_names = [
            f for f in os.listdir(upload_folder)
            if os.path.isfile(os.path.join(upload_folder, f))
        ]
    except Exception:
        candidate_names = []

    indexed_files = []
    for candidate_name in candidate_names:
        candidate_path = os.path.join(upload_folder, candidate_name)
        parsed = {}
        try:
            parsed = cv_parser.parse_cv(candidate_path) or {}
        except Exception:
            parsed = {}

        parsed_email = str(parsed.get('email', '') or '').strip().lower()
        parsed_name = re.sub(
            r'[^a-z0-9]+', '',
            f"{parsed.get('first_name', '')} {parsed.get('last_name', '')}".strip().lower(),
        )
        parsed_phone = re.sub(r'[^a-z0-9]+', '', str(parsed.get('phone', '') or '').strip().lower())
        indexed_files.append({
            'name': candidate_name,
            'path': candidate_path,
            'stem': _normalize_file_token(candidate_name)[0],
            'ext': _normalize_file_token(candidate_name)[1],
            'email': parsed_email,
            'name_key': parsed_name,
            'phone_key': parsed_phone,
            'raw_tokens': _normalize_text_tokens(parsed.get('raw_text', '') or ''),
        })

    return indexed_files


def _resolve_uploaded_file(file_reference: str, candidate_hint: dict = None):
    """Resolve an uploaded CV file path from a stored filename or candidate info."""
    upload_folder = app.config.get('UPLOAD_FOLDER', '')
    safe_name = os.path.basename(str(file_reference or '').strip())
    if not safe_name:
        return None, ''

    direct_path = os.path.join(upload_folder, safe_name)
    if os.path.exists(direct_path):
        return direct_path, safe_name

    try:
        candidates = [
            f for f in os.listdir(upload_folder)
            if os.path.isfile(os.path.join(upload_folder, f))
        ]
    except Exception:
        candidates = []

    requested_stem, requested_ext = _normalize_file_token(safe_name)
    indexed_files = _get_uploaded_file_index()
    for candidate_file in indexed_files:
        candidate_name = candidate_file['name']
        candidate_stem = candidate_file['stem']
        candidate_ext = candidate_file['ext']
        if candidate_stem == requested_stem and (not requested_ext or candidate_ext == requested_ext):
            return candidate_file['path'], candidate_name

    if requested_stem:
        for candidate_file in indexed_files:
            candidate_name = candidate_file['name']
            candidate_stem = candidate_file['stem']
            if candidate_stem.startswith(requested_stem) or requested_stem in candidate_stem:
                return candidate_file['path'], candidate_name

    if candidate_hint:
        target_email = str(candidate_hint.get('Email', '') or '').strip().lower()
        target_name = re.sub(
            r'[^a-z0-9]+', '',
            f"{candidate_hint.get('First Name', '')} {candidate_hint.get('Last Name', '')}".strip().lower(),
        )
        target_phone = re.sub(r'[^a-z0-9]+', '', str(candidate_hint.get('Phone', '') or '').strip().lower())

        for candidate_file in indexed_files:
            candidate_name = candidate_file['name']
            candidate_path = candidate_file['path']
            parsed_email = candidate_file['email']
            parsed_name = candidate_file['name_key']
            parsed_phone = candidate_file['phone_key']

            if target_email and parsed_email and parsed_email == target_email:
                return candidate_path, candidate_name
            if target_name and parsed_name and (parsed_name == target_name or parsed_name in target_name or target_name in parsed_name):
                return candidate_path, candidate_name
            if target_phone and parsed_phone and parsed_phone == target_phone:
                return candidate_path, candidate_name

        target_keywords = _normalize_text_tokens(
            ' '.join([
                str(candidate_hint.get('Profile Keywords', '') or ''),
                str(candidate_hint.get('Skills', '') or ''),
                str(candidate_hint.get('Education', '') or ''),
                str(candidate_hint.get('Current Role', '') or ''),
                str(candidate_hint.get('Applied Job Title', '') or ''),
            ])
        )
        if target_keywords:
            best_match = (0, None, '')
            for candidate_file in indexed_files:
                overlap = len(target_keywords & candidate_file.get('raw_tokens', set()))
                if overlap > best_match[0]:
                    best_match = (overlap, candidate_file['path'], candidate_file['name'])
            if best_match[0] >= 5 and best_match[1]:
                return best_match[1], best_match[2]

    if blob_storage_client.enabled:
        blob_candidates = []
        if safe_name:
            blob_candidates.extend([
                safe_name,
                f'uploads/{safe_name}',
            ])

        for blob_path in blob_candidates:
            try:
                restored = blob_storage_client.download_file(blob_path, direct_path)
                if restored and os.path.exists(direct_path):
                    return direct_path, safe_name
            except Exception:
                continue

    return None, ''


def _serve_uploaded_file(file_path: str, safe_name: str):
    mime_type, _ = mimetypes.guess_type(file_path)
    ext = os.path.splitext(file_path)[1].lower()
    inline_exts = {'.pdf', '.png', '.jpg', '.jpeg', '.txt', '.html'}

    if ext == '.docx':
        if mammoth is not None:
            try:
                with open(file_path, 'rb') as docx_file:
                    result = mammoth.convert_to_html(docx_file)
                    html = result.value or ''
                    wrapper = f"<html><head><meta charset=\"utf-8\"></head><body>{html}</body></html>"
                    headers = {'Content-Disposition': f'inline; filename="{safe_name}.html"'}
                    return Response(wrapper, mimetype='text/html', headers=headers)
            except Exception as e:
                print(f"Mammoth conversion failed for {file_path}: {e}")
                return send_file(file_path, as_attachment=True, download_name=safe_name, mimetype=mime_type)
        return send_file(file_path, as_attachment=True, download_name=safe_name, mimetype=mime_type)

    as_attachment = not (ext in inline_exts)
    resp = send_file(file_path, as_attachment=as_attachment, download_name=safe_name, mimetype=mime_type)
    if not as_attachment:
        try:
            resp.headers['Content-Disposition'] = f'inline; filename={safe_name}'
        except Exception:
            pass
    return resp


def _with_cv_availability(candidate: dict) -> dict:
    candidate_data = dict(candidate or {})
    resolved_path, resolved_name = _resolve_uploaded_file(
        candidate_data.get('CV File Name', ''),
        candidate_hint=candidate_data,
    )
    candidate_data['CV Available'] = bool(resolved_path)
    if resolved_name:
        candidate_data['Resolved CV File Name'] = resolved_name
    return candidate_data


def _parse_active_job_filters(args) -> dict:
    filters = {}
    if args.get('min_score'):
        try:
            filters['min_score'] = float(args.get('min_score'))
        except Exception:
            pass
    if args.get('max_score'):
        try:
            filters['max_score'] = float(args.get('max_score'))
        except Exception:
            pass
    if args.get('gender'):
        filters['gender'] = args.get('gender')
    if args.get('country'):
        filters['country'] = args.get('country')
    if args.get('city'):
        filters['city'] = args.get('city')
    if args.get('skill'):
        filters['skill'] = args.get('skill')
    if args.get('education_level'):
        filters['education_level'] = args.get('education_level')
    if args.get('search'):
        filters['search'] = args.get('search')
    if args.get('min_experience'):
        try:
            filters['min_experience'] = int(args.get('min_experience'))
        except Exception:
            pass
    if args.get('has_driver_license'):
        filters['has_driver_license'] = args.get('has_driver_license')
    return filters


def _candidate_passes_filters(candidate: dict, filters: dict) -> bool:
    if not filters:
        return True

    if filters.get('min_score') is not None:
        if float(candidate.get('Final Score (%)', 0) or 0) < float(filters['min_score']):
            return False
    if filters.get('max_score') is not None:
        if float(candidate.get('Final Score (%)', 0) or 0) > float(filters['max_score']):
            return False
    if filters.get('gender'):
        if str(candidate.get('Gender', '') or '').strip().lower() != str(filters['gender']).strip().lower():
            return False
    if filters.get('country'):
        if str(filters['country']).strip().lower() not in str(candidate.get('Country', '') or '').strip().lower():
            return False
    if filters.get('city'):
        if str(filters['city']).strip().lower() not in str(candidate.get('City', '') or '').strip().lower():
            return False
    if filters.get('education_level'):
        if str(filters['education_level']).strip().lower() not in str(candidate.get('Education Level', '') or '').strip().lower():
            return False
    if filters.get('min_experience') is not None:
        candidate_experience = pd.to_numeric(candidate.get('Years of Experience', 0), errors='coerce')
        if pd.isna(candidate_experience):
            candidate_experience = 0
        if float(candidate_experience) < float(filters['min_experience']):
            return False
    if filters.get('skill'):
        skill_value = str(filters['skill']).strip().lower()
        skills_text = str(candidate.get('Skills', '') or '').strip().lower()
        if skill_value not in skills_text:
            return False
    if filters.get('search'):
        search_value = str(filters['search']).strip().lower()
        full_name = f"{candidate.get('First Name', '')} {candidate.get('Last Name', '')}".strip().lower()
        email = str(candidate.get('Email', '') or '').strip().lower()
        if search_value not in full_name and search_value not in email:
            return False
    if filters.get('has_driver_license'):
        license_value = str(filters['has_driver_license']).strip().lower()
        raw_license = candidate.get("Has Driver's License", candidate.get('Has Driver License', ''))
        normalized = str(raw_license).strip().lower()
        has_license = normalized in {'1', 'true', 'yes'}
        if license_value in {'true', '1', 'yes'} and not has_license:
            return False
        if license_value in {'false', '0', 'no'} and has_license:
            return False

    return True


def build_active_job_report(job: dict, filters: dict = None, top_n: int = 50) -> dict:
    def safe_value(value):
        if pd.isna(value):
            return ''
        return value

    if not job or not job.get('Job ID'):
        return {
            'success': True,
            'job': {},
            'totals': {
                'ranked_candidates': 0,
                'qualified_candidates': 0,
                'excellent_candidates': 0,
                'average_match_score': 0,
                'average_coverage_score': 0,
                'qualified_pct': 0,
                'excellent_pct': 0,
            },
            'bands': {'Excellent': 0, 'Good': 0, 'Moderate': 0, 'Weak': 0, 'Poor': 0},
            'matched_keywords': [],
            'missing_keywords': [],
            'top_candidates': [],
            'requirement_keywords': [],
        }

    df = excel_manager._load_dataframe()
    if df.empty:
        return {
            'success': True,
            'job': job,
            'totals': {
                'ranked_candidates': 0,
                'qualified_candidates': 0,
                'excellent_candidates': 0,
                'average_match_score': 0,
                'average_coverage_score': 0,
                'qualified_pct': 0,
                'excellent_pct': 0,
            },
            'bands': {'Excellent': 0, 'Good': 0, 'Moderate': 0, 'Weak': 0, 'Poor': 0},
            'matched_keywords': [],
            'missing_keywords': [],
            'top_candidates': [],
            'requirement_keywords': [],
        }

    if df.empty:
        return {
            'success': True,
            'job': job,
            'totals': {
                'ranked_candidates': 0,
                'qualified_candidates': 0,
                'excellent_candidates': 0,
                'average_match_score': 0,
                'average_coverage_score': 0,
                'qualified_pct': 0,
                'excellent_pct': 0,
            },
            'bands': {'Excellent': 0, 'Good': 0, 'Moderate': 0, 'Weak': 0, 'Poor': 0},
            'matched_keywords': [],
            'missing_keywords': [],
            'top_candidates': [],
            'requirement_keywords': [],
        }

    job_keywords = excel_manager._job_keywords(job)
    title_terms = set(re.findall(r'\b[a-zA-Z][a-zA-Z0-9+.#/-]{2,}\b', str(job.get('Job Title', '')).lower()))
    title_terms = {
        term for term in title_terms
        if term not in {'the', 'and', 'for', 'with', 'from', 'that', 'this', 'have', 'has', 'was', 'were', 'are', 'your', 'you'}
    }

    ranked_candidates = []
    all_candidate_terms = set()
    band_counts = {'Excellent': 0, 'Good': 0, 'Moderate': 0, 'Weak': 0, 'Poor': 0}

    for _, row in df.iterrows():
        candidate_terms = excel_manager._candidate_match_terms(row)
        all_candidate_terms.update(candidate_terms)

        keyword_hits = candidate_terms & job_keywords
        keyword_score = (len(keyword_hits) / max(len(job_keywords), 1)) * 100 if job_keywords else 0
        title_score = (len(candidate_terms & title_terms) / max(len(title_terms), 1)) * 100 if title_terms else 0
        match_score = round((keyword_score * 0.75) + (title_score * 0.25), 2)
        final_score_value = pd.to_numeric(row.get('Final Score (%)', 0), errors='coerce')
        final_score = float(final_score_value) if pd.notna(final_score_value) else 0

        if match_score >= 85:
            band = 'Excellent'
        elif match_score >= 70:
            band = 'Good'
        elif match_score >= 55:
            band = 'Moderate'
        elif match_score >= 40:
            band = 'Weak'
        else:
            band = 'Poor'

        band_counts[band] += 1
        ranked_candidates.append({
            'Applicant ID': safe_value(row.get('Applicant ID', '')),
            'Candidate Key': safe_value(row.get('Candidate Key', '')),
            'First Name': safe_value(row.get('First Name', '')),
            'Last Name': safe_value(row.get('Last Name', '')),
            'Name': f"{row.get('First Name', '')} {row.get('Last Name', '')}".strip(),
            'Email': safe_value(row.get('Email', '')),
            'Phone': safe_value(row.get('Phone', '')),
            'Gender': safe_value(row.get('Gender', '')),
            'Country': safe_value(row.get('Country', '')),
            'City': safe_value(row.get('City', '')),
            'Education Level': safe_value(row.get('Education Level', '')),
            'Years of Experience': safe_value(row.get('Years of Experience', '')),
            'Current Role': safe_value(row.get('Current Role', '')),
            'Skills': safe_value(row.get('Skills', '')),
            'Has Driver\'s License': safe_value(row.get('Has Driver\'s License', '')),
            'CV File Name': safe_value(row.get('CV File Name', '')),
            'CV Available': bool(_resolve_uploaded_file(row.get('CV File Name', ''), candidate_hint={
                'First Name': row.get('First Name', ''),
                'Last Name': row.get('Last Name', ''),
                'Email': row.get('Email', ''),
                'Phone': row.get('Phone', ''),
            })[0]),
            'Final Score (%)': round(final_score, 2),
            'Match Score (%)': match_score,
            'Coverage (%)': round(keyword_score, 2),
            'Band': band,
            'Applied Job ID': safe_value(row.get('Applied Job ID', '')),
            'Applied Job Title': safe_value(row.get('Applied Job Title', '')),
        })

    ranked_candidates.sort(key=lambda item: (item['Match Score (%)'], item['Final Score (%)']), reverse=True)

    total = len(ranked_candidates)
    qualified_candidates = sum(1 for item in ranked_candidates if item['Match Score (%)'] >= 70)
    excellent_candidates = sum(1 for item in ranked_candidates if item['Match Score (%)'] >= 85)
    avg_match = round(sum(item['Match Score (%)'] for item in ranked_candidates) / total, 2) if total else 0
    avg_coverage = round(sum(item['Coverage (%)'] for item in ranked_candidates) / total, 2) if total else 0

    top_limit = max(int(top_n or 50), 1)
    visible_candidates = ranked_candidates
    if filters:
        visible_candidates = [candidate for candidate in ranked_candidates if _candidate_passes_filters(candidate, filters)]
    visible_candidates = visible_candidates[:top_limit]

    matched_keywords = sorted(job_keywords & all_candidate_terms)
    missing_keywords = sorted(job_keywords - all_candidate_terms)

    return {
        'success': True,
        'job': job,
        'totals': {
            'ranked_candidates': total,
            'qualified_candidates': qualified_candidates,
            'excellent_candidates': excellent_candidates,
            'average_match_score': avg_match,
            'average_coverage_score': avg_coverage,
            'qualified_pct': round((qualified_candidates / max(total, 1)) * 100, 2),
            'excellent_pct': round((excellent_candidates / max(total, 1)) * 100, 2),
        },
        'bands': band_counts,
        'matched_keywords': matched_keywords[:50],
        'missing_keywords': missing_keywords[:50],
        'top_candidates': visible_candidates,
        'requirement_keywords': sorted(job_keywords)[:50],
    }

def allowed_file(filename: str) -> bool:
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def process_uploaded_file(file_obj, job_id: str = ''):
    """Process one uploaded CV and store parsed results in Excel."""
    if not file_obj or file_obj.filename == '':
        return {'success': False, 'status': 400, 'error': 'No file selected'}

    if not allowed_file(file_obj.filename):
        return {
            'success': False,
            'status': 400,
            'error': f"Invalid file type for {file_obj.filename}. Only PDF and DOCX are allowed."
        }

    filename = secure_filename(file_obj.filename)
    file_path = os.path.join(UPLOAD_FOLDER, filename)
    file_obj.save(file_path)

    should_delete_file = False
    try:
        candidate_data = cv_parser.parse_cv(file_path)
        if not candidate_data:
            should_delete_file = True
            return {'success': False, 'status': 400, 'error': f'Could not parse {filename}'}

        if not candidate_data.get('first_name') and not candidate_data.get('last_name') and not candidate_data.get('email'):
            stem = os.path.splitext(filename)[0]
            fallback_parts = [part for part in re.findall(r'[A-Za-z][A-Za-z\-]{1,30}', stem) if part.lower() not in {'resume', 'cv', 'cvs', 'file', 'doc', 'pdf'}]
            if fallback_parts:
                candidate_data['first_name'] = fallback_parts[0]
                if len(fallback_parts) > 1:
                    candidate_data['last_name'] = fallback_parts[1]

        if not (candidate_data.get('email') or candidate_data.get('first_name') or candidate_data.get('last_name') or candidate_data.get('phone')):
            should_delete_file = True
            return {
                'success': False,
                'status': 400,
                'error': f'Could not identify a name or email in {filename}. A CV needs at least one identifier.'
            }

        if excel_manager.candidate_exists(candidate_data):
            should_delete_file = True
            display_name = f"{candidate_data.get('first_name', '')} {candidate_data.get('last_name', '')}".strip()
            identifier = candidate_data.get('email') or display_name or candidate_data.get('phone', '')
            return {
                'success': False,
                'status': 409,
                'duplicate': True,
                'error': f"Candidate {identifier} already exists"
            }

        # Business rule: when a job is active, all uploads are applications for that active job.
        active_job = jobs_manager.get_active_job() or {}
        job = active_job if active_job.get('Job ID') else get_effective_job(job_id)
        # Compute scores with awareness of the job when available
        scores = scoring_system.get_score_breakdown(candidate_data, job=job)
        assignment = build_job_assignment(candidate_data, job)
        success = excel_manager.add_candidate(candidate_data, scores, filename, assignment)

        if not success:
            should_delete_file = True
            return {'success': False, 'status': 500, 'error': f'Failed to add candidate from {filename}'}

        if blob_storage_client.enabled:
            try:
                content_type, _ = mimetypes.guess_type(file_path)
                blob_storage_client.upload_file(
                    f'uploads/{filename}',
                    file_path,
                    content_type=content_type or 'application/octet-stream'
                )
            except Exception as exc:
                print(f"Warning: could not sync {filename} to blob storage: {exc}")

        return {
            'success': True,
            'status': 200,
            'candidate': {
                'id': candidate_data.get('email') or f"{candidate_data.get('first_name', '')} {candidate_data.get('last_name', '')}".strip() or candidate_data.get('phone', ''),
                'name': f"{candidate_data.get('first_name', '')} {candidate_data.get('last_name', '')}".strip(),
                'email': candidate_data.get('email', ''),
                'score': scores.get('final_score', 0),
                'file_name': filename,
                'applied_job_id': assignment.get('job_id', ''),
                'applied_job_title': assignment.get('job_title', ''),
                'match_score': assignment.get('match_score', 0)
            }
        }
    finally:
        if should_delete_file and os.path.exists(file_path):
            os.remove(file_path)

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/jobs', methods=['GET'])
def get_jobs():
    try:
        jobs = jobs_manager.get_all_jobs()
        return jsonify({'success': True, 'jobs': jobs, 'total': len(jobs)}), 200
    except Exception as e:
        print(f"Error in get_jobs: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/jobs', methods=['POST'])
def create_job():
    try:
        payload = request.get_json(silent=True) or {}

        required_fields = [
            'Job Title', 'Department / Category', 'Job Type', 'Work Mode', 'Location',
            'Job Description', 'Key Responsibilities', 'Requirements / Qualifications',
            'Experience Level', 'Application Deadline'
        ]
        missing_fields = [field for field in required_fields if not str(payload.get(field, '')).strip()]
        if missing_fields:
            return jsonify({
                'error': 'Missing required fields',
                'missing_fields': missing_fields
            }), 400

        result = jobs_manager.add_job(payload)
        if result.get('success'):
            job = result.get('job', {})
            matched_count = excel_manager.assign_candidates_to_job(job)
            return jsonify({
                'success': True,
                'message': 'Job posted successfully',
                'job': job,
                'matched_candidates': matched_count
            }), 201

        return jsonify({'error': result.get('error', 'Failed to create job')}), 500
    except Exception as e:
        print(f"Error in create_job: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/jobs/<job_id>', methods=['GET'])
def get_job(job_id):
    try:
        job = jobs_manager.get_job_by_id(job_id)
        if job:
            return jsonify({'success': True, 'job': job}), 200
        return jsonify({'error': 'Job not found'}), 404
    except Exception as e:
        print(f"Error in get_job: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/jobs/<job_id>', methods=['DELETE'])
def delete_job(job_id):
    try:
        result = jobs_manager.delete_job(job_id)
        if not result.get('success'):
            return jsonify({'error': result.get('error', 'Failed to delete job')}), 400

        deleted_job = result.get('job', {})
        deleted_active = bool(result.get('was_active'))

        if deleted_active:
            remaining_jobs = jobs_manager.get_all_jobs()
            if remaining_jobs:
                next_job_id = remaining_jobs[0].get('Job ID', '')
                if next_job_id:
                    activation_result = jobs_manager.set_active_job(next_job_id)
                    if activation_result.get('success'):
                        excel_manager.assign_candidates_to_job(activation_result.get('job', {}))

        return jsonify({
            'success': True,
            'message': 'Job deleted successfully',
            'job': deleted_job,
            'deleted_active': deleted_active,
        }), 200
    except Exception as e:
        print(f"Error in delete_job: {e}")
        return jsonify({'error': str(e)}), 500





@app.route('/api/jobs/<job_id>/activate', methods=['POST'])
def activate_job(job_id):
    try:
        result = jobs_manager.set_active_job(job_id)
        if not result.get('success'):
            return jsonify({'error': result.get('error', 'Failed to activate job')}), 400

        matched_count = excel_manager.assign_candidates_to_job(result.get('job', {}))
        return jsonify({
            'success': True,
            'message': 'Job activated successfully',
            'job': result.get('job', {}),
            'matched_candidates': matched_count
        }), 200
    except Exception as e:
        print(f"Error in activate_job: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/jobs/active', methods=['GET'])
def get_active_job():
    try:
        job = jobs_manager.get_active_job()
        if not job:
            return jsonify({'success': True, 'job': {}}), 200
        return jsonify({'success': True, 'job': job}), 200
    except Exception as e:
        print(f"Error in get_active_job: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/jobs/active/matches', methods=['GET'])
def get_active_job_matches():
    try:
        job = jobs_manager.get_active_job()
        if not job:
            return jsonify({'success': True, 'job': {}, 'candidates': [], 'total': 0}), 200

        # Allow optional filtering parameters (same as /api/candidates) to be passed
        # so the Active Job matches endpoint can return server-filtered results.
        def _parse_filters(args):
            f = {}
            if args.get('min_score'):
                try:
                    f['min_score'] = float(args.get('min_score'))
                except Exception:
                    pass
            if args.get('max_score'):
                try:
                    f['max_score'] = float(args.get('max_score'))
                except Exception:
                    pass
            if args.get('gender'):
                f['gender'] = args.get('gender')
            if args.get('country'):
                f['country'] = args.get('country')
            if args.get('city'):
                f['city'] = args.get('city')
            if args.get('skill'):
                f['skill'] = args.get('skill')
            if args.get('education_level'):
                f['education_level'] = args.get('education_level')
            if args.get('search'):
                f['search'] = args.get('search')
            if args.get('min_experience'):
                try:
                    f['min_experience'] = int(args.get('min_experience'))
                except Exception:
                    pass
            if args.get('has_driver_license'):
                f['has_driver_license'] = args.get('has_driver_license')
            if args.get('applied_job_title'):
                f['applied_job_title'] = args.get('applied_job_title')
            # always filter to the active job id
            f['applied_job_id'] = job.get('Job ID', '')
            return f

        filters = _parse_filters(request.args)

        # Some datasets may have candidates linked to jobs only by title
        # (Applied Job ID empty). If no candidates exist for the active
        # job by ID, fall back to filtering by the job title so users
        # still see relevant matches.
        job_id = str(job.get('Job ID', '') or '').strip()
        has_by_id = False
        try:
            all_candidates = excel_manager.get_all_candidates()
            for c in all_candidates:
                if str(c.get('Applied Job ID', '') or '').strip() == job_id and job_id:
                    has_by_id = True
                    break
        except Exception:
            has_by_id = False

        if not has_by_id and job.get('Job Title'):
            # prefer title-based match when IDs are absent
            filters.pop('applied_job_id', None)
            filters['applied_job_title'] = job.get('Job Title')

        candidates = excel_manager.filter_candidates(filters)
        candidates = sorted(candidates, key=lambda c: float(c.get('Match Score (%)', 0) or 0), reverse=True)

        return jsonify({
            'success': True,
            'job': job,
            'candidates': candidates,
            'total': len(candidates)
        }), 200
    except Exception as e:
        print(f"Error in get_active_job_matches: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/jobs/active/matches/download', methods=['GET'])
def download_active_job_matches():
    """Download an Excel file for candidates assigned to the current active job."""
    try:
        job = jobs_manager.get_active_job()
        if not job:
            return jsonify({'error': 'No active job selected'}), 400

        candidates = excel_manager.filter_candidates({'applied_job_id': job.get('Job ID', '')})
        if not candidates:
            return jsonify({'error': 'No applications found for the active job'}), 404

        df = pd.DataFrame(candidates)
        if 'Match Score (%)' in df.columns:
            df['Match Score (%)'] = pd.to_numeric(df['Match Score (%)'], errors='coerce').fillna(0)
            df = df.sort_values(by='Match Score (%)', ascending=False)

        preferred_cols = [
            'Applicant ID', 'First Name', 'Last Name', 'Email', 'Phone',
            'Education Level', 'Years of Experience', 'Current Role', 'Skills',
            'Final Score (%)', 'Applied Job ID', 'Applied Job Title',
            'Match Score (%)', 'Match Source', 'Matched On', 'Upload Date', 'CV File Name'
        ]
        export_cols = [col for col in preferred_cols if col in df.columns]
        if export_cols:
            df = df[export_cols]

        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            sheet_name = 'Active Job Applications'
            df.to_excel(writer, index=False, sheet_name=sheet_name)

        output.seek(0)
        safe_job_title = re.sub(r'[^a-zA-Z0-9_-]+', '_', str(job.get('Job Title', 'active_job')).strip()).strip('_')
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"active_job_{safe_job_title or 'applications'}_{timestamp}.xlsx"

        return send_file(
            output,
            as_attachment=True,
            download_name=filename,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
    except Exception as e:
        print(f"Error in download_active_job_matches: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/jobs/active/report', methods=['GET'])
def get_active_job_report():
    try:
        job = jobs_manager.get_active_job()
        filters = _parse_active_job_filters(request.args)
        top_n = request.args.get('top_n', 50)
        try:
            top_n = int(top_n)
        except Exception:
            top_n = 50
        report = build_active_job_report(job, filters=filters, top_n=top_n)
        return jsonify(report), 200
    except Exception as e:
        print(f"Error in get_active_job_report: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/upload-cv', methods=['POST'])
def upload_cv():
    """Handle CV upload and parsing"""
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400
        
        result = process_uploaded_file(request.files['file'], request.form.get('job_id', '').strip())

        if result.get('success'):
            return jsonify({
                'success': True,
                'message': 'CV uploaded and processed successfully',
                'candidate': result.get('candidate', {})
            }), 200

        payload = {'error': result.get('error', 'Unknown error')}
        if result.get('duplicate'):
            payload['duplicate'] = True
        return jsonify(payload), result.get('status', 500)
            
    except Exception as e:
        print(f"Error in upload_cv: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/upload-cvs', methods=['POST'])
def upload_cvs():
    """Handle batch CV uploads and return per-file outcomes."""
    try:
        files = request.files.getlist('files')
        if not files:
            return jsonify({'error': 'No files provided'}), 400

        job_id = request.form.get('job_id', '').strip()
        results = []
        success_count = 0
        duplicate_count = 0
        failed_count = 0

        for file_obj in files:
            result = process_uploaded_file(file_obj, job_id)
            if result.get('success'):
                success_count += 1
                results.append({'status': 'uploaded', 'candidate': result.get('candidate', {})})
            elif result.get('duplicate'):
                duplicate_count += 1
                results.append({'status': 'duplicate', 'error': result.get('error', '')})
            else:
                failed_count += 1
                results.append({'status': 'failed', 'error': result.get('error', '')})

        return jsonify({
            'success': True,
            'summary': {
                'total_files': len(files),
                'uploaded': success_count,
                'duplicates': duplicate_count,
                'failed': failed_count
            },
            'results': results
        }), 200
    except Exception as e:
        print(f"Error in upload_cvs: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/dashboard', methods=['GET'])
def get_dashboard():
    """Get dashboard statistics"""
    try:
        stats = excel_manager.get_statistics()
        top_candidates = excel_manager.get_top_candidates(10)
        
        return jsonify({
            'success': True,
            'stats': stats,
            'top_candidates': top_candidates
        }), 200
    except Exception as e:
        print(f"Error in get_dashboard: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/candidates', methods=['GET'])
def get_candidates():
    """Get all candidates with optional filtering"""
    try:
        # Get query parameters
        filters = {}
        
        if request.args.get('min_score'):
            filters['min_score'] = float(request.args.get('min_score'))
        if request.args.get('max_score'):
            filters['max_score'] = float(request.args.get('max_score'))
        if request.args.get('gender'):
            filters['gender'] = request.args.get('gender')
        if request.args.get('country'):
            filters['country'] = request.args.get('country')
        if request.args.get('city'):
            filters['city'] = request.args.get('city')
        if request.args.get('skill'):
            filters['skill'] = request.args.get('skill')
        if request.args.get('education_level'):
            filters['education_level'] = request.args.get('education_level')
        if request.args.get('search'):
            filters['search'] = request.args.get('search')
        if request.args.get('min_experience'):
            filters['min_experience'] = int(request.args.get('min_experience'))
        if request.args.get('has_driver_license'):
            filters['has_driver_license'] = request.args.get('has_driver_license')
        if request.args.get('applied_job_id'):
            filters['applied_job_id'] = request.args.get('applied_job_id')
        if request.args.get('applied_job_title'):
            filters['applied_job_title'] = request.args.get('applied_job_title')

        candidates = excel_manager.get_all_candidates() if not filters else excel_manager.filter_candidates(filters)
        candidates = [_with_cv_availability(candidate) for candidate in candidates]
        
        return jsonify({
            'success': True,
            'candidates': candidates,
            'total': len(candidates)
        }), 200
    except Exception as e:
        print(f"Error in get_candidates: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/candidate/<path:identifier>', methods=['GET'])
def get_candidate_detail(identifier):
    """Get detailed information about a specific candidate"""
    try:
        candidate = excel_manager.get_candidate_by_email(identifier)
        
        if candidate:
            return jsonify({
                'success': True,
                'candidate': candidate
            }), 200
        else:
            return jsonify({'error': 'Candidate not found'}), 404
    except Exception as e:
        print(f"Error in get_candidate_detail: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/candidate/<path:identifier>', methods=['DELETE'])
def delete_candidate(identifier):
    """Delete a candidate"""
    try:
        success = excel_manager.delete_candidate(identifier)
        
        if success:
            return jsonify({
                'success': True,
                'message': 'Candidate deleted successfully'
            }), 200
        else:
            return jsonify({'error': 'Failed to delete candidate'}), 500
    except Exception as e:
        print(f"Error in delete_candidate: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/export', methods=['POST'])
def export_data():
    """Export filtered candidates to Excel"""
    try:
        data = request.json.get('data', [])
        
        if not data:
            return jsonify({'error': 'No data to export'}), 400
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'export_{timestamp}'
        
        success = excel_manager.export_to_excel(data, filename)
        
        if success:
            return jsonify({
                'success': True,
                'message': f'Data exported to {filename}.xlsx'
            }), 200
        else:
            return jsonify({'error': 'Failed to export data'}), 500
    except Exception as e:
        print(f"Error in export_data: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/export-download', methods=['POST'])
def export_and_download():
    """Export filtered candidates and stream the Excel file directly to browser."""
    try:
        payload = request.get_json(silent=True) or {}
        data = payload.get('data', [])

        if not data:
            return jsonify({'error': 'No data to export'}), 400

        df = pd.DataFrame(data)
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Filtered Applicants')
        output.seek(0)

        filename = f"filtered_candidates_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        return send_file(
            output,
            as_attachment=True,
            download_name=filename,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
    except Exception as e:
        print(f"Error in export_and_download: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/download-excel', methods=['GET'])
def download_excel():
    """Download the main applicants Excel file"""
    try:
        excel_path = APPLICANTS_FILE
        
        if os.path.exists(excel_path):
            return send_file(excel_path, as_attachment=True, 
                           download_name='applicants.xlsx')
        else:
            return jsonify({'error': 'Excel file not found'}), 404
    except Exception as e:
        print(f"Error in download_excel: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/download-upload/<path:filename>', methods=['GET'], endpoint='download_upload_route')
def download_upload(filename):
    """Serve an uploaded CV file by filename from the uploads folder.

    For commonly viewable types (PDF, images, text/html) set Content-Disposition
    to inline so the browser opens them in a new tab. For other types force
    download as an attachment.
    """
    try:
        file_path, safe_name = _resolve_uploaded_file(filename)
        if not file_path:
            return jsonify({'error': 'File not found'}), 404
        return _serve_uploaded_file(file_path, safe_name)
    except Exception as e:
        print(f"Error in download_upload: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/download-candidate-cv/<path:identifier>', methods=['GET'], endpoint='download_candidate_cv_route')
def download_candidate_cv(identifier):
    """Resolve and serve a candidate CV from a candidate identifier or email."""
    try:
        candidate = excel_manager.get_candidate_by_email(identifier) or {}
        file_reference = candidate.get('CV File Name', '') or identifier
        file_path, safe_name = _resolve_uploaded_file(file_reference, candidate_hint=candidate)
        if not file_path:
            return jsonify({'error': 'File not found'}), 404
        return _serve_uploaded_file(file_path, safe_name)
    except Exception as e:
        print(f"Error in download_candidate_cv: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/debug/storage', methods=['GET'])
def debug_storage():
    """Lightweight diagnostics for deployed storage state."""
    try:
        stats = excel_manager.get_statistics()
        jobs = jobs_manager.get_all_jobs()
        return jsonify({
            'success': True,
            'paths': {
                'storage_root': STORAGE_ROOT,
                'upload_folder': UPLOAD_FOLDER,
                'applicants_file': APPLICANTS_FILE,
                'jobs_file': JOBS_FILE,
            },
            'exists': {
                'uploads_dir': os.path.exists(UPLOAD_FOLDER),
                'applicants': os.path.exists(APPLICANTS_FILE),
                'jobs': os.path.exists(JOBS_FILE),
            },
            'counts': {
                'candidates': int(stats.get('total_applicants', 0) or 0),
                'jobs': len(jobs)
            }
        }), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/debug/candidates', methods=['GET'])
def debug_candidates():
    """Return a small candidate payload to validate JSON serialization end-to-end."""
    try:
        candidates = excel_manager.get_all_candidates()
        return jsonify({
            'success': True,
            'count': len(candidates),
            'sample': candidates[:3]
        }), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/admin/reset-system', methods=['POST'])
def reset_system_data():
    try:
        _clear_directory_contents(UPLOAD_FOLDER)

        # Recreate empty data stores
        if os.path.exists(APPLICANTS_FILE):
            os.remove(APPLICANTS_FILE)
        if os.path.exists(JOBS_FILE):
            os.remove(JOBS_FILE)

        excel_manager.ensure_file_exists()
        jobs_manager.ensure_file_exists()

        return jsonify({
            'success': True,
            'message': 'All system data has been reset successfully'
        }), 200
    except Exception as e:
        print(f"Error in reset_system_data: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/debug/candidate-count', methods=['GET'])
def debug_candidate_count():
    """Detailed candidate count breakdown to verify all candidates are being counted."""
    try:
        import pandas as pd
        # Raw load directly
        df = pd.read_excel(APPLICANTS_FILE) if os.path.exists(APPLICANTS_FILE) else pd.DataFrame()
        raw_count = len(df)
        
        # Via excel manager
        all_candidates = excel_manager.get_all_candidates()
        manager_count = len(all_candidates)
        
        # Via statistics
        stats = excel_manager.get_statistics()
        stats_count = stats.get('total_applicants', 0)
        
        # Count by score ranges
        if 'Final Score (%)' in df.columns:
            df['Final Score (%)'] = pd.to_numeric(df['Final Score (%)'], errors='coerce').fillna(0)
            above_80 = int((df['Final Score (%)'] >= 80).sum())
            below_80 = int((df['Final Score (%)'] < 80).sum())
        else:
            above_80 = 0
            below_80 = raw_count
        
        return jsonify({
            'success': True,
            'counts': {
                'raw_excel_rows': raw_count,
                'manager_get_all': manager_count,
                'statistics_total': stats_count,
                'above_80_percent': above_80,
                'below_80_percent': below_80
            }
        }), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.errorhandler(413)
def request_entity_too_large(error):
    return jsonify({'error': 'Upload too large. Maximum batch size is 300MB (supports ~20 CVs per upload)'}), 413

@app.route('/admin')
def admin_page():
    """Serve the admin skills management page"""
    # Render via Jinja so `url_for` works inside the template
    try:
        return render_template('admin.html')
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/admin/master-skills', methods=['GET'])
def get_master_skills():
    """Get current master skills list"""
    try:
        skills_path = os.path.join(DATA_FOLDER, 'master_skills.json')
        if os.path.exists(skills_path):
            with open(skills_path, 'r', encoding='utf-8') as f:
                skills = json.load(f)
        else:
            # Fallback to parser's default
            skills = cv_parser.common_skills + getattr(cv_parser, 'master_skills', [])
        
        return jsonify({
            'success': True,
            'skills': sorted(list(set(skills)))  # Remove duplicates and sort
        }), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/admin/master-skills', methods=['POST'])
def save_master_skills():
    """Save updated master skills list"""
    try:
        data = request.get_json()
        skills = data.get('skills', [])
        
        if not isinstance(skills, list) or not skills:
            return jsonify({'success': False, 'error': 'Skills must be a non-empty list'}), 400
        
        # Validate each skill
        skills = [s.strip() for s in skills if isinstance(s, str) and s.strip()]
        skills = sorted(list(set(skills)))  # Remove duplicates and sort
        
        # Save to file
        skills_path = os.path.join(DATA_FOLDER, 'master_skills.json')
        with open(skills_path, 'w', encoding='utf-8') as f:
            json.dump(skills, f, indent=2, ensure_ascii=False)
        
        # Reload parser with new skills
        cv_parser.master_skills = skills
        
        return jsonify({
            'success': True,
            'message': f'Saved {len(skills)} skills',
            'skills': skills
        }), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/admin/master-skills/reset', methods=['POST'])
def reset_master_skills():
    """Reset to default master skills"""
    try:
        # Create default skills file
        default_skills = [
            'Python','Java','C','C++','C#','Go','Rust','Ruby','Perl','PHP','Swift','Kotlin','Objective-C',
            'JavaScript','TypeScript','Node.js','React','Angular','Vue','HTML','CSS',
            'SQL','PostgreSQL','MySQL','MongoDB','Redis',
            'AWS','Azure','GCP','Docker','Kubernetes',
            'DevOps','Linux','Git','Jenkins','GitHub Actions',
            'Machine Learning','Data Science','TensorFlow','PyTorch',
            'Agile','Scrum','Project Management'
        ]
        
        skills_path = os.path.join(DATA_FOLDER, 'master_skills.json')
        with open(skills_path, 'w', encoding='utf-8') as f:
            json.dump(sorted(default_skills), f, indent=2, ensure_ascii=False)
        
        cv_parser.master_skills = sorted(default_skills)
        
        return jsonify({
            'success': True,
            'message': 'Reset to default skills',
            'skills': sorted(default_skills)
        }), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=5000)
