import sys
from pathlib import Path
root = Path(r"c:\Users\TafaraChitiyo-I-\Documents\CV Analysis")
sys.path.insert(0, str(root / "cv_analyzer"))
try:
    from app import build_active_job_report, jobs_manager
    job = jobs_manager.get_active_job() or {}
    report = build_active_job_report(job, top_n=40)
    candidates = report.get("top_candidates", [])

    print(f"JOB_INFO: {job.get('Job ID')} | {job.get('Job Title')}")
    print(f"COUNT: {len(candidates)}")

    if candidates:
        first_name = candidates[0].get("Name", "")
        fragment = first_name[:3] if len(first_name) >= 3 else first_name
        
        filtered_count = len([c for c in candidates if fragment.lower() in str(c.get("Name", "")).lower()])
        
        print(f"FRAGMENT: {fragment}")
        print(f"FILTERED_COUNT: {filtered_count}")
        print(f"NON_EMPTY: {len(candidates) > 0}")
    else:
        print("NON_EMPTY: False - NO CANDIDATES FOUND")
except Exception as e:
    print(f"ERROR: {e}")
