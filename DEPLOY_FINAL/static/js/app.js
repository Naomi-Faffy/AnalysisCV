const state = {
    candidates: [],
    filteredCandidates: [],
    topCandidates: [],
    uploadResults: [],
    jobs: [],
    activeJob: null,
    activeMatches: [],
    activeJobReport: null,
    candidatePage: 1,
    filteredCandidatePage: 1,
    activeTopCount: 20,
    activeJobFilters: {},
    stats: {},
    charts: {}
};

const CANDIDATES_PAGE_SIZE = 12;

const chartPalette = [
    '#22489A', '#32B24B', '#FF9F1C', '#3BA7D6', '#A56AE0', '#F06292', '#607D8B', '#26A69A'
];

function getCsrfToken() {
    const tokenEl = document.querySelector('meta[name="csrf-token"]');
    return tokenEl ? tokenEl.getAttribute('content') : '';
}

function fetchWithCsrf(url, options = {}) {
    const csrfToken = getCsrfToken();
    const headers = new Headers(options.headers || {});

    if (csrfToken) {
        headers.set('X-CSRFToken', csrfToken);
    }

    return fetch(url, {
        ...options,
        headers
    });
}

document.addEventListener('DOMContentLoaded', () => {
    initNavigation();
    initSidebarToggle();
    initUploadArea();
    initJobForm();
    bindFilterInputs();
    initActiveJobControls();
    loadDashboard();
    loadCandidates();
    loadJobs();
    loadActiveJobMatches();
    loadActiveJobReport();
});

function initActiveJobControls() {
    const topEl = document.getElementById('activeTopCount');

    if (topEl) {
        // initialize from state
        topEl.value = String(state.activeTopCount || 20);
        topEl.addEventListener('change', () => {
            const val = parseInt(topEl.value, 10) || 20;
            // constrain to valid values (5..50 step 5)
            state.activeTopCount = Math.min(50, Math.max(5, Math.round(val / 5) * 5));
            topEl.value = String(state.activeTopCount);
            loadActiveJobReport();
            renderActiveJobMatches();
        });
    }
}

async function applyActiveFilters() {
    const topEl = document.getElementById('activeTopCount');
    const searchEl = document.getElementById('activeSearchInput');
    const minScoreEl = document.getElementById('activeScoreRangeMin');
    const maxScoreEl = document.getElementById('activeScoreRangeMax');
    const genderEl = document.getElementById('activeGenderFilter');
    const countryEl = document.getElementById('activeCountryFilter');
    const cityEl = document.getElementById('activeCityFilter');
    const educationEl = document.getElementById('activeEducationFilter');
    const skillEl = document.getElementById('activeSkillFilter');
    const minExpEl = document.getElementById('activeMinExperience');
    const driverEl = document.getElementById('activeDriverLicenseFilter');

    state.activeTopCount = topEl ? (parseInt(topEl.value, 10) || 20) : (state.activeTopCount || 20);
    state.activeJobFilters = {
        search: searchEl ? searchEl.value.trim() : '',
        min_score: minScoreEl && minScoreEl.value ? Number(minScoreEl.value) : null,
        max_score: maxScoreEl && maxScoreEl.value ? Number(maxScoreEl.value) : null,
        gender: genderEl ? genderEl.value : '',
        country: countryEl ? countryEl.value.trim() : '',
        city: cityEl ? cityEl.value.trim() : '',
        education_level: educationEl ? educationEl.value : '',
        skill: skillEl ? skillEl.value.trim() : '',
        min_experience: minExpEl && minExpEl.value ? Number(minExpEl.value) : null,
        has_driver_license: driverEl ? driverEl.value : ''
    };

    console.log('applyActiveFilters', { filters: state.activeJobFilters, topCount: state.activeTopCount });

    await loadActiveJobReport();
    await awaitPromiseLoadActiveMatches();
}

// Small helper to call loadActiveJobMatches and await it from non-async contexts
function awaitPromiseLoadActiveMatches() {
    // loadActiveJobMatches returns a promise; return it so callers can await
    return loadActiveJobMatches();
}

async function resetActiveFilters() {
    const topEl = document.getElementById('activeTopCount');

    if (topEl) topEl.value = '20';
    ['activeSearchInput','activeScoreRangeMin','activeScoreRangeMax','activeGenderFilter','activeCountryFilter','activeCityFilter','activeEducationFilter','activeSkillFilter','activeMinExperience','activeDriverLicenseFilter'].forEach(id => {
        const el = document.getElementById(id);
        if (!el) return;
        if (el.tagName === 'SELECT') el.selectedIndex = 0;
        else el.value = '';
    });

    state.activeTopCount = 20;
    state.activeJobFilters = {};
    await loadActiveJobReport();
    await awaitPromiseLoadActiveMatches();
}

function _candidatePassesActiveFilters(candidate, filters) {
    if (!filters || !Object.keys(filters).length) return true;
    if (filters.min_score !== null && filters.min_score !== undefined) {
        const fs = Number(candidate['Final Score (%)'] || 0);
        if (fs < filters.min_score) return false;
    }
    if (filters.max_score !== null && filters.max_score !== undefined) {
        const fs = Number(candidate['Final Score (%)'] || 0);
        if (fs > filters.max_score) return false;
    }
    if (filters.gender) {
        const g = String(candidate.Gender || '').toLowerCase();
        if (filters.gender && filters.gender !== '' && g !== String(filters.gender).toLowerCase()) return false;
    }
    if (filters.country) {
        const c = String(candidate.Country || '').toLowerCase();
        if (!c.includes(String(filters.country).toLowerCase())) return false;
    }
    if (filters.city) {
        const ct = String(candidate.City || '').toLowerCase();
        if (!ct.includes(String(filters.city).toLowerCase())) return false;
    }
    if (filters.education_level) {
        const ed = String(candidate['Education Level'] || '').toLowerCase();
        if (filters.education_level && filters.education_level !== '' && ed !== String(filters.education_level).toLowerCase()) return false;
    }
    if (filters.search) {
        const search = String(filters.search).toLowerCase();
        const fullName = `${candidate['First Name'] || ''} ${candidate['Last Name'] || ''}`.trim().toLowerCase();
        const email = String(candidate.Email || '').toLowerCase();
        if (!fullName.includes(search) && !email.includes(search)) return false;
    }
    if (filters.skill) {
        const skl = String(candidate.Skills || '').toLowerCase();
        if (!skl.includes(String(filters.skill).toLowerCase())) return false;
    }
    if (filters.min_experience !== null && filters.min_experience !== undefined) {
        const exp = Number(candidate['Years of Experience'] || candidate['Years Experience'] || 0) || 0;
        if (exp < filters.min_experience) return false;
    }
    if (filters.has_driver_license) {
        // Support multiple possible field names and numeric values (1/0)
        const drvRaw = (candidate["Has Driver's License"] !== undefined)
            ? candidate["Has Driver's License"]
            : (candidate['Has Driver License'] !== undefined)
                ? candidate['Has Driver License']
                : (candidate.has_driver_license !== undefined)
                    ? candidate.has_driver_license
                    : (candidate['has_driver_license'] !== undefined)
                        ? candidate['has_driver_license']
                        : '';

        const drv = String(drvRaw || '').toLowerCase();
        const drvBool = drv === 'true' || drv === '1' || drv === 'yes';
        const drvFalse = drv === 'false' || drv === '0' || drv === 'no' || drv === '';

        if (String(filters.has_driver_license) === 'true' && !drvBool) return false;
        if (String(filters.has_driver_license) === 'false' && drvBool) return false;
    }
    return true;
}

