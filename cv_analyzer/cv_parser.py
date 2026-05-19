import re
from datetime import datetime
from typing import Dict, List, Tuple

import pdfplumber
from docx import Document

try:
    from pyresparser import ResumeParser
    PYRES_PARSER_AVAILABLE = True
except Exception:
    PYRES_PARSER_AVAILABLE = False

try:
    import spacy
    SPACY_AVAILABLE = True
except ImportError:
    SPACY_AVAILABLE = False
    spacy = None

class CVParser:
    def __init__(self):
        if SPACY_AVAILABLE:
            try:
                self.nlp = spacy.load("en_core_web_sm")
            except Exception:
                print("Warning: spacy model not loaded. Install with: python -m spacy download en_core_web_sm")
                self.nlp = None
        else:
            print("Warning: spacy not installed. Install with: pip install spacy")
            self.nlp = None
        # PyResparser availability
        self.pyresparser_available = PYRES_PARSER_AVAILABLE
        
        self.common_skills = [
            'Python', 'Java', 'JavaScript', 'C++', 'C#', 'SQL', 'HTML', 'CSS', 'React', 'Angular',
            'Vue', 'Node.js', 'Express', 'Django', 'Flask', 'Spring', 'AWS', 'Azure', 'GCP',
            'Docker', 'Kubernetes', 'Git', 'Linux', 'Windows', 'Excel', 'Power BI', 'Tableau',
            'Machine Learning', 'Data Analysis', 'Statistics', 'Communication', 'Leadership',
            'Project Management', 'Agile', 'Scrum', 'MongoDB', 'PostgreSQL', 'MySQL', 'API',
            'REST', 'GraphQL', 'CI/CD', 'Jenkins', 'GitHub', 'Gitlab', 'Bitbucket', 'Jira',
            'Salesforce', 'SAP', 'ERP', 'CRM', 'Finance', 'Accounting', 'Marketing', 'Sales',
            'Hardware', 'Embedded Systems', 'Firmware', 'Microcontroller', 'Electronics', 'PCB',
            'PLC', 'Instrumentation', 'Networking', 'Router', 'Switch', 'TCP/IP', 'IoT',
            'RF', 'Signal Processing', 'Electrical Engineering', 'Mechatronics', 'AutoCAD', 'SolidWorks'
        ]
        # Load master skills from data/master_skills.json if available for easier maintenance
        try:
            import json, os
            skills_path = os.path.join(os.path.dirname(__file__), 'data', 'master_skills.json')
            with open(skills_path, 'r', encoding='utf-8') as f:
                self.master_skills = json.load(f)
        except Exception:
            # Fallback inline subset if file missing
            self.master_skills = ['Python', 'JavaScript', 'Java', 'C#', 'C++', 'SQL', 'AWS', 'Azure', 'Docker', 'Kubernetes']
        self.skill_aliases = {
            'js': 'JavaScript',
            'javascript': 'JavaScript',
            'py': 'Python',
            'python': 'Python',
            'node': 'Node.js',
            'nodejs': 'Node.js',
            'express': 'Node.js',
            'postgres': 'PostgreSQL',
            'postgresql': 'PostgreSQL',
            'psql': 'PostgreSQL',
            'ml': 'Machine Learning',
            'machinelearning': 'Machine Learning',
            'ai': 'Machine Learning',
            'powerbi': 'Power BI',
            'power-bi': 'Power BI',
            'gitlab': 'Gitlab',
            'github': 'GitHub',
            'githubactions': 'GitHub Actions',
            'aws': 'AWS',
            'amazon': 'AWS',
            'amazonwebservices': 'AWS',
            'gcp': 'GCP',
            'googlecloud': 'GCP',
            'azure': 'Azure',
            'k8s': 'Kubernetes',
            'docker': 'Docker'
        }
        self.countries = [
            'USA', 'United States', 'UK', 'United Kingdom', 'Canada', 'India', 'Australia',
            'Germany', 'France', 'Japan', 'Singapore', 'UAE', 'Netherlands', 'Brazil',
            'South Africa', 'Kenya', 'Nigeria', 'Ghana', 'Zimbabwe', 'Zambia', 'Botswana'
        ]
        self.region_country_map = {
            'harare': 'Zimbabwe',
            'bulawayo': 'Zimbabwe',
            'mutare': 'Zimbabwe',
            'gaborone': 'Botswana',
            'lusaka': 'Zambia',
            'nairobi': 'Kenya',
            'lagos': 'Nigeria',
            'accra': 'Ghana',
            'johannesburg': 'South Africa',
            'cape town': 'South Africa',
            'pretoria': 'South Africa'
        }
        self.institution_keywords = [
            'university', 'college', 'polytechnic', 'institute', 'school of', 'academy'
        ]
        self.section_aliases = {
            'contact & identity': 'contact',
            'contact': 'contact',
            'personal details': 'contact',
            'profile': 'summary',
            'professional summary': 'summary',
            'summary': 'summary',
            'objective': 'summary',
            'work experience': 'experience',
            'experience': 'experience',
            'employment history': 'experience',
            'professional experience': 'experience',
            'education': 'education',
            'academic background': 'education',
            'skills': 'skills',
            'technical skills': 'skills',
            'core skills': 'skills',
            'certifications': 'certifications',
            'certificates': 'certifications',
            'projects': 'projects',
            'personal projects': 'projects',
            'portfolio': 'projects',
            'achievements': 'achievements',
            'awards': 'achievements',
            'publications': 'publications',
            'volunteer': 'volunteer',
            'volunteering': 'volunteer',
            'references': 'references',
            'additional information': 'other',
        }
        self.section_header_pattern = re.compile(r'^(?:[A-Z][A-Z &/\-]{2,}|[A-Z][A-Za-z &/\-]{2,}:?)$')

    def extract_from_pdf(self, file_path: str) -> str:
        """Extract text from PDF file"""
        text = ""
        try:
            with pdfplumber.open(file_path) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text() or ""
                    if not page_text.strip():
                        # Fallback for PDFs where regular text extraction fails.
                        words = page.extract_words() or []
                        page_text = " ".join(w.get('text', '') for w in words if w.get('text'))
                    text += page_text + "\n"
        except Exception as e:
            print(f"Error extracting PDF: {e}")
        return text

    def extract_from_docx(self, file_path: str) -> str:
        """Extract text from DOCX file"""
        text = ""
        try:
            doc = Document(file_path)
            for paragraph in doc.paragraphs:
                text += paragraph.text + "\n"
        except Exception as e:
            print(f"Error extracting DOCX: {e}")
        return text

    def _clean_text(self, text: str) -> str:
        normalized = re.sub(r'\r', '\n', text or "")
        normalized = re.sub(r'\n{3,}', '\n\n', normalized)
        normalized = re.sub(r'\t+', ' ', normalized)
        return normalized.strip()

    def _split_lines(self, text: str) -> List[str]:
        return [line.strip() for line in self._clean_text(text).split('\n')]

    def _normalize_header(self, text: str) -> str:
        header = re.sub(r'[:\-–—]+$', '', str(text or '').strip()).lower()
        header = re.sub(r'\s+', ' ', header)
        return header

    def _classify_section(self, header: str) -> str:
        header_norm = self._normalize_header(header)
        if header_norm in self.section_aliases:
            return self.section_aliases[header_norm]
        for alias, canonical in self.section_aliases.items():
            if alias in header_norm:
                return canonical
        return 'other'

    def _is_section_header(self, line: str) -> bool:
        line = str(line or '').strip()
        if not line:
            return False
        if len(line) > 60:
            return False
        if ':' in line and len(line.split()) <= 6:
            return True
        return bool(self.section_header_pattern.match(line))

    def _detect_sections(self, text: str) -> Dict[str, List[str]]:
        lines = self._split_lines(text)
        sections: Dict[str, List[str]] = {'preamble': []}
        current = 'preamble'
        sections[current] = []

        for raw_line in lines:
            line = raw_line.strip()
            if not line:
                continue

            if self._is_section_header(line):
                current = self._classify_section(line)
                sections.setdefault(current, [])
                continue

            sections.setdefault(current, []).append(line)

        return sections

    def _join_lines(self, lines: List[str]) -> str:
        return '\n'.join([line for line in lines if line]).strip()

    def _extract_section_text(self, sections: Dict[str, List[str]], section_name: str) -> str:
        return self._join_lines(sections.get(section_name, []))

    def _extract_links(self, text: str) -> Dict[str, List[str]]:
        text = self._normalize_obfuscation(text)
        urls = re.findall(r'https?://[^\s)\]\}>"\']+', text, flags=re.IGNORECASE)
        linkedin = [u for u in urls if 'linkedin.com' in u.lower()]
        github = [u for u in urls if 'github.com' in u.lower()]
        portfolio = [u for u in urls if u not in linkedin and u not in github]
        return {
            'linkedin': sorted(set(linkedin)),
            'github': sorted(set(github)),
            'portfolio': sorted(set(portfolio)),
        }

    def _extract_summary_text(self, sections: Dict[str, List[str]]) -> str:
        summary = self._extract_section_text(sections, 'summary')
        if summary:
            return summary
        preamble = self._join_lines(sections.get('preamble', [])[:8])
        return preamble

    def _extract_certifications(self, sections: Dict[str, List[str]], text: str) -> List[str]:
        cert_text = self._extract_section_text(sections, 'certifications')
        candidates = []
        source = cert_text or text
        for line in self._split_lines(source):
            if any(keyword in line.lower() for keyword in ['cert', 'certificate', 'certification', 'aws', 'pmp', 'cfa', 'cpa', 'comptia', 'azure', 'google cloud', 'scrum']):
                cleaned = re.sub(r'^[-•*\u2022\s]+', '', line).strip()
                if cleaned and cleaned not in candidates:
                    candidates.append(cleaned)
        return candidates[:10]

    def _extract_projects(self, sections: Dict[str, List[str]], text: str) -> List[str]:
        project_text = self._extract_section_text(sections, 'projects')
        candidates = []
        source = project_text or text
        for line in self._split_lines(source):
            if len(line) < 3:
                continue
            if any(keyword in line.lower() for keyword in ['project', 'built', 'developed', 'created', 'portfolio', 'github']):
                cleaned = re.sub(r'^[-•*\u2022\s]+', '', line).strip()
                if cleaned and cleaned not in candidates:
                    candidates.append(cleaned)
        return candidates[:10]

    def _extract_experience_items(self, sections: Dict[str, List[str]], text: str) -> List[Dict]:
        experience_text = self._extract_section_text(sections, 'experience') or text
        lines = self._split_lines(experience_text)
        roles: List[Dict] = []
        current_role = None

        title_pattern = re.compile(
            r'(?P<title>[A-Z][A-Za-z0-9+\-/&()., ]{2,80}?)\s*(?:\||-|,| at )\s*(?P<employer>[A-Z][A-Za-z0-9&()., ]{2,80})',
            re.IGNORECASE,
        )
        date_pattern = re.compile(r'(?:(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s*)?(?:19|20)\d{2}\s*(?:-|–|to|through|present|current)\s*(?:(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s*)?(?:19|20)\d{2}|(?:present|current)', re.IGNORECASE)

        for raw_line in lines:
            line = raw_line.strip()
            if not line:
                continue

            is_bullet = line.startswith(('-', '•', '*', '\u2022'))
            title_match = title_pattern.search(line)

            if title_match and not is_bullet:
                if current_role:
                    roles.append(current_role)
                current_role = {
                    'job_title': title_match.group('title').strip(),
                    'employer': title_match.group('employer').strip(),
                    'employment_dates': '',
                    'employment_type': '',
                    'location': '',
                    'responsibilities': [],
                    'achievements': [],
                    'raw_lines': [line],
                }
                continue

            if current_role is None and any(keyword in line.lower() for keyword in ['manager', 'developer', 'engineer', 'analyst', 'lead', 'consultant', 'intern', 'specialist', 'assistant']):
                current_role = {
                    'job_title': line,
                    'employer': '',
                    'employment_dates': '',
                    'employment_type': '',
                    'location': '',
                    'responsibilities': [],
                    'achievements': [],
                    'raw_lines': [line],
                }
                continue

            if current_role is None:
                continue

            current_role['raw_lines'].append(line)
            if date_pattern.search(line) and not current_role['employment_dates']:
                current_role['employment_dates'] = line

            if any(prefix in line.lower() for prefix in ['remote', 'hybrid', 'onsite', 'on-site']):
                current_role['location'] = line

            if is_bullet or line.endswith('.'):
                target = 'achievements' if any(metric in line for metric in ['%', '$', 'x', 'grew', 'reduced', 'increased', 'improved', 'saved', 'led', 'delivered']) else 'responsibilities'
                current_role[target].append(re.sub(r'^[-•*\u2022\s]+', '', line).strip())

        if current_role:
            roles.append(current_role)

        return roles[:12]

    def _extract_education_items(self, sections: Dict[str, List[str]], text: str) -> List[Dict]:
        education_text = self._extract_section_text(sections, 'education') or text
        items: List[Dict] = []
        lines = self._split_lines(education_text)
        year_pattern = re.compile(r'(19|20)\d{2}')

        current_item = None
        for line in lines:
            if not line:
                continue
            if any(k in line.lower() for k in ['bsc', 'bachelor', 'master', 'msc', 'mba', 'diploma', 'certificate', 'phd', 'degree', 'associate', 'honours', 'honors']):
                if current_item:
                    items.append(current_item)
                current_item = {
                    'qualification': line.strip(),
                    'institution': '',
                    'field_of_study': '',
                    'graduation_year': year_pattern.search(line).group(0) if year_pattern.search(line) else '',
                    'raw_lines': [line],
                }
                continue
            if current_item is not None:
                current_item['raw_lines'].append(line)
                if not current_item['institution'] and any(keyword in line.lower() for keyword in self.institution_keywords):
                    current_item['institution'] = line.strip()
                if not current_item['field_of_study'] and any(keyword in line.lower() for keyword in ['computer science', 'finance', 'engineering', 'information technology', 'business', 'accounting', 'marketing', 'law', 'nursing', 'medicine']):
                    current_item['field_of_study'] = line.strip()

        if current_item:
            items.append(current_item)

        return items[:10]

    def _normalize_obfuscation(self, text: str) -> str:
        """Normalize common obfuscations like ' at ', '[at]', ' dot ' etc."""
        if not text:
            return text
        s = text
        # Common replacements
        s = s.replace('\uFF20', '@')  # fullwidth at
        s = s.replace('＠', '@')
        # various fullwidth/ideographic dots -> ascii dot
        for uni_dot in ['。', '．', '｡', '﹒']:
            s = s.replace(uni_dot, '.')
        # replace common obfuscations like ' [at] ', '(at)', ' at ' -> '@'
        s = re.sub(r'\s*\[?\(?\s*at\s*\)?\]?\s*', '@', s, flags=re.IGNORECASE)
        # replace common obfuscations like ' dot ', '(dot)', '[dot]' -> '.'
        s = re.sub(r'\s*\[?\(?\s*dot\s*\)?\]?\s*', '.', s, flags=re.IGNORECASE)
        # remove spaces around @ and dots that often break regex
        s = re.sub(r'\s*@\s*', '@', s)
        s = re.sub(r'\s*\.\s*', '.', s)
        return s

    def extract_email(self, text: str) -> str:
        """Extract email address using normalization, labeled-field search and fallbacks."""
        if not text:
            return ""

        norm = self._normalize_obfuscation(text)

        # Prefer labeled occurrences (Email:, E-mail:, Contact:)
        labeled_pattern = re.compile(r'(?:email|e-mail|contact|mailto)[:\s]*([^\n\r]+)', re.IGNORECASE)
        for m in labeled_pattern.finditer(norm):
            candidate = m.group(1).strip()
            # strip common trailing punctuation
            candidate = candidate.strip(' ,;:\t"\'')
            email = re.search(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}', candidate)
            if email:
                return email.group(0).lower()

        # Look for inline emails in the whole text
        email_re = re.compile(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}', re.UNICODE)
        m = email_re.search(norm)
        if m:
            return m.group(0).lower()

        # Heuristic fallback: patterns like 'user at domain dot com'
        fuzzy = re.sub(r'[^a-zA-Z0-9@._%+\s-]', ' ', norm)
        fuzzy = re.sub(r'\s{2,}', ' ', fuzzy)
        fuzzy_match = re.search(r'([A-Za-z0-9._%+-]+)\s+at\s+([A-Za-z0-9.-]+)\s+dot\s+([A-Za-z]{2,})', fuzzy, re.IGNORECASE)
        if fuzzy_match:
            return f"{fuzzy_match.group(1).lower()}@{fuzzy_match.group(2).lower()}.{fuzzy_match.group(3).lower()}"

        # No email found
        return ""

    def extract_phone(self, text: str) -> str:
        """Extract phone number"""
        patterns = [
            r'(?:\+\d{1,3}[-.\s]?)?\(?(?:\d{2,4})\)?[-.\s]?\d{3,4}[-.\s]?\d{3,4}',
            r'\+\d{9,15}',
            r'\b\d{10,13}\b'
        ]
        for pattern in patterns:
            matches = re.findall(pattern, text)
            if matches:
                phone = re.sub(r'\s+', ' ', matches[0]).strip()
                return phone
        return ""

    def extract_names(self, text: str) -> Tuple[str, str]:
        """Extract first and last names"""
        first_name = ""
        last_name = ""

        lines = text.split('\n')
        blocked_tokens = {
            'curriculum', 'vitae', 'resume', 'cv', 'contact', 'email', 'phone',
            'summary', 'profile', 'objective', 'address', 'linkedin', 'github'
        }
        for line in lines[:40]:
            line = re.sub(r'\s+', ' ', line or '').strip()
            if not line:
                continue
            lowered = line.lower()
            if "@" in lowered or any(ch.isdigit() for ch in lowered) or 'http' in lowered:
                continue
            words = [w for w in re.findall(r"[A-Za-z][A-Za-z'\-]{1,30}", line) if len(w) > 1]
            if len(words) < 1:
                continue
            if words[0].lower() in blocked_tokens or (len(words) >= 2 and words[1].lower() in blocked_tokens):
                continue

            first_name = words[0]
            if len(words) >= 2:
                last_name = words[1]
            break

        if self.nlp and not first_name:
            doc = self.nlp(text[:1500])
            for ent in doc.ents:
                if ent.label_ == "PERSON":
                    parts = ent.text.split()
                    if len(parts) >= 2:
                        first_name = parts[0]
                        last_name = parts[1]
                        break

        # Clean up
        first_name = re.sub(r'[^a-zA-Z]', '', first_name).strip()
        last_name = re.sub(r'[^a-zA-Z]', '', last_name).strip()

        if first_name and not last_name:
            # Accept a single strong name token instead of rejecting the CV outright.
            return first_name, ""

        return first_name, last_name

    def _name_from_email(self, email: str) -> Tuple[str, str]:
        if not email or '@' not in email:
            return "", ""
        local = email.split('@', 1)[0]
        parts = [p for p in re.split(r'[^a-zA-Z]+', local) if p and len(p) > 1]
        if len(parts) >= 2:
            return parts[0].title(), parts[1].title()
        if len(parts) == 1:
            return parts[0].title(), ""
        return "", ""

    def extract_gender(self, text: str) -> str:
        """Infer gender from pronouns or titles"""
        text_lower = text.lower()
        
        female_indicators = ['she/her', 'pronouns: she', 'mrs.', 'ms.', 'miss', 'chairwoman', 'female']
        male_indicators = ['he/him', 'pronouns: he', 'mr.', 'chairman', 'male']
        
        for indicator in female_indicators:
            if indicator in text_lower:
                return "Female"
        
        for indicator in male_indicators:
            if indicator in text_lower:
                return "Male"
        
        return "Not specified"

    def extract_location(self, text: str) -> Tuple[str, str]:
        """Extract city and country"""
        city = ""
        country = ""

        text_upper = text.upper()
        for country_name in self.countries:
            if country_name.upper() in text_upper:
                country = country_name
                break

        lines = text.split('\n')
        for line in lines[:20]:
            words = line.split(',')
            if len(words) > 1 and country and country.lower() in words[-1].lower():
                city = words[0].strip()
                break

        if self.nlp and (not city or not country):
            doc = self.nlp(text[:2000])
            gpe_entities = [ent.text for ent in doc.ents if ent.label_ in ["GPE", "LOC"]]
            if gpe_entities and not city:
                city = gpe_entities[0]

        if not country:
            lowered = text.lower()
            for region, mapped_country in self.region_country_map.items():
                if region in lowered:
                    country = mapped_country
                    if not city:
                        city = region.title()
                    break
        
        return city, country

    def extract_institutions(self, text: str) -> List[str]:
        institutions = []
        lines = [line.strip() for line in text.split('\n') if line.strip()]

        for line in lines:
            line_lower = line.lower()
            if any(keyword in line_lower for keyword in self.institution_keywords):
                cleaned = re.sub(r'\s+', ' ', line).strip(' -:;')
                if len(cleaned) > 4 and cleaned not in institutions:
                    institutions.append(cleaned)

        if self.nlp and not institutions:
            doc = self.nlp(text[:3000])
            orgs = [ent.text.strip() for ent in doc.ents if ent.label_ == "ORG"]
            for org in orgs:
                if any(keyword in org.lower() for keyword in self.institution_keywords):
                    if org not in institutions:
                        institutions.append(org)

        return institutions[:5]

    def extract_education(self, text: str) -> List[Dict]:
        """Extract education details"""
        education = []
        
        degree_keywords = ['bachelor', 'master', 'phd', 'diploma', 'bsc', 'msc', 'btech', 
                          'mtech', 'degree', 'graduation', 'graduated', 'b.a', 'b.s', 'b.e']
        
        lines = text.split('\n')
        for i, line in enumerate(lines):
            if any(keyword in line.lower() for keyword in degree_keywords):
                year_match = re.search(r'(19|20)\d{2}', line)
                next_line = lines[i+1].strip() if i+1 < len(lines) else ""
                institution = ""
                if any(keyword in next_line.lower() for keyword in self.institution_keywords):
                    institution = next_line
                education.append({
                    'qualification': line.strip(),
                    'details': next_line,
                    'institution': institution,
                    'graduation_year': year_match.group(0) if year_match else ""
                })

        if not education:
            for institution in self.extract_institutions(text):
                education.append({
                    'qualification': institution,
                    'details': 'Institution detected from CV text',
                    'institution': institution,
                    'graduation_year': ''
                })
        
        return education

    def extract_experience(self, text: str) -> Dict:
        """Extract experience information"""
        experience = {
            'years': 0,
            'current_role': "",
            'previous_roles': []
        }
        
        # Look for years of experience
        year_patterns = [
            r'(\d+(?:\.\d+)?)\s*(?:\+)?\s*(?:years?|yrs?)\s*(?:of)?\s*(?:experience)?',
            r'(\d+)\s*(?:\+)?\s*years?',
            r'years?[\s:]+(\d+)',
            r'\b(\d+)\s*yrs?\b',
        ]
        
        for pattern in year_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            if matches:
                try:
                    experience['years'] = int(float(matches[0]))
                    break
                except Exception:
                    pass

        if experience['years'] == 0:
            timeline_matches = re.findall(r'(?:19|20)\d{2}', text)
            if len(timeline_matches) >= 2:
                try:
                    years_span = abs(int(timeline_matches[0]) - int(timeline_matches[-1]))
                    experience['years'] = max(0, years_span)
                except Exception:
                    pass

        # Guard against OCR noise generating unrealistic values.
        if experience['years'] < 0:
            experience['years'] = 0
        if experience['years'] > 45:
            experience['years'] = 0

        # Look for job titles
        job_keywords = ['developer', 'engineer', 'manager', 'analyst', 'designer', 
                       'consultant', 'architect', 'lead', 'senior', 'junior', 'technician', 'specialist']
        
        lines = text.split('\n')
        for line in lines:
            if any(keyword in line.lower() for keyword in job_keywords):
                if not experience['current_role']:
                    experience['current_role'] = line.strip()
                else:
                    experience['previous_roles'].append(line.strip())
        
        return experience

    def _normalize_skill(self, skill: str) -> str:
        compact = skill.strip().lower().replace(' ', '')
        if compact in self.skill_aliases:
            return self.skill_aliases[compact]
        return skill

    def extract_skills(self, text: str) -> List[str]:
        """Extract skills from CV using master skills and optional extra skills list"""
        return self._extract_skills_with_master(text, extra_skills=None)

    def _extract_skills_with_master(self, text: str, extra_skills: List[str] = None) -> List[str]:
        found_skills = set()
        text_lower = text.lower()

        # Check master skills first (broad coverage)
        for skill in getattr(self, 'master_skills', []) + self.common_skills:
            if skill and isinstance(skill, str) and skill.lower() in text_lower:
                found_skills.add(self._normalize_skill(skill))

        # Token-based fallback matching
        raw_tokens = re.findall(r'\b[a-zA-Z][a-zA-Z+.#]{1,25}\b', text)
        for token in raw_tokens:
            norm = self._normalize_skill(token)
            # match against both common and master skills
            if norm in [self._normalize_skill(s) for s in (getattr(self, 'master_skills', []) + self.common_skills)]:
                found_skills.add(norm)

        # Merge any extra skills provided (e.g., from pyresparser)
        if extra_skills:
            for s in extra_skills:
                if s and isinstance(s, str):
                    found_skills.add(self._normalize_skill(s))

        return sorted(found_skills)
    def extract_driver_license(self, text: str) -> bool:
        """Check if CV mentions driver's license or driving experience.

        Accept common spelling variants (license / licence) and several
        phrase patterns such as "driving licence", "driver's permit",
        "licensed driver", or licence classes.
        """
        if not text:
            return False

        driver_patterns = [
            r"\bdriver'?s?\s+licen[cs]e\b",
            r"\bdriver'?s?\s+permit\b",
            r"\bvalid\s+driver'?s?\s+licen[cs]e\b",
            r"\bdriving\s+licen[cs]e\b",
            r"\bdriving\s+permit\b",
            r"\bPDP\b",  # Professional Driver's Permit
            r"\bclass\s+[a-z0-9]+\b",  # class C, class 2, etc.
            r"\blicensed\s+driver\b",
            r"\bholds?\s+(a\s+)?driving\s+licen[cs]e\b",
            r"\bfull\s+driving\s+licen[cs]e\b",
        ]

        for pattern in driver_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return True

        return False
    
    def parse_with_pyresparser(self, file_path: str) -> List[str]:
        """Use pyresparser to extract fields if available. Returns a list of skills or empty list."""
        if not getattr(self, 'pyresparser_available', False):
            return []

        try:
            data = ResumeParser(file_path).get_extracted_data()
            skills = data.get('skills') or data.get('skill') or []
            if isinstance(skills, str):
                # comma separated
                skills = [s.strip() for s in skills.split(',') if s.strip()]
            return skills or []
        except Exception as e:
            print(f"pyresparser extraction failed: {e}")
            return []
    def extract_age_or_dob(self, text: str) -> str:
        """Extract age or date of birth"""
        date_patterns = [
            r'(\d{1,2}[-/]\d{1,2}[-/]\d{4})',
            r'(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4}',
            r'age[\s:]+(\d{1,3})',
            r'born[\s:]+(\d{4})'
        ]
        
        for pattern in date_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            if matches:
                return matches[0]
        
        return ""

    def _calculate_age(self, age_or_dob: str) -> int:
        if not age_or_dob:
            return 0
        if age_or_dob.isdigit() and len(age_or_dob) <= 2:
            age = int(age_or_dob)
            return age if 14 <= age <= 80 else 0

        for fmt in ["%d/%m/%Y", "%d-%m-%Y", "%m/%d/%Y", "%m-%d-%Y", "%B %d %Y", "%B %d, %Y"]:
            try:
                dob = datetime.strptime(age_or_dob, fmt)
                today = datetime.today()
                return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
            except ValueError:
                continue
        return 0

    def infer_education_level(self, education: List[Dict]) -> str:
        text = " ".join(item.get('qualification', '').lower() for item in education)
        if any(k in text for k in ['phd', 'doctorate']):
            return 'PhD'
        if any(k in text for k in ['master', 'msc', 'mba', 'mtech']):
            return 'Masters'
        if any(k in text for k in ['bachelor', 'bsc', 'ba', 'btech', 'degree']):
            return 'Degree'
        if any(k in text for k in ['diploma', 'certificate']):
            return 'Diploma/Certificate'
        return 'Unknown'

    def parse_cv(self, file_path: str) -> Dict:
        """Parse complete CV and extract all information"""
        if file_path.lower().endswith('.pdf'):
            text = self.extract_from_pdf(file_path)
        elif file_path.lower().endswith('.docx'):
            text = self.extract_from_docx(file_path)
        else:
            return {}

        text = self._clean_text(text)
        sections = self._detect_sections(text)

        contact_text = self._extract_section_text(sections, 'contact') or text[:2000]
        contact_plus_text = f"{contact_text}\n{text}"
        summary = self._extract_summary_text(sections)
        links = self._extract_links(text)
        certifications = self._extract_certifications(sections, text)
        projects = self._extract_projects(sections, text)
        experience_items = self._extract_experience_items(sections, text)
        education_items = self._extract_education_items(sections, text)

        first_name, last_name = self.extract_names(contact_plus_text)
        email = self.extract_email(contact_plus_text)
        phone = self.extract_phone(contact_plus_text)
        if (not first_name or not last_name) and email:
            email_first, email_last = self._name_from_email(email)
            if not first_name:
                first_name = email_first
            if not last_name:
                last_name = email_last
        gender = self.extract_gender(text)
        city, country = self.extract_location(contact_plus_text)
        age_dob = self.extract_age_or_dob(text)
        age = self._calculate_age(str(age_dob))
        education = education_items or self.extract_education(text)
        education_level = self.infer_education_level(education)
        experience = self.extract_experience(text)
        # Optionally use pyresparser for fast resume parsing and skill extraction
        parser_skills = []
        try:
            if getattr(self, 'pyresparser_available', False):
                parser_skills = self.parse_with_pyresparser(file_path)
        except Exception as e:
            print(f"Error running pyresparser: {e}")

        skills = self._extract_skills_with_master(text, extra_skills=parser_skills)
        has_driver_license = self.extract_driver_license(text)

        confidence = {
            'contact': 'HIGH' if email or phone or (first_name and last_name) else 'MEDIUM',
            'summary': 'HIGH' if summary else 'LOW',
            'experience': 'HIGH' if experience_items else 'MEDIUM',
            'education': 'HIGH' if education_items else 'MEDIUM',
            'skills': 'HIGH' if skills else 'LOW',
        }

        return {
            'first_name': first_name,
            'last_name': last_name,
            'email': email,
            'phone': phone,
            'gender': gender,
            'city': city,
            'country': country,
            'age_dob': age_dob,
            'age': age,
            'education': education,
            'education_level': education_level,
            'experience': experience,
            'skills': skills,
            'has_driver_license': has_driver_license,
            'summary': summary,
            'links': links,
            'certifications': certifications,
            'projects': projects,
            'experience_entries': experience_items,
            'sections': sections,
            'confidence': confidence,
            'raw_text': text
        }
