import sys
from pathlib import Path
root = Path(r"C:\Users\TafaraChitiyo-I-\Documents\CV Analysis")
sys.path.insert(0, str(root / "cv_analyzer"))
from app import build_active_job_report, jobs_manager
job = jobs_manager.get_active_job() or {}
report = build_active_job_report(job, top_n=40)
candidates = report.get("top_candidates", [])
print(f"JOB_INFO: {job.get('Job ID')} | {job.get('Job Title')}")
print(f"COUNT: {len(candidates)}")
if candidates:
    fn = candidates[0].get("Name", "")
    frag = fn[:3]
    edu = candidates[0].get("Education Level", "")
    name_count = len([c for c in candidates if frag.lower() in str(c.get("Name", "")).lower()])
    edu_count = len([c for c in candidates if str(c.get("Education Level", "")) == edu])
    print(f"FRAG: {frag} | NAME_FILTER_COUNT: {name_count}")
    print(f"EDU: {edu} | EDU_FILTER_COUNT: {edu_count}")
    print(f"NON_EMPTY: {len(candidates) > 0}")
else:
    print("NON_EMPTY: False")