function initNavigation() {
    const links = document.querySelectorAll('.nav-link');
    const tabs = document.querySelectorAll('.tab-content');

    links.forEach((link) => {
        const tabName = link.getAttribute('data-tab');
        // If this link doesn't have a data-tab attribute, allow normal navigation (e.g., /admin external page)
        if (!tabName) return;

        link.addEventListener('click', (event) => {
            event.preventDefault();

            links.forEach((item) => item.classList.remove('active'));
            tabs.forEach((tab) => tab.classList.remove('active'));

            link.classList.add('active');
            const tabEl = document.getElementById(tabName);
            if (tabEl) tabEl.classList.add('active');
            document.getElementById('page-title').textContent = toTitleCase(tabName);

            if (tabName === 'active-job') {
                loadActiveJobReport();
            }
        });
    });
}

function initSidebarToggle() {
    const sidebar = document.getElementById('sidebar');
    const toggle = document.getElementById('sidebarToggle');

    if (!sidebar || !toggle) {
        return;
    }

    const syncState = (isOpen) => {
        document.body.classList.toggle('sidebar-open', isOpen);
        toggle.setAttribute('aria-expanded', isOpen ? 'true' : 'false');
    };

    syncState(false);

    toggle.addEventListener('click', () => {
        syncState(!document.body.classList.contains('sidebar-open'));
    });

    sidebar.querySelectorAll('.nav-link').forEach((link) => {
        link.addEventListener('click', () => {
            syncState(false);
        });
    });

    window.addEventListener('keydown', (event) => {
        if (event.key === 'Escape') {
            syncState(false);
        }
    });

    window.addEventListener('resize', () => {
        if (window.innerWidth > 900) {
            syncState(false);
        }
    });
}

function initUploadArea() {
    const dropZone = document.getElementById('dropZone');
    const fileInput = document.getElementById('fileInput');
    const folderInput = document.getElementById('folderInput');
    const selectFolderBtn = document.getElementById('selectFolderBtn');

    dropZone.addEventListener('click', (event) => {
        // Only trigger file input if the click is directly on dropZone, not on child elements like buttons
        if (event.target === dropZone || event.target.tagName === 'P') {
            fileInput.click();
        }
    });

    if (selectFolderBtn && folderInput) {
        selectFolderBtn.addEventListener('click', (event) => {
            event.stopPropagation();
            folderInput.click();
        });

        folderInput.addEventListener('change', () => {
            if (folderInput.files.length) {
                // folderInput.files contains all files in the selected directory (and subdirectories)
                uploadCVFiles(Array.from(folderInput.files));
                folderInput.value = '';
            }
        });
    }

    fileInput.addEventListener('change', () => {
        if (fileInput.files.length) {
            uploadCVFiles(Array.from(fileInput.files));
            fileInput.value = '';
        }
    });

    ['dragenter', 'dragover'].forEach((eventName) => {
        dropZone.addEventListener(eventName, (event) => {
            event.preventDefault();
            dropZone.classList.add('drag-over');
        });
    });

    ['dragleave', 'drop'].forEach((eventName) => {
        dropZone.addEventListener(eventName, (event) => {
            event.preventDefault();
            dropZone.classList.remove('drag-over');
        });
    });

    dropZone.addEventListener('drop', (event) => {
        const files = Array.from(event.dataTransfer.files || []);
        if (files.length) {
            uploadCVFiles(files);
        }
    });
}

function bindFilterInputs() {
    const searchInput = document.getElementById('searchInput');
    if (searchInput) {
        searchInput.addEventListener('keydown', (event) => {
            if (event.key === 'Enter') {
                applyFilters();
            }
        });
    }
}

function initJobForm() {
    const form = document.getElementById('jobForm');
    if (!form) {
        return;
    }

    form.addEventListener('submit', async (event) => {
        event.preventDefault();

        const payload = {
            'Job Title': valueOf('jobTitle'),
            'Department / Category': valueOf('jobDepartment'),
            'Job Type': valueOf('jobType'),
            'Work Mode': valueOf('workMode'),
            'Location': valueOf('jobLocation'),
            'Job Description': valueOf('jobDescription'),
            'Key Responsibilities': valueOf('jobResponsibilities'),
            'Requirements / Qualifications': valueOf('jobRequirements'),
            'Experience Level': valueOf('experienceLevel'),
            'Application Deadline': valueOf('applicationDeadline')
        };

        try {
            const response = await fetchWithCsrf('/api/jobs', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(payload)
            });
            const result = await response.json();

            if (!response.ok || !result.success) {
                const message = result.missing_fields?.length
                    ? `Missing fields: ${result.missing_fields.join(', ')}`
                    : (result.error || 'Failed to post job.');
                showJobStatus(message, true);
                return;
            }

            showJobStatus('Job posted successfully.', false);
            resetJobForm(true);
            await loadJobs();
            await loadActiveJobMatches();
            await loadCandidates();
        } catch (error) {
            showJobStatus(`Job post failed: ${error.message}`, true);
        }
    });
}

async function loadJobs() {
    try {
        const response = await fetch('/api/jobs');
        const result = await response.json();
        if (!response.ok || !result.success) {
            return;
        }

        state.jobs = result.jobs || [];
        renderJobsBoard();
        // Populate job filter dropdown if present — dedupe by job title
        const jobFilterEl = document.getElementById('jobFilter');
        if (jobFilterEl) {
            const current = jobFilterEl.value || '';
            jobFilterEl.innerHTML = '<option value="">All Candidates</option>';
            const seenTitles = new Set();
            state.jobs.forEach((job) => {
                const title = (job['Job Title'] || '').trim() || (job['Job ID'] || '').trim();
                if (!title || seenTitles.has(title)) return;
                seenTitles.add(title);
                const opt = document.createElement('option');
                // store the job title as the value so selecting the title filters by title across jobs
                opt.value = title;
                opt.textContent = title;
                jobFilterEl.appendChild(opt);
            });
            if (current) jobFilterEl.value = current;
        }
    } catch (error) {
        console.error('Failed to load jobs:', error);
    }
}

