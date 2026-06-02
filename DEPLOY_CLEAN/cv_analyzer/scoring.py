import re
from typing import Dict, List, Optional

try:
    from sentence_transformers import SentenceTransformer
    SENTENCE_TRANSFORMERS_AVAILABLE = True
except Exception:
    SentenceTransformer = None
    SENTENCE_TRANSFORMERS_AVAILABLE = False


class ScoringSystem:
    """Implements an extended scoring engine matching the 8-dimension framework.

    The class preserves backward-compatible keys produced by `get_score_breakdown`.
    """
    WEIGHT_PROFILES = {
        'Tech/Engineering': {
            'Relevance': 0.18, 'Experience Quality': 0.22, 'Skills Match': 0.28,
            'Education & Creds': 0.07, 'Presentation': 0.07, 'Career Trajectory': 0.08,
            'Achievements': 0.07, 'Culture & Soft': 0.03
        },
        'Sales/BD': {
            'Relevance': 0.18, 'Experience Quality': 0.20, 'Skills Match': 0.15,
            'Education & Creds': 0.08, 'Presentation': 0.10, 'Career Trajectory': 0.12,
            'Achievements': 0.14, 'Culture & Soft': 0.03
        },
        'Creative': {
            'Relevance': 0.15, 'Experience Quality': 0.15, 'Skills Match': 0.18,
            'Education & Creds': 0.08, 'Presentation': 0.15, 'Career Trajectory': 0.10,
            'Achievements': 0.12, 'Culture & Soft': 0.07
        },
        'Finance/Legal': {
            'Relevance': 0.20, 'Experience Quality': 0.18, 'Skills Match': 0.20,
            'Education & Creds': 0.15, 'Presentation': 0.10, 'Career Trajectory': 0.08,
            'Achievements': 0.06, 'Culture & Soft': 0.03
        },
        'Healthcare': {
            'Relevance': 0.22, 'Experience Quality': 0.18, 'Skills Match': 0.20,
            'Education & Creds': 0.18, 'Presentation': 0.07, 'Career Trajectory': 0.06,
            'Achievements': 0.06, 'Culture & Soft': 0.03
        },
        'Executive/C-Suite': {
            'Relevance': 0.20, 'Experience Quality': 0.22, 'Skills Match': 0.12,
            'Education & Creds': 0.10, 'Presentation': 0.08, 'Career Trajectory': 0.18,
            'Achievements': 0.08, 'Culture & Soft': 0.02
        },
        'Graduate/Entry': {
            'Relevance': 0.18, 'Experience Quality': 0.12, 'Skills Match': 0.20,
            'Education & Creds': 0.20, 'Presentation': 0.12, 'Career Trajectory': 0.06,
            'Achievements': 0.08, 'Culture & Soft': 0.04
        }
    }

    def __init__(self, required_skills: Optional[List[str]] = None):
        self.required_skills = required_skills or [
            'Python', 'JavaScript', 'SQL', 'Git', 'Communication',
            'Data Analysis', 'Problem Solving', 'Teamwork'
        ]
        # synonym / alias map to expand JD and CV terms for semantic matching
        self.SYNONYM_MAP = {
            'python': {'py'},
            'javascript': {'js', 'node', 'node.js', 'react', 'reactjs'},
            'ci/cd': {'cicd', 'continuous integration', 'continuous delivery'},
            'docker': {'container', 'containers'},
            'aws': {'amazon web services'},
            'git': {'version control', 'gitlab', 'github'},
            'sql': {'database', 'postgres', 'mysql', 'sqlite'},
            'html': {'css'},
            'react': {'reactjs'},
            'node.js': {'node'},
        }
        self.semantic_model = None
        if SENTENCE_TRANSFORMERS_AVAILABLE:
            try:
                self.semantic_model = SentenceTransformer('all-MiniLM-L6-v2')
            except Exception as exc:
                print(f"Warning: sentence-transformers model not loaded. Install or download model for semantic matching: {exc}")
                self.semantic_model = None

    def _safe_num(self, v) -> float:
        try:
            return float(v or 0)
        except Exception:
            return 0.0

    def _presence(self, value) -> bool:
        return bool(value and str(value).strip())

    # Dimension calculators (0-100)
    def relevance(self, candidate: Dict, job: Optional[Dict] = None) -> float:
        if not job:
            # As a proxy, measure overlap between candidate skills and common required_skills
            cand_skills = {s.lower() for s in (candidate.get('skills') or [])}
            match = sum(1 for s in self.required_skills if s.lower() in cand_skills)
            return min(100.0, (match / max(len(self.required_skills), 1)) * 100)

        # JD-based relevance: skill overlap + title similarity + industry keywords
        jd_text = ' '.join([str(job.get(k, '')) for k in ['Job Title', 'Requirements / Qualifications', 'Job Description', 'Key Responsibilities']])
        jd_terms = set(re.findall(r"\b[a-zA-Z][a-zA-Z0-9+.#/-]{2,}\b", jd_text.lower()))
        cand_terms = set(re.findall(r"\b[a-zA-Z][a-zA-Z0-9+.#/-]{2,}\b", str(candidate.get('raw_text','')).lower()))
        if not jd_terms:
            return 0.0
        exact = len(jd_terms & cand_terms)
        return round(min(100.0, (exact / len(jd_terms)) * 100), 2)

    # Helpers for semantic expansion
    def _normalize(self, term: str) -> str:
        return re.sub(r"[^a-z0-9]+", '', term.lower() or '')

    def _expand_terms(self, terms: List[str]) -> set:
        out = set()
        for t in terms or []:
            if not t:
                continue
            n = self._normalize(t)
            out.add(n)
            syns = self.SYNONYM_MAP.get(n, set())
            for s in syns:
                out.add(self._normalize(s))
        return out

    def _semantic_similarity(self, left_text: str, right_text: str) -> float:
        if not self.semantic_model:
            return 0.0

        left_text = (left_text or '').strip()
        right_text = (right_text or '').strip()
        if not left_text or not right_text:
            return 0.0

        try:
            embeddings = self.semantic_model.encode([left_text, right_text], normalize_embeddings=True)
            if len(embeddings) < 2:
                return 0.0
            left_vec, right_vec = embeddings[0], embeddings[1]
            similarity = float(sum(a * b for a, b in zip(left_vec, right_vec)))
            return max(0.0, min(1.0, similarity))
        except Exception as exc:
            print(f"Warning: semantic similarity check failed: {exc}")
            return 0.0

    def experience_quality(self, candidate: Dict) -> float:
        years = int(self._safe_num(candidate.get('experience', {}).get('years', 0)))
        entries = candidate.get('experience_entries') or []
        achievements = 0
        duties_only = 0
        for e in entries:
            ach = len(e.get('achievements') or [])
            resp = len(e.get('responsibilities') or [])
            achievements += ach
            if ach == 0 and resp > 0:
                duties_only += 1

        score = 0.0
        # base by seniority (strongly reward experience-heavy CVs)
        if years >= 20:
            score += 88
        elif years >= 10:
            score += 76
        elif years >= 5:
            score += 62
        elif years >= 3:
            score += 45
        elif years >= 1:
            score += 28
        else:
            score += 12

        # achievements still help, but they should not be required for strong scores
        score += min(40, achievements * 6)

        # reduce penalty for duties-only entries but soften impact
        score -= min(8, duties_only * 1.0)

        # progression bonus: multiple roles at same employer with promotions
        titles = [e.get('job_title','') for e in entries if e.get('job_title')]
        if len(titles) >= 2 and titles[0] and titles[-1] and titles[0] != titles[-1]:
            score += 10

        # clamp and return
        score = max(0.0, min(100.0, score))
        return round(score,2)

    def skills_match(self, candidate: Dict, job: Optional[Dict] = None) -> float:
        cand_skills = [s for s in (candidate.get('skills') or [])]
        raw_text = str(candidate.get('raw_text','')).lower()

        required = [s for s in (job.get('required_skills') if job else self.required_skills) or []]
        preferred = [s for s in (job.get('preferred_skills') if job else []) or []]

        cand_set = self._expand_terms(cand_skills + re.findall(r"\b[a-zA-Z][a-zA-Z0-9+.#/-]{2,}\b", raw_text))
        req_set = self._expand_terms(required)
        pref_set = self._expand_terms(preferred)


        score = 0.0
        # reward required matches strongly, but soften penalties for missing ones
        for r in req_set:
            if r in cand_set:
                score += 18
            else:
                score -= 1

        for p in pref_set:
            if p in cand_set:
                score += 8

        # bonus for other skills present in CV (more generous)
        extra_skills = cand_set - req_set - pref_set
        score += min(30, len(extra_skills) * 2.0)

        # Ensure CVs with detected skills never end up in the lowest tiers due to missing required skills.
        # A CV with many detected skills should score at least 20.
        if len(cand_set) > 8:
            score = max(score, 20.0)
        elif len(cand_set) > 4:
            score = max(score, 15.0)

        score = max(0.0, min(100.0, score))
        return round(score,2)

    def education_and_creds(self, candidate: Dict, job: Optional[Dict] = None) -> float:
        edu = candidate.get('education') or []
        level = (candidate.get('education_level') or '').lower()
        certs = candidate.get('certifications') or []


        score = 0.0
        # more discriminative caps for top academic credentials (slightly more generous)
        if any('phd' in (i.get('qualification','').lower()) for i in edu) or 'phd' in level:
            score += 95
        elif 'master' in level:
            score += 90
        elif 'degree' in level or any('bsc' in (i.get('qualification','').lower()) for i in edu):
            score += 80
        elif edu:
            score += 50
        else:
            score += 15

        # certification boosts (useful industry certs give meaningful uplift)
        for c in certs:
            cl = c.lower()
            if any(k in cl for k in ['aws', 'pmp', 'cfa', 'cpa', 'azure']):
                score += 15
            else:
                score += 8

        # cap at 100
        return round(min(100.0, score),2)

    def presentation_formatting(self, candidate: Dict) -> float:
        text = str(candidate.get('raw_text','') or '')
        words = len(re.findall(r'\w+', text))
        sections = candidate.get('sections') or {}

        score = 50.0
        # basic length heuristics
        if words < 150:
            score -= 15
        elif words > 2500:
            score -= 10

        # sections presence
        required_sections = ['contact','experience','education','skills']
        miss = sum(1 for s in required_sections if not sections.get(s))
        score -= miss * 8

        # simple grammar/typo approximation: count long sequences without punctuation
        long_sentences = sum(1 for s in re.split(r'[\.\n]', text) if len(s.split())>40)
        score -= min(20, long_sentences * 5)

        return round(max(0.0, min(100.0, score)),2)

    def career_trajectory(self, candidate: Dict) -> float:
        entries = candidate.get('experience_entries') or []
        years = int(self._safe_num(candidate.get('experience', {}).get('years', 0)))
        score = 50.0
        if years >= 10:
            score += 15
        elif years >=5:
            score += 8

        # promotions heuristic
        employers = [e.get('employer','').lower() for e in entries if e.get('employer')]
        if len(employers) != len(set(employers)):
            score += 10

        # job-hopping penalty
        if len(entries) >= 4 and years < 4:
            score -= 20

        return round(max(0.0, min(100.0, score)),2)

    def achievements_impact(self, candidate: Dict) -> float:
        entries = candidate.get('experience_entries') or []
        tier1 = 0
        tier2 = 0
        tier3 = 0
        for e in entries:
            for a in (e.get('achievements') or []):
                if any(ch in a for ch in ['%', '$', 'x']):
                    tier1 += 1
                elif any(word in a.lower() for word in ['improved','increased','reduced','led','delivered','achieved','boosted']):
                    tier2 += 1
                else:
                    tier3 += 1

        score = min(100.0, tier1 * 20 + tier2 * 10 + tier3 * 4)
        if score == 0:
            score = 15.0
        return round(score,2)

    def culture_and_soft(self, candidate: Dict) -> float:
        score = 50.0
        raw = str(candidate.get('raw_text','')).lower()
        boosts = 0
        if 'volunteer' in raw or 'volunteering' in raw:
            boosts += 1
        if 'lead' in raw and 'team' in raw:
            boosts += 1
        if 'open source' in raw or 'github' in raw:
            boosts +=1

        score += boosts * 6
        # penalize excessive soft-skill-only lists
        soft_only = sum(1 for word in ['communication','leadership','teamwork','motivation'] if word in raw)
        if soft_only > 8:
            score -= 10
        return round(max(0.0, min(100.0, score)),2)

    # Weight selector
    def _weights_for_job(self, job_type: str) -> Dict[str, float]:
        return self.WEIGHT_PROFILES.get(job_type, self.WEIGHT_PROFILES['Tech/Engineering'])

    def weighted_cv_quality(self, candidate: Dict, job_type: str = 'Tech/Engineering') -> float:
        w = self._weights_for_job(job_type)
        dims = {
            'Relevance': self.relevance(candidate, None),
            'Experience Quality': self.experience_quality(candidate),
            'Skills Match': self.skills_match(candidate, None),
            'Education & Creds': self.education_and_creds(candidate),
            'Presentation': self.presentation_formatting(candidate),
            'Career Trajectory': self.career_trajectory(candidate),
            'Achievements': self.achievements_impact(candidate),
            'Culture & Soft': self.culture_and_soft(candidate)
        }
        total = sum(dims[k] * w[k] for k in dims.keys())
        return round(total,2), dims

    # Job-fit calculation
    def job_fit_score(self, candidate: Dict, job: Dict, job_type: str = 'Tech/Engineering') -> Dict:
        # Keyword match score
        jd_text = ' '.join([str(job.get(k, '')) for k in ['Job Title', 'Requirements / Qualifications', 'Job Description', 'Key Responsibilities']])
        jd_terms = set(re.findall(r"\b[a-zA-Z][a-zA-Z0-9+.#/-]{2,}\b", jd_text.lower()))
        cand_terms = set(re.findall(r"\b[a-zA-Z][a-zA-Z0-9+.#/-]{2,}\b", str(candidate.get('raw_text','')).lower()))
        keyword_score = (len(jd_terms & cand_terms) / max(len(jd_terms),1)) * 100 if jd_terms else 0

        semantic_similarity = self._semantic_similarity(jd_text, str(candidate.get('raw_text', '')))
        semantic_score = round(semantic_similarity * 100, 2)

        # Weighted dimension score (use weighted_cv_quality)
        weighted, dims = self.weighted_cv_quality(candidate, job_type)

        # Gap penalties (semantic and prioritized)
        gaps = []
        gap_penalty = 0

        # Expand JD required/preferred skills semantically
        required_skills = [s for s in (job.get('required_skills') or [])]
        preferred_skills = [s for s in (job.get('preferred_skills') or [])]
        req_set = self._expand_terms(required_skills)
        pref_set = self._expand_terms(preferred_skills)

        # Required skills missing -> Critical
        for rs in req_set:
            if rs and rs not in cand_terms:
                gaps.append({'type':'Required skill absent','item':rs,'severity':'Critical'})
                gap_penalty += 18

        # Preferred skills missing -> High/Medium depending on number
        missing_pref = [p for p in pref_set if p and p not in cand_terms]
        for idx, p in enumerate(missing_pref):
            sev = 'High' if idx < 3 else 'Medium'
            gaps.append({'type':'Preferred skill absent','item':p,'severity':sev})
            gap_penalty += 6 if sev == 'High' else 3

        # Experience level check (if provided in job)
        exp_level = (job.get('Experience Level') or '').lower()
        cand_years = int(self._safe_num(candidate.get('experience', {}).get('years', 0)))
        if 'senior' in exp_level or 'mid' in exp_level or 'junior' in exp_level:
            desired = 0
            if 'senior' in exp_level:
                desired = 6
            elif 'mid' in exp_level:
                desired = 3
            elif 'junior' in exp_level:
                desired = 0
            if desired and cand_years < desired:
                gaps.append({'type':'Experience below expectation','item':f'{cand_years} years','severity':'High'})
                gap_penalty += 10

        # Education requirement heuristic
        jd_text_lower = str(job.get('Requirements / Qualifications', '')).lower()
        if any(k in jd_text_lower for k in ['master', "master's", 'msc', 'mba', 'phd']) and 'master' not in (candidate.get('education_level') or '').lower():
            gaps.append({'type':'Education level mismatch','item':candidate.get('education_level',''), 'severity':'Medium'})
            gap_penalty += 8

        gap_penalty = min(60, gap_penalty)

        job_fit = (keyword_score * 0.24) + (semantic_score * 0.26) + (weighted * 0.50) - (gap_penalty * 0.25)
        job_fit = max(0.0, min(100.0, job_fit))

        return {
            'job_fit_score': round(job_fit,2),
            'keyword_match_score': round(keyword_score,2),
            'semantic_match_score': round(semantic_score,2),
            'weighted_dimension_score': round(weighted,2),
            'gap_penalty': gap_penalty,
            'gaps': gaps,
            'dimensions': dims
        }

    # Backward-compatible breakdown
    def get_score_breakdown(self, candidate: Dict, job: Optional[Dict] = None, job_type: str = 'Tech/Engineering') -> Dict:
        # Keep original keys for compatibility
        identity = 5 if (candidate.get('first_name') or candidate.get('last_name')) else 2
        address = 5 if candidate.get('city') or candidate.get('country') else 2
        education = self.education_and_creds(candidate)
        experience = self.experience_quality(candidate)
        skills = self.skills_match(candidate, job)

        # Rebalance: give education, experience and skills 90% combined (identity/address 10%)
        # Adjusted internal distribution to favor experience slightly so strong CVs reach higher top scores.
        total_candidate_score = round(identity + address + (education / 100 * 30) + (experience / 100 * 40) + (skills / 100 * 20), 2)
        max_score = 100
        final_score = round(min(total_candidate_score, max_score), 2)

        out = {
            'identity': identity,
            'address': address,
            'education': round(education,2),
            'experience': round(experience,2),
            'skills': round(skills,2),
            'total_candidate_score': total_candidate_score,
            'max_score': max_score,
            'final_score': final_score
        }

        # Add extended report
        weighted, dims = self.weighted_cv_quality(candidate, job_type)
        out.update({'cv_quality_score': weighted, 'cv_dimensions': dims})

        if job:
            fit = self.job_fit_score(candidate, job, job_type)
            out.update({'job_fit': fit})

        return out