function renderJobsBoard() {
    const container = document.getElementById('jobsBoard');
    if (!container) {
        return;
    }

    if (!state.jobs.length) {
        container.innerHTML = '<div class="empty-state">No job posts yet. Use the form to publish the first role.</div>';
        return;
    }

    container.innerHTML = state.jobs.map((job) => {
        const title = job['Job Title'] || 'Untitled Role';
        const department = job['Department / Category'] || 'General';
        const jobType = job['Job Type'] || '';
        const workMode = job['Work Mode'] || '';
        const location = job['Location'] || '';
        const deadline = job['Application Deadline'] || '';
        const postDate = job['Post Date'] || '';
        const summary = truncateText(job['Job Description'] || '', 180);
        const isActive = Number(job['Is Active'] || 0) === 1 || String(job['Status'] || '').toLowerCase() === 'active';
        const activeBadge = isActive ? '<span class="job-pill">Active</span>' : '<span class="job-pill">Inactive</span>';
        const activeAction = isActive
            ? '<button class="btn-secondary" disabled>Current Active Job</button>'
            : `<button class="btn-primary" onclick="activateJob('${encodeURIComponent(job['Job ID'] || '')}', event)">Set Active</button>`;
        const deleteAction = `<button class="btn-danger" onclick="deleteJob('${encodeURIComponent(job['Job ID'] || '')}', event)">Delete Job</button>`;

        return `
            <div class="job-card" onclick="openJobModal('${encodeURIComponent(job['Job ID'] || '')}')">
                <div class="job-card-header">
                    <div>
                        <div class="job-card-title">${escapeHtml(title)}</div>
                        <div class="candidate-email">${escapeHtml(department)}</div>
                    </div>
                    <div>${activeBadge}</div>
                </div>
                <div class="job-meta">
                    <span class="job-pill">${escapeHtml(jobType)}</span>
                    <span class="job-pill">${escapeHtml(workMode)}</span>
                    <span class="job-pill">${escapeHtml(location)}</span>
                    <span class="job-pill">${escapeHtml(job['Experience Level'] || '')}</span>
                </div>
                <div class="job-summary">${escapeHtml(summary)}</div>
                <div class="candidate-email" style="margin-top: 10px;">
                    Post Date: ${escapeHtml(postDate || 'Auto detected')}
                    ${deadline ? ` | Deadline: ${escapeHtml(deadline)}` : ''}
                </div>
                <div class="job-detail-actions" style="margin-top: 10px;" onclick="event.stopPropagation()">
                    ${activeAction}
                    ${deleteAction}
                </div>
            </div>
        `;
    }).join('');
}

async function activateJob(encodedJobId, event) {
    if (event) {
        event.stopPropagation();
    }

    const jobId = decodeURIComponent(encodedJobId);
    try {
        const response = await fetchWithCsrf(`/api/jobs/${encodeURIComponent(jobId)}/activate`, {
            method: 'POST'
        });
        const result = await response.json();

        if (!response.ok || !result.success) {
            showJobStatus(result.error || 'Failed to activate job.', true);
            return;
        }

        showJobStatus(`Job activated. ${result.matched_candidates || 0} CV bank candidate(s) matched.`, false);
        await Promise.all([loadJobs(), loadActiveJobMatches(), loadActiveJobReport(), loadCandidates()]);

        const activeTab = document.querySelector('.nav-link[data-tab="active-job"]');
        if (activeTab) {
            activeTab.click();
        }
    } catch (error) {
        showJobStatus(`Failed to activate job: ${error.message}`, true);
    }
}

async function deleteJob(encodedJobId, event) {
    if (event) {
        event.stopPropagation();
    }

    const jobId = decodeURIComponent(encodedJobId);
    if (!window.confirm('Delete this job? This cannot be undone.')) {
        return;
    }

    try {
        const response = await fetchWithCsrf(`/api/jobs/${encodeURIComponent(jobId)}`, {
            method: 'DELETE'
        });
        const result = await response.json();

        if (!response.ok || !result.success) {
            showJobStatus(result.error || 'Failed to delete job.', true);
            return;
        }

        showJobStatus('Job deleted successfully.', false);
        await Promise.all([loadJobs(), loadActiveJobMatches(), loadActiveJobReport(), loadCandidates()]);
    } catch (error) {
        showJobStatus(`Failed to delete job: ${error.message}`, true);
    }
}

async function loadActiveJobMatches() {
    try {
        const params = new URLSearchParams();
        const response = await fetch(`/api/jobs/active/matches${params.toString() ? ('?' + params.toString()) : ''}`);
        const result = await response.json();
        if (!response.ok || !result.success) {
            return;
        }

        state.activeJob = result.job || null;
        state.activeMatches = result.candidates || [];
        renderActiveJobMatches();
    } catch (error) {
        console.error('Failed to load active job matches:', error);
    }
}

async function loadActiveJobReport() {
    try {
        const params = new URLSearchParams();
        const topEl = document.getElementById('activeTopCount');
        const topN = topEl ? (parseInt(topEl.value, 10) || state.activeTopCount || 20) : (state.activeTopCount || 20);
        params.set('top_n', String(topN));
        console.log('loadActiveJobReport: requesting', params.toString());
        const response = await fetch(`/api/jobs/active/report${params.toString() ? `?${params.toString()}` : ''}`);
        const result = await response.json();
        console.log('loadActiveJobReport: response', { ok: response.ok, status: response.status, success: result && result.success, top_candidates: (result && result.top_candidates && result.top_candidates.length) || 0 });
        if (!response.ok || !result.success) {
            return;
        }

        state.activeJobReport = result;
        renderActiveJobReport();
    } catch (error) {
        console.error('Failed to load active job report:', error);
    }
}

function renderActiveJobReport() {
    const report = state.activeJobReport;
    console.log('renderActiveJobReport', { reportExists: !!report, jobId: report && report.job && report.job['Job ID'], top_candidates: (report && report.top_candidates && report.top_candidates.length) || 0 });
    const summary = document.getElementById('activeJobAnalysisSummary');
    const topCandidatesContainer = document.getElementById('activeJobTopCandidates');
    const keywords = document.getElementById('activeJobKeywords');
    const notes = document.getElementById('activeJobScoringNotes');

    if (!summary || !topCandidatesContainer || !keywords || !notes) {
        return;
    }

    if (!report || !report.job || !report.job['Job ID']) {
        summary.textContent = 'No active job selected. Set one job as active to view ranking and analysis.';
        topCandidatesContainer.innerHTML = '<div class="empty-state">No active job selected.</div>';
        keywords.innerHTML = '<div class="empty-state">No active job selected.</div>';
        notes.innerHTML = `
            <ul style="margin-left: 18px; color: var(--ink-700);">
                <li>Identity, address and contact details confirm the CV is complete.</li>
                <li>Education, experience and skills drive the main score.</li>
                <li>A master's degree can still rank below a bachelor's if the CV is weak on skills, experience, or evidence matching the job.</li>
            </ul>
        `;
        return;
    }

    const job = report.job;
    const totals = report.totals || {};
    const matchedKeywords = report.matched_keywords || [];
    const missingKeywords = report.missing_keywords || [];
    const topCandidates = report.top_candidates || [];
    const activeFilters = state.activeJobFilters || {};

    const topCount = Number((document.getElementById('activeTopCount') && document.getElementById('activeTopCount').value) || state.activeTopCount || 20);

    const currentViewCandidates = topCandidates.filter(Boolean).slice(0, Math.min(topCount, 50));
    const filteredTopCandidates = currentViewCandidates.filter((candidate) => _candidatePassesActiveFilters(candidate, activeFilters));

    summary.textContent = `Active job: ${job['Job Title'] || 'Untitled'} | ${totals.ranked_candidates || 0} CVs ranked`;

    const candidatesSlice = filteredTopCandidates;

    const topCandidatesRows = candidatesSlice.length
        ? candidatesSlice.map((candidate, index) => `
            <div class="candidate-item" style="align-items: stretch; gap: 12px; flex-direction: column;">
                <div style="display:flex; justify-content:space-between; gap: 12px; align-items:flex-start;">
                    <div class="candidate-info" style="min-width: 0;">
                        <div class="candidate-name">${index + 1}. ${escapeHtml(candidate.Name || `${candidate['First Name'] || ''} ${candidate['Last Name'] || ''}`.trim() || 'N/A')}</div>
                        <div class="candidate-email">${escapeHtml(candidate.Email || 'No email on file')}</div>
                    </div>
                    <div style="display:flex; gap:8px; flex-wrap:wrap; justify-content:flex-end;">
                        <button class="btn-primary btn-small" onclick="openCandidateModal('${encodeURIComponent(candidateIdentifier(candidate))}')">View</button>
                        <a class="btn-resume btn-small" href="/api/download-candidate-cv/${encodeURIComponent(candidateIdentifier(candidate))}" target="_blank" rel="noopener noreferrer">Resume</a>
                    </div>
                </div>
                <div style="display:flex; gap: 10px; flex-wrap: wrap;">
                    <span class="job-pill">CV Score: ${Number(candidate['Final Score (%)'] || 0).toFixed(1)}%</span>
                    <span class="job-pill">Match Score: ${Number(candidate['Match Score (%)'] || 0).toFixed(1)}%</span>
                </div>
            </div>
        `).join('')
        : '<div class="empty-state">No candidates to rank for this active job.</div>';

    topCandidatesContainer.innerHTML = topCandidatesRows;

    const matchedChips = matchedKeywords.length
        ? matchedKeywords.map((keyword) => `<span class="job-pill">${escapeHtml(keyword)}</span>`).join('')
        : '<div class="empty-state">No requirement terms were confidently matched.</div>';
    const missingChips = missingKeywords.length
        ? missingKeywords.map((keyword) => `<span class="job-pill" style="background: rgba(185,74,74,0.12); color: #923838; border-color: rgba(185,74,74,0.25);">${escapeHtml(keyword)}</span>`).join('')
        : '<div class="empty-state">No missing requirement terms detected.</div>';

    keywords.innerHTML = `
        <div class="detail-section">
            <h4>Matched Requirements</h4>
            <div class="job-meta">${matchedChips}</div>
        </div>
        <div class="detail-section">
            <h4>Missing Requirements</h4>
            <div class="job-meta">${missingChips}</div>
        </div>
    `;

    notes.innerHTML = `
        <ul style="margin-left: 18px; color: var(--ink-700);">
            <li><strong>Identity</strong>: name, email and phone completeness.</li>
            <li><strong>Education</strong>: degree level, certifications, field of study and recency.</li>
            <li><strong>Experience</strong>: years, role history and achievement signals.</li>
            <li><strong>Skills</strong>: overlap with the job description and evidence in the CV.</li>
            <li><strong>Important</strong>: this is a holistic score. A master's degree alone does not guarantee a higher rank if skills and experience are weaker.</li>
        </ul>
    `;
}

async function resetSystemData() {
    if (!window.confirm('Reset all system data? This will delete all jobs, candidates, and uploaded files.')) {
        return;
    }

    try {
        const response = await fetchWithCsrf('/api/admin/reset-system', {
            method: 'POST'
        });
        const result = await response.json();

        if (!response.ok || !result.success) {
            alert(result.error || 'Failed to reset system data.');
            return;
        }

        alert('System data reset successfully.');
        state.candidates = [];
        state.filteredCandidates = [];
        state.topCandidates = [];
        state.uploadResults = [];
        state.jobs = [];
        state.activeJob = null;
        state.activeMatches = [];
        state.activeJobReport = null;

        await Promise.all([loadDashboard(), loadCandidates(), loadJobs(), loadActiveJobMatches(), loadActiveJobReport()]);
        renderUploadResults();
    } catch (error) {
        alert(`Failed to reset system data: ${error.message}`);
    }
}

function renderActiveJobMatches() {
    const summary = document.getElementById('activeJobSummary');
    const container = document.getElementById('activeMatchesTable');
    if (!summary || !container) {
        return;
    }

    if (!state.activeJob || !state.activeJob['Job ID']) {
        summary.textContent = 'No active job selected.';
        container.innerHTML = '<div class="empty-state">Set one job as active to see CV bank matches.</div>';
        return;
    }

    const topCount = state.activeTopCount || 20;
    const currentViewMatches = state.activeMatches.filter(Boolean).slice(0, Math.min(topCount, 50));
    const matchesSlice = currentViewMatches.filter((candidate) => _candidatePassesActiveFilters(candidate, state.activeJobFilters || {}));

    summary.textContent = `Active job: ${state.activeJob['Job Title'] || 'Untitled'} (${matchesSlice.length} matched candidate(s) in current view)`;

    if (!matchesSlice.length) {
        container.innerHTML = '<div class="empty-state">No matches yet for the active job.</div>';
        return;
    }

    const rows = matchesSlice
        .map((candidate) => {
            const email = candidate['Email'] || '';
            const fullName = `${candidate['First Name'] || ''} ${candidate['Last Name'] || ''}`.trim();
            const identifier = candidateIdentifier(candidate);
            const score = Number(candidate['Final Score (%)'] || 0).toFixed(1);
            const matchScore = Number(candidate['Match Score (%)'] || 0).toFixed(1);
            const resumeBtn = `<a class="btn-resume btn-small" href="/api/download-candidate-cv/${encodeURIComponent(identifier)}" target="_blank" rel="noopener noreferrer">Resume</a>`;

            return `
                <tr>
                    <td>${escapeHtml(fullName || 'N/A')}</td>
                    <td>${escapeHtml(email || 'No email on file')}</td>
                    <td>${score}%</td>
                    <td>${matchScore}%</td>
                    <td>
                        <button class="btn-primary btn-small" onclick="openCandidateModal('${encodeURIComponent(identifier)}')">View</button>
                    </td>
                    <td>
                        ${resumeBtn}
                    </td>
                </tr>
            `;
        })
        .join('');

    container.innerHTML = `
        <table>
            <thead>
                <tr>
                    <th>Name</th>
                    <th>Email</th>
                    <th>CV Score</th>
                    <th>Job Match</th>
                    <th>View</th>
                    <th>Resume</th>
                </tr>
            </thead>
            <tbody>${rows}</tbody>
        </table>
    `;
}

async function openJobModal(encodedJobId) {
    const jobId = decodeURIComponent(encodedJobId);
    try {
        const response = await fetch(`/api/jobs/${encodeURIComponent(jobId)}`);
        const result = await response.json();
        if (!response.ok || !result.success) {
            return;
        }

        const job = result.job;
        const details = document.getElementById('candidateDetail');
        details.innerHTML = `
            <h3>${escapeHtml(job['Job Title'] || '')}</h3>
            <div class="job-detail-grid">
                ${detailRow('Department / Category', job['Department / Category'])}
                ${detailRow('Job Type', job['Job Type'])}
                ${detailRow('Work Mode', job['Work Mode'])}
                ${detailRow('Location', job['Location'])}
                ${detailRow('Experience Level', job['Experience Level'])}
                ${detailRow('Application Deadline', job['Application Deadline'])}
                ${detailRow('Post Date', job['Post Date'])}
            </div>
            <div class="detail-section">
                <h4>Job Description</h4>
                <div class="detail-value" style="text-align:left; white-space:pre-wrap;">${escapeHtml(job['Job Description'] || '')}</div>
            </div>
            <div class="detail-section">
                <h4>Key Responsibilities</h4>
                <div class="detail-value" style="text-align:left; white-space:pre-wrap;">${escapeHtml(job['Key Responsibilities'] || '')}</div>
            </div>
            <div class="detail-section">
                <h4>Requirements / Qualifications</h4>
                <div class="detail-value" style="text-align:left; white-space:pre-wrap;">${escapeHtml(job['Requirements / Qualifications'] || '')}</div>
            </div>
        `;

        document.getElementById('candidateModal').classList.add('show');
    } catch (error) {
        console.error('Failed to open job details:', error);
    }
}

function showJobStatus(message, isError) {
    const statusEl = document.getElementById('jobFormStatus');
    if (!statusEl) {
        return;
    }
    statusEl.style.display = 'block';
    statusEl.className = `upload-status ${isError ? 'error' : 'success'}`;
    statusEl.textContent = message;
}

function resetJobForm(keepStatus = false) {
    const form = document.getElementById('jobForm');
    if (form) {
        form.reset();
    }
    if (!keepStatus) {
        const statusEl = document.getElementById('jobFormStatus');
        if (statusEl) {
            statusEl.style.display = 'none';
            statusEl.textContent = '';
        }
    }
}

async function uploadCVFiles(files) {
    const validFiles = (files || []).filter((file) => {
        const ext = String(file.name || '').split('.').pop().toLowerCase();
        return ['pdf', 'docx'].includes(ext);
    });

    if (!validFiles.length) {
        showUploadStatus('No valid files selected. Only PDF and DOCX are supported.', true);
        return;
    }

    showUploadStatus(`Uploading ${validFiles.length} CV file(s)...`, false);

    if (validFiles.length === 1) {
        await uploadSingleCV(validFiles[0]);
        return;
    }

    const formData = new FormData();
    validFiles.forEach((file) => formData.append('files', file));
    if (state.activeJob && state.activeJob['Job ID']) {
        formData.append('job_id', state.activeJob['Job ID']);
    }

    try {
        const response = await fetchWithCsrf('/api/upload-cvs', {
            method: 'POST',
            body: formData
        });
        const result = await response.json();

        if (!response.ok || !result.success) {
            showUploadStatus(result.error || 'Batch upload failed.', true);
            state.uploadResults = [
                {
                    file_name: 'Batch Request',
                    status: 'failed',
                    email: '',
                    score: '',
                    message: result.error || 'Batch upload failed.'
                }
            ];
            renderUploadResults();
            return;
        }

        state.uploadResults = (result.results || []).map((item) => {
            const candidate = item.candidate || {};
            return {
                file_name: candidate.file_name || '',
                status: item.status || 'failed',
                email: candidate.email || '',
                score: candidate.score !== undefined ? Number(candidate.score).toFixed(1) + '%' : '',
                message: item.error || ''
            };
        });
        renderUploadResults();

        (result.results || [])
            .filter((item) => item.status === 'uploaded' && item.candidate)
            .forEach((item) => appendRecentUpload(item.candidate));

        const summary = result.summary || {};
        showUploadStatus(
            `Batch complete: ${summary.uploaded || 0} uploaded, ${summary.duplicates || 0} duplicates, ${summary.failed || 0} failed.`,
            false
        );
        await Promise.all([loadDashboard(), loadCandidates(), loadActiveJobMatches()]);
    } catch (error) {
        showUploadStatus(`Batch upload failed: ${error.message}`, true);
    }
}

async function uploadSingleCV(file) {
    const formData = new FormData();
    formData.append('file', file);
    if (state.activeJob && state.activeJob['Job ID']) {
        formData.append('job_id', state.activeJob['Job ID']);
    }

    try {
        const response = await fetchWithCsrf('/api/upload-cv', {
            method: 'POST',
            body: formData
        });
        const result = await response.json();

        if (!response.ok || !result.success) {
            showUploadStatus(result.error || 'Upload failed.', true);
            state.uploadResults = [
                {
                    file_name: file.name,
                    status: result.duplicate ? 'duplicate' : 'failed',
                    email: '',
                    score: '',
                    message: result.error || 'Upload failed.'
                }
            ];
            renderUploadResults();
            return;
        }

        showUploadStatus('CV uploaded successfully. Excel data has been updated.', false);
        appendRecentUpload(result.candidate);
        state.uploadResults = [
            {
                file_name: result.candidate.file_name || file.name,
                status: 'uploaded',
                email: result.candidate.email || '',
                score: result.candidate.score !== undefined ? Number(result.candidate.score).toFixed(1) + '%' : '',
                message: ''
            }
        ];
        renderUploadResults();
        await Promise.all([loadDashboard(), loadCandidates(), loadActiveJobMatches()]);
    } catch (error) {
        showUploadStatus(`Upload failed: ${error.message}`, true);
        state.uploadResults = [
            {
                file_name: file.name,
                status: 'failed',
                email: '',
                score: '',
                message: error.message
            }
        ];
        renderUploadResults();
    }
}

function renderUploadResults() {
    const card = document.getElementById('uploadResultsCard');
    const container = document.getElementById('uploadResultsTable');

    if (!card || !container) {
        return;
    }

    if (!state.uploadResults.length) {
        card.style.display = 'none';
        container.innerHTML = '';
        return;
    }

    card.style.display = 'block';

    const rows = state.uploadResults
        .map((item) => {
            const status = String(item.status || 'failed').toLowerCase();
            const statusClass = `status-${status}`;
            return `
                <tr>
                    <td>${escapeHtml(item.file_name || 'N/A')}</td>
                    <td><span class="status-badge ${statusClass}">${escapeHtml(status)}</span></td>
                    <td>${escapeHtml(item.email || '-')}</td>
                    <td>${escapeHtml(item.score || '-')}</td>
                    <td>${escapeHtml(item.message || '-')}</td>
                </tr>
            `;
        })
        .join('');

    container.innerHTML = `
        <table class="upload-results-table">
            <thead>
                <tr>
                    <th>File</th>
                    <th>Status</th>
                    <th>Email</th>
                    <th>Score</th>
                    <th>Message</th>
                </tr>
            </thead>
            <tbody>${rows}</tbody>
        </table>
    `;
}

function showUploadStatus(message, isError) {
    const statusEl = document.getElementById('uploadStatus');
    statusEl.style.display = 'block';
    statusEl.className = `upload-status ${isError ? 'error' : 'success'}`;
    statusEl.textContent = message;
}

function appendRecentUpload(candidate) {
    const wrapper = document.getElementById('uploadedCandidates');
    const list = document.getElementById('uploadedList');
    wrapper.style.display = 'block';

    const item = document.createElement('div');
    item.className = 'candidate-item';
    item.innerHTML = `
        <div class="candidate-info">
            <div class="candidate-name">${escapeHtml(candidate.name || 'Unknown')}</div>
            <div class="candidate-email">${escapeHtml(candidate.email || '')}</div>
        </div>
        <div class="candidate-score">${Number(candidate.score || 0).toFixed(1)}%</div>
    `;
    list.prepend(item);

    while (list.children.length > 6) {
        list.removeChild(list.lastElementChild);
    }
}

async function loadDashboard() {
    try {
        const response = await fetch('/api/dashboard');
        const result = await response.json();
        if (!response.ok || !result.success) {
            return;
        }

        state.stats = result.stats || {};
        state.topCandidates = result.top_candidates || [];

        renderStatsSummary();
        renderTopCandidates();
        renderCharts();
    } catch (error) {
        console.error('Failed to load dashboard:', error);
    }
}

async function loadCandidates(filters = {}) {
    const params = new URLSearchParams();
    Object.entries(filters).forEach(([key, value]) => {
        if (value !== null && value !== undefined && value !== '') {
            params.append(key, value);
        }
    });

    try {
        const response = await fetch(`/api/candidates?${params.toString()}`);
        const result = await response.json();
        if (!response.ok || !result.success) {
            return;
        }

        state.candidates = result.candidates || [];
        if (Object.keys(filters).length > 0) {
            state.filteredCandidatePage = 1;
        } else {
            state.candidatePage = Math.min(state.candidatePage || 1, Math.max(1, Math.ceil(state.candidates.length / CANDIDATES_PAGE_SIZE)));
        }
        renderCandidatesTable('candidatesTable', state.candidates, false);

        if (Object.keys(filters).length > 0) {
            state.filteredCandidates = result.candidates || [];
            document.getElementById('filteredResults').style.display = 'block';
            renderCandidatesTable('filteredTable', state.filteredCandidates, false);
        }
    } catch (error) {
        console.error('Failed to load candidates:', error);
    }
}

function renderStatsSummary() {
    const total = state.stats.total_applicants || 0;
    const avg = Number(state.stats.average_score || 0);
    const topScore = state.topCandidates.length ? Number(state.topCandidates[0]['Final Score (%)'] || 0) : 0;

    document.getElementById('total-applicants').textContent = total;
    document.getElementById('avg-score').textContent = `${avg.toFixed(1)}%`;
    document.getElementById('top-score').textContent = `${topScore.toFixed(1)}%`;
}

function renderTopCandidates() {
    const container = document.getElementById('top-candidates');

    if (!state.topCandidates.length) {
        container.innerHTML = '<div class="empty-state">No candidates yet. Upload CVs to start ranking.</div>';
        return;
    }

    container.innerHTML = state.topCandidates
        .map((candidate, index) => {
            const first = candidate['First Name'] || '';
            const last = candidate['Last Name'] || '';
            const email = candidate['Email'] || '';
            const identifier = candidateIdentifier(candidate);
            const score = Number(candidate['Final Score (%)'] || 0);
            return `
                <div class="candidate-item" onclick="openCandidateModal('${encodeURIComponent(identifier)}')">
                    <div class="candidate-info">
                        <div class="candidate-name">${index + 1}. ${escapeHtml(`${first} ${last}`.trim())}</div>
                        <div class="candidate-email">${escapeHtml(email || 'No email on file')}</div>
                    </div>
                    <div class="candidate-score">${score.toFixed(1)}%</div>
                </div>
            `;
        })
        .join('');
}

function renderCharts() {
    const stats = state.stats;

    createOrUpdateChart('scoreChart', 'bar', stats.score_distribution || {}, {
        label: 'Candidates',
        backgroundColor: '#22489A'
    });

    createOrUpdateChart('genderChart', 'pie', stats.gender_distribution || {}, {
        backgroundColor: chartPalette
    });

    const locationData = topN(stats.location_distribution || {}, 8);
    createOrUpdateChart('locationChart', 'bar', locationData, {
        label: 'Applicants',
        backgroundColor: '#32B24B'
    });

    const skillsData = topN(stats.skills_frequency || {}, 10);
    createOrUpdateChart('skillsChart', 'bar', skillsData, {
        label: 'Frequency',
        backgroundColor: '#FF9F1C'
    });

    createOrUpdateChart('educationChart', 'doughnut', stats.education_distribution || {}, {
        backgroundColor: chartPalette
    });

    createOrUpdateChart('experienceChart', 'bar', stats.experience_distribution || {}, {
        label: 'Candidates',
        backgroundColor: '#3058A6'
    });

    createOrUpdateChart('requirementsFitChart', 'bar', stats.requirements_fit_distribution || {}, {
        label: 'Count',
        backgroundColor: ['#93C5FD', '#2ECC71']
    });
}

function createOrUpdateChart(canvasId, type, dataObject, style = {}) {
    const labels = Object.keys(dataObject);
    const data = Object.values(dataObject);
    const element = document.getElementById(canvasId);

    if (!element) {
        return;
    }

    if (state.charts[canvasId]) {
        state.charts[canvasId].destroy();
    }

    if (!labels.length) {
        const ctx = element.getContext('2d');
        ctx.clearRect(0, 0, element.width, element.height);
        return;
    }

    state.charts[canvasId] = new Chart(element, {
        type,
        data: {
            labels,
            datasets: [
                {
                    label: style.label || 'Value',
                    data,
                    borderColor: style.borderColor || '#22489A',
                    backgroundColor: style.backgroundColor || chartPalette,
                    fill: style.fill || false,
                    tension: style.tension || 0
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    display: type === 'pie' || type === 'doughnut'
                }
            }
        }
    });
}

function renderCandidatesTable(containerId, candidates, includeActions) {
    const container = document.getElementById(containerId);

    if (!candidates.length) {
        container.innerHTML = '<div class="empty-state">No candidates found for this view.</div>';
        return;
    }

    if (containerId === 'filteredTable') {
        renderFilteredCandidateCards(container, candidates);
        return;
    }

    const isAllCandidatesView = containerId === 'candidatesTable';
    const pageKey = containerId === 'filteredTable' ? 'filteredCandidatePage' : 'candidatePage';
    const totalPages = Math.max(1, Math.ceil(candidates.length / CANDIDATES_PAGE_SIZE));
    const requestedPage = Number(state[pageKey] || 1);
    const currentPage = Math.min(Math.max(1, requestedPage), totalPages);
    state[pageKey] = currentPage;
    const startIndex = (currentPage - 1) * CANDIDATES_PAGE_SIZE;
    const pageCandidates = candidates.slice(startIndex, startIndex + CANDIDATES_PAGE_SIZE);

    const headers = isAllCandidatesView
        ? ['Name', 'Email', 'Contact Number', 'CV File Name']
        : ['Name', 'Email', 'Gender', 'Age', 'Location', 'Education', 'Experience', 'Skills', 'Final Score', 'Applied Job', 'Match'];

    const rows = pageCandidates
        .map((candidate) => {
            const email = candidate['Email'] || '';
            const name = `${candidate['First Name'] || ''} ${candidate['Last Name'] || ''}`.trim();
            const identifier = candidateIdentifier(candidate);
            const score = Number(candidate['Final Score (%)'] || 0);
            const badge = scoreClass(score);
            const phone = candidate['Phone'] || '';

            const cvFileName = candidate['CV File Name'] || candidate['file_name'] || '';
            if (isAllCandidatesView) {
                const safeLink = cvFileName ? `<a href="/api/download-candidate-cv/${encodeURIComponent(identifier)}" target="_blank" rel="noopener noreferrer">${escapeHtml(cvFileName)}</a>` : '-';
                return `
                    <tr>
                        <td>${escapeHtml(name || 'N/A')}</td>
                        <td>${escapeHtml(email || 'No email on file')}</td>
                        <td>${escapeHtml(phone || '-')}</td>
                        <td>${safeLink}</td>
                    </tr>
                `;
            }

            return `
                <tr>
                    <td>${escapeHtml(name || 'N/A')}</td>
                    <td>${escapeHtml(email)}</td>
                    <td>${escapeHtml(candidate['Gender'] || 'Not specified')}</td>
                    <td>${escapeHtml(String(candidate['Age'] || ''))}</td>
                    <td>${escapeHtml(`${candidate['City'] || ''}, ${candidate['Country'] || ''}`.replace(/^,\s*/, ''))}</td>
                    <td>${escapeHtml(candidate['Education Level'] || 'Unknown')}</td>
                    <td>${escapeHtml(String(candidate['Years of Experience'] || 0))} yrs</td>
                    <td>${escapeHtml(candidate['Skills'] || '')}</td>
                    <td><span class="score ${badge}">${score.toFixed(1)}%</span></td>
                    <td>${escapeHtml(candidate['Applied Job Title'] || '-')}</td>
                    <td>${Number(candidate['Match Score (%)'] || 0).toFixed(1)}%</td>
                    ${includeActions && !isAllCandidatesView ? `<td>
                        <button class="btn-secondary" onclick="openCandidateModal('${encodeURIComponent(identifier)}')">View</button>
                        <button class="btn-danger" onclick="deleteCandidate('${encodeURIComponent(identifier)}')">Delete</button>
                    </td>` : ''}
                </tr>
            `;
        })
        .join('');

    const pagination = totalPages > 1
        ? `
            <div class="pagination-bar">
                <div class="pagination-info">
                    Showing ${startIndex + 1}-${Math.min(startIndex + CANDIDATES_PAGE_SIZE, candidates.length)} of ${candidates.length}
                </div>
                <div class="pagination-actions">
                    <button class="btn-secondary pagination-btn" ${currentPage === 1 ? 'disabled' : ''} onclick="goToCandidatePage('${containerId}', ${currentPage - 1})">Prev</button>
                    <span class="pagination-page">Page ${currentPage} of ${totalPages}</span>
                    <button class="btn-secondary pagination-btn" ${currentPage === totalPages ? 'disabled' : ''} onclick="goToCandidatePage('${containerId}', ${currentPage + 1})">Next</button>
                </div>
            </div>
        `
        : '';

    container.innerHTML = `
        <table>
            <thead>
                <tr>
                    ${headers.map((h) => `<th>${h}</th>`).join('')}
                            ${includeActions && !isAllCandidatesView ? '<th>Actions</th>' : ''}
                </tr>
            </thead>
            <tbody>${rows}</tbody>
        </table>
        ${pagination}
    `;
}

function renderFilteredCandidateCards(container, candidates) {
    const pageKey = 'filteredCandidatePage';
    const totalPages = Math.max(1, Math.ceil(candidates.length / CANDIDATES_PAGE_SIZE));
    const requestedPage = Number(state[pageKey] || 1);
    const currentPage = Math.min(Math.max(1, requestedPage), totalPages);
    state[pageKey] = currentPage;
    const startIndex = (currentPage - 1) * CANDIDATES_PAGE_SIZE;
    const pageCandidates = candidates.slice(startIndex, startIndex + CANDIDATES_PAGE_SIZE);

    const rows = pageCandidates
        .map((candidate, index) => {
            const identifier = candidateIdentifier(candidate);
            const name = `${candidate['First Name'] || ''} ${candidate['Last Name'] || ''}`.trim() || candidate.Name || 'N/A';
            const email = candidate['Email'] || 'No email on file';
            const score = Number(candidate['Final Score (%)'] || 0).toFixed(1);
            const matchScore = Number(candidate['Match Score (%)'] || 0).toFixed(1);
            const resumeBtn = `<a class="btn-resume btn-small" href="/api/download-candidate-cv/${encodeURIComponent(identifier)}" target="_blank" rel="noopener noreferrer">Resume</a>`;

            return `
                <div class="candidate-item candidate-card" style="align-items: stretch; gap: 12px; flex-direction: column;">
                    <div style="display:flex; justify-content:space-between; gap: 12px; align-items:flex-start;">
                        <div class="candidate-info" style="min-width: 0;">
                            <div class="candidate-name">${index + startIndex + 1}. ${escapeHtml(name)}</div>
                            <div class="candidate-email">${escapeHtml(email)}</div>
                        </div>
                        <div style="display:flex; gap:8px; flex-wrap:wrap; justify-content:flex-end;">
                            <button class="btn-primary btn-small" onclick="openCandidateModal('${encodeURIComponent(identifier)}')">View</button>
                            ${resumeBtn}
                        </div>
                    </div>
                    <div class="candidate-card-chips">
                        <span class="job-pill">CV Score: ${score}%</span>
                        <span class="job-pill">Match Score: ${matchScore}%</span>
                    </div>
                </div>
            `;
        })
        .join('');

    const pagination = totalPages > 1
        ? `
            <div class="pagination-bar">
                <div class="pagination-info">
                    Showing ${startIndex + 1}-${Math.min(startIndex + CANDIDATES_PAGE_SIZE, candidates.length)} of ${candidates.length}
                </div>
                <div class="pagination-actions">
                    <button class="btn-secondary pagination-btn" ${currentPage === 1 ? 'disabled' : ''} onclick="goToCandidatePage('filteredTable', ${currentPage - 1})">Prev</button>
                    <span class="pagination-page">Page ${currentPage} of ${totalPages}</span>
                    <button class="btn-secondary pagination-btn" ${currentPage === totalPages ? 'disabled' : ''} onclick="goToCandidatePage('filteredTable', ${currentPage + 1})">Next</button>
                </div>
            </div>
        `
        : '';

    container.innerHTML = `
        <div class="candidate-results-grid">
            ${rows}
        </div>
        ${pagination}
    `;
}

function goToCandidatePage(containerId, pageNumber) {
    const targetPage = Math.max(1, Number(pageNumber) || 1);
    const pageKey = containerId === 'filteredTable' ? 'filteredCandidatePage' : 'candidatePage';
    state[pageKey] = targetPage;

    if (containerId === 'filteredTable') {
        renderCandidatesTable('filteredTable', state.filteredCandidates, false);
        return;
    }

    renderCandidatesTable('candidatesTable', state.candidates, false);
}

async function openCandidateModal(encodedEmail) {
    const email = decodeURIComponent(encodedEmail);

    try {
        const response = await fetch(`/api/candidate/${encodeURIComponent(email)}`);
        const result = await response.json();

        if (!response.ok || !result.success) {
            return;
        }

        const candidate = result.candidate;
        const details = document.getElementById('candidateDetail');
        details.innerHTML = `
            <h3>${escapeHtml(`${candidate['First Name'] || ''} ${candidate['Last Name'] || ''}`.trim())}</h3>
            <div class="detail-section">
                <h4>Profile</h4>
                ${detailRow('Email', candidate['Email'])}
                ${detailRow('Phone', candidate['Phone'])}
                ${detailRow('Gender', candidate['Gender'])}
                ${detailRow('Age/DOB', candidate['Age/DOB'])}
                ${detailRow('City', candidate['City'])}
                ${detailRow('Country', candidate['Country'])}
            </div>
            <div class="detail-section">
                <h4>Education & Experience</h4>
                ${detailRow('Education', candidate['Education'])}
                ${detailRow('Education Level', candidate['Education Level'])}
                ${detailRow('Years of Experience', candidate['Years of Experience'])}
                ${detailRow('Current Role', candidate['Current Role'])}
            </div>
            <div class="detail-section">
                <h4>Scoring</h4>
                ${detailRow('Identity Score', candidate['Identity Score'])}
                ${detailRow('Address Score', candidate['Address Score'])}
                ${detailRow('Education Score', candidate['Education Score'])}
                ${detailRow('Experience Score', candidate['Experience Score'])}
                ${detailRow('Skills Score', candidate['Skills Score'])}
                ${detailRow('Final Score', `${Number(candidate['Final Score (%)'] || 0).toFixed(1)}%`)}
                ${detailRow('Applied Job', candidate['Applied Job Title'])}
                ${detailRow('Job Match Score', `${Number(candidate['Match Score (%)'] || 0).toFixed(1)}%`)}
                ${detailRow('Match Source', candidate['Match Source'])}
            </div>
            <div class="detail-section">
                <h4>Skills</h4>
                ${detailRow('Skills', candidate['Skills'])}
            </div>
        `;

        document.getElementById('candidateModal').classList.add('show');
    } catch (error) {
        console.error('Failed to open candidate details:', error);
    }
}

function candidateIdentifier(candidate) {
    if (!candidate || typeof candidate !== 'object') {
        return '';
    }

    const email = candidate['Email'] || '';
    if (email) {
        return email;
    }

    const candidateKey = candidate['Candidate Key'] || '';
    if (candidateKey) {
        return candidateKey;
    }

    const name = candidate.Name || `${candidate['First Name'] || ''} ${candidate['Last Name'] || ''}`.trim();
    const phone = candidate['Phone'] || '';
    if (name && phone) {
        return `${name} ${phone}`.trim();
    }
    return name || phone || '';
}

function closeCandidateModal() {
    document.getElementById('candidateModal').classList.remove('show');
}

window.addEventListener('click', (event) => {
    const modal = document.getElementById('candidateModal');
    if (event.target === modal) {
        closeCandidateModal();
    }
});

async function deleteCandidate(encodedEmail) {
    const email = decodeURIComponent(encodedEmail);
    if (!confirm(`Delete candidate ${email}?`)) {
        return;
    }

    try {
        const response = await fetchWithCsrf(`/api/candidate/${encodeURIComponent(email)}`, {
            method: 'DELETE'
        });
        const result = await response.json();
        if (!response.ok || !result.success) {
            alert(result.error || 'Delete failed.');
            return;
        }

        await Promise.all([loadDashboard(), loadCandidates()]);
    } catch (error) {
        console.error('Failed to delete candidate:', error);
    }
}

async function applyFilters() {
    const filters = {
        search: valueOf('searchInput'),
        min_score: valueOf('scoreRangeMin'),
        max_score: valueOf('scoreRangeMax'),
        gender: valueOf('genderFilter'),
        country: valueOf('countryFilter'),
        city: valueOf('cityFilter'),
        education_level: valueOf('educationFilter'),
        skill: valueOf('skillFilter'),
        min_experience: valueOf('minExperience'),
        applied_job_title: valueOf('jobFilter'),
        has_driver_license: valueOf('driverLicenseFilter')
    };

    await loadCandidates(filters);
}

function resetFilters() {
    [
        'searchInput',
        'scoreRangeMin',
        'scoreRangeMax',
        'genderFilter',
        'countryFilter',
        'cityFilter',
        'educationFilter',
        'skillFilter',
        'minExperience',
        'driverLicenseFilter'
    ].forEach((id) => {
        const element = document.getElementById(id);
        if (element) {
            element.value = '';
        }
    });

    document.getElementById('filteredResults').style.display = 'none';
    state.candidatePage = 1;
    state.filteredCandidatePage = 1;
    loadCandidates();
}

async function exportFiltered() {
    const data = state.filteredCandidates.length ? state.filteredCandidates : state.candidates;

    if (!data.length) {
        alert('No records available to export.');
        return;
    }

    try {
        const response = await fetchWithCsrf('/api/export-download', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ data })
        });

        if (!response.ok) {
            let message = 'Export failed.';
            try {
                const result = await response.json();
                message = result.error || message;
            } catch (e) {
                message = 'Export failed.';
            }
            alert(message);
            return;
        }

        const blob = await response.blob();
        const downloadUrl = window.URL.createObjectURL(blob);
        const disposition = response.headers.get('Content-Disposition') || '';
        const filenameMatch = disposition.match(/filename="?([^";]+)"?/i);
        const filename = filenameMatch ? filenameMatch[1] : 'filtered_candidates.xlsx';

        const anchor = document.createElement('a');
        anchor.href = downloadUrl;
        anchor.download = filename;
        document.body.appendChild(anchor);
        anchor.click();
        anchor.remove();
        window.URL.revokeObjectURL(downloadUrl);
    } catch (error) {
        alert(`Export failed: ${error.message}`);
    }
}

function downloadExcel() {
    window.location.href = '/api/download-excel';
}

async function downloadActiveJobMatches() {
    if (!state.activeJob || !state.activeJob['Job ID']) {
        alert('No active job selected. Set a job as active first.');
        return;
    }

    try {
        const response = await fetch('/api/jobs/active/matches/download');

        if (!response.ok) {
            let message = 'Failed to download active job applications.';
            try {
                const result = await response.json();
                message = result.error || message;
            } catch (e) {
                message = 'Failed to download active job applications.';
            }
            alert(message);
            return;
        }

        const blob = await response.blob();
        const downloadUrl = window.URL.createObjectURL(blob);
        const disposition = response.headers.get('Content-Disposition') || '';
        const filenameMatch = disposition.match(/filename="?([^";]+)"?/i);
        const filename = filenameMatch ? filenameMatch[1] : 'active_job_applications.xlsx';

        const anchor = document.createElement('a');
        anchor.href = downloadUrl;
        anchor.download = filename;
        document.body.appendChild(anchor);
        anchor.click();
        anchor.remove();
        window.URL.revokeObjectURL(downloadUrl);
    } catch (error) {
        alert(`Failed to download active job applications: ${error.message}`);
    }
}

function detailRow(label, value) {
    return `
        <div class="detail-item">
            <span class="detail-label">${escapeHtml(String(label || ''))}</span>
            <span class="detail-value">${escapeHtml(String(value || 'N/A'))}</span>
        </div>
    `;
}

function scoreClass(score) {
    if (score >= 85) {
        return 'excellent';
    }
    if (score >= 70) {
        return 'good';
    }
    if (score >= 55) {
        return 'fair';
    }
    return 'poor';
}

function toTitleCase(value) {
    return String(value)
        .replace(/[-_]/g, ' ')
        .replace(/\w\S*/g, (txt) => txt.charAt(0).toUpperCase() + txt.substring(1).toLowerCase());
}

function topN(dataObject, limit) {
    return Object.fromEntries(
        Object.entries(dataObject)
            .sort((a, b) => b[1] - a[1])
            .slice(0, limit)
    );
}

function valueOf(id) {
    const element = document.getElementById(id);
    if (!element) {
        return '';
    }
    return String(element.value || '').trim();
}

function escapeHtml(value) {
    return String(value || '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

function truncateText(value, maxLength) {
    const text = String(value || '');
    if (text.length <= maxLength) {
        return text;
    }
    return `${text.slice(0, maxLength).trim()}...`;
}

window.applyFilters = applyFilters;
window.resetFilters = resetFilters;
window.exportFiltered = exportFiltered;
window.downloadExcel = downloadExcel;
window.downloadActiveJobMatches = downloadActiveJobMatches;
window.loadActiveJobReport = loadActiveJobReport;
window.deleteJob = deleteJob;
window.resetSystemData = resetSystemData;
window.openCandidateModal = openCandidateModal;
window.closeCandidateModal = closeCandidateModal;
window.deleteCandidate = deleteCandidate;
window.openJobModal = openJobModal;
window.resetJobForm = resetJobForm;
window.activateJob = activateJob;
