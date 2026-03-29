// Mobile nav toggle — runs on every page
document.addEventListener('DOMContentLoaded', () => {
    const toggle = document.querySelector('.nav-toggle');
    const links  = document.querySelector('nav .links');
    if (!toggle || !links) return;
    toggle.addEventListener('click', () => {
        const open = links.classList.toggle('open');
        toggle.setAttribute('aria-expanded', String(open));
    });
    // Close when any nav link/button is tapped
    links.addEventListener('click', (e) => {
        if (e.target.closest('a, button')) {
            links.classList.remove('open');
            toggle.setAttribute('aria-expanded', 'false');
        }
    });
    // Close when user taps outside the nav
    document.addEventListener('click', (e) => {
        if (!e.target.closest('nav')) {
            links.classList.remove('open');
            toggle.setAttribute('aria-expanded', 'false');
        }
    });
});

const API = {
    token: localStorage.getItem('aw_token'),
    async req(method, path, body) {
        const h = { 'Content-Type': 'application/json' };
        if (this.token) h['Authorization'] = `Bearer ${this.token}`;
        const opts = { method, headers: h };
        if (body) opts.body = JSON.stringify(body);
        const res = await fetch(`/api${path}`, opts);
        if (res.status === 401) { this.logout(); return null; }
        if (res.status === 204) return null;
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Request failed');
        return data;
    },
    setToken(t) { this.token = t; localStorage.setItem('aw_token', t); },
    logout() { this.token = null; localStorage.removeItem('aw_token'); window.location.href = '/login'; },
    isLoggedIn() { return !!this.token; }
};

function esc(s) { const d = document.createElement('div'); d.textContent = s; return d.innerHTML; }
function scoreClass(s) { if (s >= 80) return 'score-good'; if (s >= 50) return 'score-ok'; return 'score-bad'; }
function timeAgo(d) {
    if (!d) return 'Never';
    const s = Math.floor((Date.now() - new Date(d)) / 1000);
    if (s < 60) return 'just now'; if (s < 3600) return Math.floor(s/60) + 'm ago';
    if (s < 86400) return Math.floor(s/3600) + 'h ago'; return Math.floor(s/86400) + 'd ago';
}
const _TOAST_ICONS = { success: '✓', error: '✕', info: 'ℹ', warning: '⚠' };

function showToast(msg, type = 'success', duration = 4000) {
    let region = document.getElementById('toast-region');
    if (!region) {
        region = document.createElement('div');
        region.id = 'toast-region';
        region.className = 'toast-region';
        region.setAttribute('role', 'log');
        region.setAttribute('aria-label', 'Notifications');
        region.setAttribute('aria-atomic', 'false');
        document.body.appendChild(region);
    }
    // Errors interrupt screen readers immediately; all others politely queue
    region.setAttribute('aria-live', type === 'error' ? 'assertive' : 'polite');

    // Evict oldest when over limit
    while (region.children.length >= 5) _dismissToast(region.firstElementChild);

    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.setAttribute('role', 'status');
    toast.innerHTML =
        `<span class="toast-icon" aria-hidden="true">${_TOAST_ICONS[type] || _TOAST_ICONS.info}</span>` +
        `<span class="toast-msg">${esc(msg)}</span>` +
        `<button class="toast-close" type="button" aria-label="Dismiss notification">&#215;</button>` +
        `<div class="toast-bar" aria-hidden="true"></div>`;
    region.appendChild(toast);

    const bar = toast.querySelector('.toast-bar');
    if (duration > 0) {
        bar.style.animation = `toast-shrink ${duration}ms linear forwards`;
        toast._timer = setTimeout(() => _dismissToast(toast), duration);
    }

    toast.querySelector('.toast-close').addEventListener('click', () => _dismissToast(toast));

    // Pause the countdown while the user hovers over the toast
    toast.addEventListener('mouseenter', () => {
        clearTimeout(toast._timer);
        bar.style.animationPlayState = 'paused';
    });
    toast.addEventListener('mouseleave', () => {
        if (!toast.classList.contains('toast-out')) {
            bar.style.animationPlayState = 'running';
            toast._timer = setTimeout(() => _dismissToast(toast), 1200);
        }
    });
}

function _dismissToast(toast) {
    if (!toast || toast.classList.contains('toast-out')) return;
    clearTimeout(toast._timer);
    toast.classList.add('toast-out');
    toast.addEventListener('animationend', () => toast.remove(), { once: true });
}

// ── Animations & Transitions (Track B #8) ──────────────────────────────────

/**
 * Animate a stat counter from 0 to `target`.
 * Respects prefers-reduced-motion — skips animation when user prefers less motion.
 * @param {HTMLElement} el      - Target element whose textContent will be updated
 * @param {number|null} target  - Final numeric value (null → shows '--')
 * @param {number} duration     - Animation duration in ms (default 600)
 */
function animateCounter(el, target, duration = 600) {
    if (target === null || target === undefined) { el.textContent = '--'; return; }
    const num = +target;
    if (isNaN(num)) { el.textContent = target; return; }
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
        el.textContent = target;
        return;
    }
    el.classList.add('counting');
    const start = performance.now();
    const tick = (now) => {
        const p = Math.min((now - start) / duration, 1);
        const eased = 1 - Math.pow(1 - p, 3); // ease-out cubic
        el.textContent = Math.round(num * eased);
        if (p < 1) { requestAnimationFrame(tick); }
        else { el.textContent = target; el.classList.remove('counting'); }
    };
    requestAnimationFrame(tick);
}

/**
 * Observe `.reveal` elements and add `.visible` when they enter the viewport.
 * Safe to call multiple times; won't re-observe already-visible elements.
 */
function initReveal() {
    const els = document.querySelectorAll('.reveal:not(.visible)');
    if (!els.length) return;
    if (!('IntersectionObserver' in window)) {
        // Fallback: make everything visible immediately
        els.forEach(el => el.classList.add('visible'));
        return;
    }
    const obs = new IntersectionObserver((entries) => {
        entries.forEach(e => {
            if (e.isIntersecting) { e.target.classList.add('visible'); obs.unobserve(e.target); }
        });
    }, { threshold: 0.1, rootMargin: '0px 0px -32px 0px' });
    els.forEach(el => obs.observe(el));
}

// Auto-init reveal on every page load
document.addEventListener('DOMContentLoaded', initReveal);

// Skeleton helpers
function skSiteCards(n) {
    return Array.from({length: n}, () => `
        <div class="site-card" aria-hidden="true" style="pointer-events:none">
            <div class="site-info">
                <div class="sk" style="width:56px;height:56px;border-radius:50%;flex-shrink:0"></div>
                <div style="display:flex;flex-direction:column;gap:8px;flex:1">
                    <div class="sk" style="height:14px;width:50%"></div>
                    <div class="sk" style="height:11px;width:35%"></div>
                </div>
            </div>
            <div style="display:flex;gap:10px">
                <div class="sk" style="height:32px;width:84px;border-radius:8px"></div>
                <div class="sk" style="height:32px;width:68px;border-radius:8px"></div>
            </div>
        </div>`).join('');
}

function skIssueCards(n) {
    const w = [75, 65, 80, 60];
    return Array.from({length: n}, (_, i) => `
        <div class="issue-card" aria-hidden="true">
            <div style="display:flex;gap:8px;margin-bottom:10px">
                <div class="sk" style="height:22px;width:72px;border-radius:100px"></div>
                <div class="sk" style="height:22px;width:88px"></div>
            </div>
            <div class="sk" style="height:14px;width:${w[i % 4]}%;margin-bottom:8px"></div>
            <div class="sk" style="height:11px;width:${w[(i + 2) % 4] - 20}%"></div>
        </div>`).join('');
}

// Inline field validation helpers
function setFieldError(inputEl, message) {
    inputEl.classList.add('input-invalid');
    inputEl.classList.remove('input-valid');
    inputEl.setAttribute('aria-invalid', 'true');
    const group = inputEl.closest('.form-group');
    let errEl = group.querySelector('.field-error');
    if (!errEl) {
        errEl = document.createElement('div');
        errEl.className = 'field-error';
        errEl.setAttribute('role', 'alert');
        errEl.id = (inputEl.id || inputEl.name) + '-error';
        inputEl.setAttribute('aria-describedby', errEl.id);
        group.appendChild(errEl);
    }
    errEl.textContent = message;
    errEl.classList.add('visible');
}
function clearFieldError(inputEl) {
    inputEl.classList.remove('input-invalid');
    inputEl.removeAttribute('aria-invalid');
    const errEl = inputEl.closest('.form-group')?.querySelector('.field-error');
    if (errEl) errEl.classList.remove('visible');
}
function setFieldValid(inputEl) {
    inputEl.classList.add('input-valid');
    inputEl.classList.remove('input-invalid');
    clearFieldError(inputEl);
}
function validateEmailField(inputEl) {
    const v = inputEl.value.trim();
    if (!v) { setFieldError(inputEl, 'Email is required'); return false; }
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v)) { setFieldError(inputEl, 'Enter a valid email address'); return false; }
    setFieldValid(inputEl); return true;
}
function validatePasswordField(inputEl, minLen = 8) {
    const v = inputEl.value;
    if (!v) { setFieldError(inputEl, 'Password is required'); return false; }
    if (v.length < minLen) { setFieldError(inputEl, `Password must be at least ${minLen} characters`); return false; }
    setFieldValid(inputEl); return true;
}
function validateRequiredField(inputEl, label) {
    const v = inputEl.value.trim();
    if (!v) { setFieldError(inputEl, `${label} is required`); return false; }
    setFieldValid(inputEl); return true;
}
function validateURLField(inputEl) {
    const v = inputEl.value.trim();
    if (!v) { setFieldError(inputEl, 'URL is required'); return false; }
    try {
        const url = new URL(v);
        if (!['http:', 'https:'].includes(url.protocol)) { setFieldError(inputEl, 'URL must start with http:// or https://'); return false; }
    } catch { setFieldError(inputEl, 'Enter a valid URL (e.g. https://example.com)'); return false; }
    setFieldValid(inputEl); return true;
}
function clearFormValidation(form) {
    form.querySelectorAll('input').forEach(el => {
        el.classList.remove('input-valid', 'input-invalid');
        el.removeAttribute('aria-invalid');
        el.removeAttribute('aria-describedby');
        const errEl = el.closest('.form-group')?.querySelector('.field-error');
        if (errEl) errEl.classList.remove('visible');
    });
}

// Auth
function initAuth(type) {
    if (API.isLoggedIn()) { window.location.href = '/dashboard'; return; }
    const form = document.getElementById('auth-form');
    const globalErr = document.getElementById('error-msg');
    if (!form) return;

    const emailInput = form.querySelector('#email');
    const passwordInput = form.querySelector('#password');

    // Validate on blur so users get feedback as they fill the form
    emailInput?.addEventListener('blur', () => { if (emailInput.value) validateEmailField(emailInput); });
    emailInput?.addEventListener('focus', () => clearFieldError(emailInput));
    if (type === 'register') {
        passwordInput?.addEventListener('blur', () => { if (passwordInput.value) validatePasswordField(passwordInput); });
        passwordInput?.addEventListener('focus', () => clearFieldError(passwordInput));
    }

    form.addEventListener('submit', async (e) => {
        e.preventDefault(); err.style.display = 'none';
        const btn = form.querySelector('button[type=submit]');
        const origText = btn.innerHTML;
        btn.disabled = true;
        btn.innerHTML = `<span class="spinner" aria-hidden="true"></span>${type === 'register' ? 'Creating account\u2026' : 'Signing in\u2026'}`;
        e.preventDefault();
        globalErr.style.display = 'none';

        // Validate all fields before submitting
        const emailOk = validateEmailField(emailInput);
        const pwOk = type === 'register' ? validatePasswordField(passwordInput) : validateRequiredField(passwordInput, 'Password');
        if (!emailOk || !pwOk) return;

        const btn = form.querySelector('button[type=submit]');
        const origLabel = btn.textContent;
        btn.disabled = true;
        btn.textContent = type === 'register' ? 'Creating account\u2026' : 'Signing in\u2026';
        try {
            let data;
            if (type === 'register') {
                data = await API.req('POST', '/auth/register', { email: emailInput.value.trim(), password: passwordInput.value });
            } else {
                const fd = new URLSearchParams();
                fd.append('username', emailInput.value.trim());
                fd.append('password', passwordInput.value);
                const r = await fetch('/api/auth/login', { method: 'POST', body: fd });
                data = await r.json();
                if (!r.ok) throw new Error(data.detail || 'Login failed');
            }
            API.setToken(data.access_token); window.location.href = '/dashboard';
        } catch (e) { err.textContent = e.message; err.style.display = 'block'; btn.disabled = false; btn.innerHTML = origText; }
        } catch (err) {
            globalErr.textContent = err.message;
            globalErr.style.display = 'block';
            btn.disabled = false;
            btn.textContent = origLabel;
        }
    });
}

// Dashboard
let currentView = 'sites'; // sites, scan-detail
let currentSiteId = null;
let currentScanId = null;
let _scoreTrendChart = null;
let _severityChart = null;
let currentScan = null;
let currentIssues = [];

async function initDashboard() {
    if (!API.isLoggedIn()) { window.location.href = '/login'; return; }
    document.getElementById('logout-btn')?.addEventListener('click', () => API.logout());
    document.getElementById('add-site-btn')?.addEventListener('click', () => document.getElementById('add-modal').classList.add('active'));
    document.getElementById('close-modal')?.addEventListener('click', () => {
        document.getElementById('add-modal').classList.remove('active');
        const form = document.getElementById('site-form');
        if (form) { form.reset(); clearFormValidation(form); }
    });
    document.getElementById('site-form')?.addEventListener('submit', addSite);
    document.getElementById('close-edit-modal')?.addEventListener('click', () => document.getElementById('edit-modal').classList.remove('active'));
    document.getElementById('edit-site-form')?.addEventListener('submit', saveEditSite);
    // Close modals when clicking the backdrop
    document.getElementById('add-modal')?.addEventListener('click', e => { if (e.target === e.currentTarget) e.currentTarget.classList.remove('active'); });
    document.getElementById('edit-modal')?.addEventListener('click', e => { if (e.target === e.currentTarget) e.currentTarget.classList.remove('active'); });
    await loadStats();
    await Promise.all([loadSites(), loadCharts()]);
}

function setStatVal(id, val) {
    const el = document.getElementById(id);
    if (!el) return;
    el.classList.remove('sk');
    el.textContent = val;
}

async function loadStats() {
    const ids = ['stat-sites', 'stat-scans', 'stat-score', 'stat-issues', 'stat-critical'];
    ids.forEach(id => { const el = document.getElementById(id); if (el) el.classList.add('sk'); });
    try {
        const s = await API.req('GET', '/dashboard/stats');
        if (!s) return;
        animateCounter(document.getElementById('stat-sites'), s.total_sites);
        animateCounter(document.getElementById('stat-scans'), s.total_scans);
        document.getElementById('stat-score').textContent = s.avg_score !== null ? s.avg_score : '--';
        animateCounter(document.getElementById('stat-issues'), s.total_issues);
        animateCounter(document.getElementById('stat-critical'), s.critical_issues);
    } catch (e) { console.error(e); }
        setStatVal('stat-sites', s.total_sites);
        setStatVal('stat-scans', s.total_scans);
        setStatVal('stat-score', s.avg_score !== null ? s.avg_score : '--');
        setStatVal('stat-issues', s.total_issues);
        setStatVal('stat-critical', s.critical_issues);
    } catch (e) { ids.forEach(id => { const el = document.getElementById(id); if (el) el.classList.remove('sk'); }); console.error(e); }
}

async function loadSites() {
    const el = document.getElementById('main-content');
    el.innerHTML = `<div class="sites-list" aria-busy="true" aria-label="Loading sites">${skSiteCards(3)}</div>`;
    try {
        const sites = await API.req('GET', '/sites');
        if (!sites?.length) {
            el.innerHTML = `<div class="empty-state"><div class="icon">\uD83C\uDF10</div><p>No sites added yet</p><p style="font-size:0.88rem">Add your first website to scan for accessibility issues.</p></div>`;
            return;
        }
        el.innerHTML = `<div class="sites-list">${sites.map(s => `
            <div class="site-card" onclick="openSite(${s.id})">
                <div class="site-info">
                    ${s.last_score !== null ? `<div class="score-ring ${scoreClass(s.last_score)}">${s.last_score.toFixed(0)}</div>` : `<div class="score-ring" style="background:var(--surface-2);color:var(--text-dim);border-color:var(--border)">--</div>`}
                    <div><div class="name">${esc(s.name)}</div><div class="url">${esc(s.url)}</div></div>
                </div>
                <div class="site-meta">
                    <span class="last-scan">${s.last_scan_at ? 'Scanned ' + timeAgo(s.last_scan_at) : 'Not scanned'}</span>
                    <button class="btn btn-sm btn-green" onclick="event.stopPropagation();startScan(${s.id})">Scan Now</button>
                    <button class="btn btn-sm btn-edit" aria-label="Edit ${esc(s.name)}" onclick="event.stopPropagation();openEditSite(${s.id},'${esc(s.name).replace(/'/g,"\\'")}','${esc(s.url).replace(/'/g,"\\'")}')">Edit</button>
                    <button class="btn btn-sm btn-green" onclick="event.stopPropagation();startScan(${s.id},this)">Scan Now</button>
                    <button class="btn btn-sm btn-danger" onclick="event.stopPropagation();deleteSite(${s.id})">Delete</button>
                </div>
            </div>`).join('')}</div>`;
    } catch (e) { console.error(e); }
}

async function openSite(siteId) {
    currentSiteId = siteId;
    const el = document.getElementById('main-content');
    el.innerHTML = `<a href="#" class="back-link" onclick="loadSites();return false">&larr; Back to sites</a>
        <div class="sites-list" aria-busy="true" aria-label="Loading scans">${skSiteCards(3)}</div>`;
    try {
        const scans = await API.req('GET', `/sites/${siteId}/scans`);
        const sites = await API.req('GET', '/sites');
        const site = sites.find(s => s.id === siteId);
        if (!scans?.length) {
            el.innerHTML = `<a href="#" class="back-link" onclick="loadSites();return false">&larr; Back to sites</a>
                <div class="empty-state"><div class="icon">\uD83D\uDD0D</div><p>No scans yet for ${esc(site?.name || '')}</p>
                <button class="btn btn-green" onclick="startScan(${siteId},this)">Run First Scan</button></div>`;
            return;
        }
        el.innerHTML = `<a href="#" class="back-link" onclick="loadSites();return false">&larr; Back to sites</a>
            <h2 style="margin-bottom:16px">${esc(site?.name || '')}</h2>
            <div class="sites-list">${scans.map(s => `
                <div class="site-card" onclick="openScan(${s.id})">
                    <div class="site-info">
                        ${s.score !== null ? `<div class="score-ring ${scoreClass(s.score)}">${s.score.toFixed(0)}</div>` : `<div class="score-ring" style="background:var(--surface-2);color:var(--text-dim);border-color:var(--border)">${s.status === 'running' ? '...' : '--'}</div>`}
                        <div>
                            <div class="name">Scan #${s.id} &mdash; ${s.status}</div>
                            <div class="url">${s.pages_scanned} pages, ${s.total_issues} issues &mdash; ${timeAgo(s.completed_at || s.created_at)}</div>
                        </div>
                    </div>
                    <div class="severity-bar">
                        ${s.critical_count ? `<span class="badge badge-critical">${s.critical_count} Critical</span>` : ''}
                        ${s.serious_count ? `<span class="badge badge-serious">${s.serious_count} Serious</span>` : ''}
                        ${s.moderate_count ? `<span class="badge badge-moderate">${s.moderate_count} Moderate</span>` : ''}
                        ${s.minor_count ? `<span class="badge badge-minor">${s.minor_count} Minor</span>` : ''}
                    </div>
                </div>`).join('')}</div>`;
    } catch (e) { console.error(e); }
}

async function openScan(scanId) {
    currentScanId = scanId;
    const el = document.getElementById('main-content');
    el.innerHTML = `
        <a href="#" class="back-link" onclick="openSite(${currentSiteId});return false">&larr; Back to scans</a>
        <div class="scan-detail" aria-busy="true" style="margin-bottom:20px">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px">
                <div class="sk" style="height:22px;width:120px"></div>
                <div class="sk" style="width:64px;height:64px;border-radius:50%"></div>
            </div>
            <div class="sk" style="height:13px;width:55%;margin-bottom:14px"></div>
            <div style="display:flex;gap:10px">
                ${Array.from({length: 4}, () => `<div class="sk" style="height:32px;width:90px;border-radius:8px"></div>`).join('')}
            </div>
        </div>
        <div class="sk" style="height:18px;width:130px;margin-bottom:12px"></div>
        <div class="issues-list" aria-busy="true" aria-label="Loading issues">${skIssueCards(4)}</div>`;
    try {
        const [scan, issues] = await Promise.all([
            API.req('GET', `/scans/${scanId}`),
            API.req('GET', `/scans/${scanId}/issues`),
        ]);

        const SEVERITIES = ['critical', 'serious', 'moderate', 'minor'];
        const grouped = { critical: [], serious: [], moderate: [], minor: [] };
        issues.forEach(i => { (grouped[i.severity] ?? grouped.minor).push(i); });

        function issueCard(i) {
            const uid = `i${i.id}`;
            const hasCode = !!i.element_html;
            const hasFix = !!i.how_to_fix;
            return `<div class="issue-card ${esc(i.severity)}">
                <div class="issue-header">
                    <span class="badge badge-${esc(i.severity)}">${esc(i.severity)}</span>
                    ${i.wcag_criteria ? `<span class="wcag">WCAG ${esc(i.wcag_criteria)}</span>` : ''}
                    <code class="issue-rule-id">${esc(i.rule_id)}</code>
                </div>
                <p class="issue-message">${esc(i.message)}</p>
                <p class="issue-page-url">${esc(i.page_url)}</p>
                ${i.selector ? `<code class="issue-selector" title="${esc(i.selector)}">${esc(i.selector)}</code>` : ''}
                ${hasCode || hasFix ? `<div class="issue-actions">
                    ${hasCode ? `<button class="issue-toggle" aria-expanded="false" aria-controls="${uid}-code" onclick="toggleSection(this)"><span class="toggle-icon" aria-hidden="true">&#9660;</span> HTML snippet</button>` : ''}
                    ${hasFix ? `<button class="issue-toggle" aria-expanded="false" aria-controls="${uid}-fix" onclick="toggleSection(this)"><span class="toggle-icon" aria-hidden="true">&#9660;</span> How to fix</button>` : ''}
                </div>` : ''}
                ${hasCode ? `<div id="${uid}-code" class="issue-section" hidden><div class="issue-code"><code class="language-html">${esc(i.element_html)}</code></div></div>` : ''}
                ${hasFix ? `<div id="${uid}-fix" class="issue-section" hidden><div class="issue-fix">${esc(i.how_to_fix)}</div></div>` : ''}
            </div>`;
        }

        function severityGroup(sev) {
            const grp = grouped[sev];
            if (!grp.length) return '';
            const gid = `grp-${sev}`;
            const n = grp.length;
            const label = sev[0].toUpperCase() + sev.slice(1);
            return `<div class="issue-group">
                <button class="issue-group-header ${sev}" aria-expanded="true" aria-controls="${gid}" onclick="toggleGroup(this)">
                    <span class="group-title">${label}</span>
                    <span class="group-count">${n} ${n === 1 ? 'issue' : 'issues'}</span>
                    <span class="group-toggle" aria-hidden="true">&#9660;</span>
                </button>
                <div id="${gid}" class="issue-group-body">${grp.map(issueCard).join('')}</div>
            </div>`;
        }

        currentScan = scan;
        currentIssues = issues || [];
        el.innerHTML = `
            <a href="#" class="back-link" onclick="openSite(${scan.site_id});return false">&larr; Back to scans</a>
            <div class="scan-detail">
                <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px">
                <div class="scan-detail-header">
                    <h3>Scan #${scan.id}</h3>
                    ${scan.score !== null ? `<div class="score-ring ${scoreClass(scan.score)}" style="width:64px;height:64px;font-size:1.2rem">${scan.score.toFixed(0)}</div>` : ''}
                </div>
                <p style="color:var(--text-muted);margin:8px 0">${scan.pages_scanned} pages scanned &mdash; ${scan.total_issues} issues found</p>
                <div class="severity-bar">
                    <span class="severity-count" style="background:var(--red-light);color:var(--red)">${scan.critical_count} Critical</span>
                    <span class="severity-count" style="background:#fff7ed;color:#c2410c">${scan.serious_count} Serious</span>
                    <span class="severity-count" style="background:var(--amber-light);color:var(--amber)">${scan.moderate_count} Moderate</span>
                    <span class="severity-count" style="background:var(--blue-light);color:var(--blue)">${scan.minor_count} Minor</span>
                </div>
            </div>
            <div class="export-actions">
                <button class="btn btn-outline btn-sm" onclick="exportCSV()" aria-label="Export issues as CSV spreadsheet">
                    <span aria-hidden="true">&#8595;</span> Export CSV
                </button>
                <button class="btn btn-outline btn-sm" onclick="exportPDF()" aria-label="Export scan report as PDF">
                    <span aria-hidden="true">&#8595;</span> Export PDF
                </button>
            </div>
            <h3 style="margin-bottom:12px">Issues (${issues.length})</h3>
            <div class="issues-list">${issues.map(i => `
                <div class="issue-card">
                    <div class="issue-header">
                        <span class="badge badge-${i.severity}">${i.severity}</span>
                        ${i.wcag_criteria ? `<span class="wcag">WCAG ${i.wcag_criteria}</span>` : ''}
                        <span style="color:var(--text-dim);font-size:0.82rem">${i.rule_id}</span>
                    </div>
                    <div class="issue-message">${esc(i.message)}</div>
                    <div class="issue-url" style="color:var(--text-muted);font-size:0.82rem">${esc(i.page_url)}</div>
                    ${i.element_html ? `<div class="issue-code">${esc(i.element_html)}</div>` : ''}
                    ${i.how_to_fix ? `<div class="issue-fix">${esc(i.how_to_fix)}</div>` : ''}
                </div>`).join('')}</div>`;
            <div class="issues-header">
                <h3>Issues (${issues.length})</h3>
                ${issues.length ? `<button class="btn btn-sm btn-outline" onclick="expandAllIssues()">Expand All</button>` : ''}
            </div>
            ${issues.length
                ? `<div class="issues-list" role="list">${SEVERITIES.map(severityGroup).join('')}</div>`
                : `<p style="color:var(--text-muted)">No issues found &mdash; great job!</p>`}`;

        if (issues.length && window.hljs) {
            el.querySelectorAll('.issue-code code').forEach(b => hljs.highlightElement(b));
        }
    } catch (e) { console.error(e); }
}

function toggleGroup(btn) {
    const expanded = btn.getAttribute('aria-expanded') === 'true';
    btn.setAttribute('aria-expanded', String(!expanded));
    const body = document.getElementById(btn.getAttribute('aria-controls'));
    if (body) body.hidden = expanded;
}

function toggleSection(btn) {
    const expanded = btn.getAttribute('aria-expanded') === 'true';
    btn.setAttribute('aria-expanded', String(!expanded));
    const section = document.getElementById(btn.getAttribute('aria-controls'));
    if (section) section.hidden = expanded;
}

function expandAllIssues() {
    document.querySelectorAll('.issue-group-header[aria-expanded="false"]').forEach(toggleGroup);
    document.querySelectorAll('.issue-toggle[aria-expanded="false"]').forEach(toggleSection);
function exportCSV() {
    if (!currentIssues.length) { showToast('No issues to export', 'info'); return; }
    const headers = ['Severity', 'WCAG Criteria', 'Rule ID', 'Message', 'Page URL', 'Selector', 'How to Fix'];
    const rows = currentIssues.map(i => [
        i.severity,
        i.wcag_criteria || '',
        i.rule_id,
        i.message,
        i.page_url,
        i.selector || '',
        i.how_to_fix || ''
    ].map(v => `"${String(v).replace(/"/g, '""')}"`));
    const csv = '\uFEFF' + [headers.join(','), ...rows.map(r => r.join(','))].join('\r\n');
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `scan-${currentScanId}-issues.csv`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    showToast('CSV downloaded');
}

async function exportPDF() {
    if (typeof window.jspdf === 'undefined') {
        showToast('PDF library is still loading — please try again in a moment', 'info');
        return;
    }
    const { jsPDF } = window.jspdf;
    const doc = new jsPDF({ orientation: 'landscape', unit: 'mm', format: 'a4' });
    const pageW = doc.internal.pageSize.getWidth();

    // Header bar
    doc.setFillColor(79, 70, 229);
    doc.rect(0, 0, pageW, 16, 'F');
    doc.setFontSize(11);
    doc.setFont('helvetica', 'bold');
    doc.setTextColor(255, 255, 255);
    doc.text('AccessWave — Accessibility Scan Report', 14, 11);

    // Scan metadata
    doc.setTextColor(26, 29, 35);
    doc.setFontSize(14);
    doc.text(`Scan #${currentScan.id}`, 14, 26);
    doc.setFontSize(9);
    doc.setFont('helvetica', 'normal');
    doc.setTextColor(107, 114, 128);
    const scoreLabel = currentScan.score !== null ? currentScan.score.toFixed(0) + ' / 100' : 'N/A';
    doc.text(`Score: ${scoreLabel}   |   Pages scanned: ${currentScan.pages_scanned}   |   Total issues: ${currentScan.total_issues}`, 14, 33);
    doc.text(`Critical: ${currentScan.critical_count}   Serious: ${currentScan.serious_count}   Moderate: ${currentScan.moderate_count}   Minor: ${currentScan.minor_count}`, 14, 39);

    if (!currentIssues.length) {
        doc.setTextColor(5, 150, 105);
        doc.setFontSize(11);
        doc.setFont('helvetica', 'bold');
        doc.text('No issues found — great job!', 14, 52);
    } else {
        const severityColors = {
            critical: [220, 38, 38],
            serious:  [194, 65, 12],
            moderate: [217, 119, 6],
            minor:    [37, 99, 235],
        };
        doc.autoTable({
            startY: 46,
            head: [['Severity', 'WCAG', 'Rule ID', 'Message', 'Page URL']],
            body: currentIssues.map(i => [
                i.severity,
                i.wcag_criteria || '',
                i.rule_id,
                i.message,
                i.page_url,
            ]),
            styles: { fontSize: 8, cellPadding: 3, overflow: 'linebreak' },
            headStyles: { fillColor: [79, 70, 229], textColor: 255, fontStyle: 'bold' },
            columnStyles: {
                0: { cellWidth: 22 },
                1: { cellWidth: 18 },
                2: { cellWidth: 36 },
                3: { cellWidth: 'auto' },
                4: { cellWidth: 70 },
            },
            didParseCell(data) {
                if (data.section === 'body' && data.column.index === 0) {
                    const color = severityColors[data.cell.raw] || [26, 29, 35];
                    data.cell.styles.textColor = color;
                    data.cell.styles.fontStyle = 'bold';
                }
            },
            alternateRowStyles: { fillColor: [244, 245, 247] },
        });
    }

    const pageCount = doc.internal.getNumberOfPages();
    for (let p = 1; p <= pageCount; p++) {
        doc.setPage(p);
        doc.setFontSize(8);
        doc.setTextColor(156, 163, 175);
        doc.text(`Page ${p} of ${pageCount}`, pageW - 14, doc.internal.pageSize.getHeight() - 6, { align: 'right' });
    }

    doc.save(`scan-${currentScanId}-report.pdf`);
    showToast('PDF downloaded');
}

async function addSite(e) {
    e.preventDefault();
    const form = e.target;
    const btn = form.querySelector('button[type=submit]');
    const origText = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner" aria-hidden="true"></span>Adding\u2026';
    const nameInput = form.querySelector('[name=name]');
    const urlInput = form.querySelector('[name=url]');

    const nameOk = validateRequiredField(nameInput, 'Site name');
    const urlOk = validateURLField(urlInput);
    if (!nameOk || !urlOk) return;

    try {
        await API.req('POST', '/sites', { name: nameInput.value.trim(), url: urlInput.value.trim() });
        document.getElementById('add-modal').classList.remove('active');
        form.reset();
        clearFormValidation(form);
        showToast('Site added');
        await Promise.all([loadStats(), loadSites()]);
    } catch (e) {
        showToast(e.message, 'error');
        btn.disabled = false;
        btn.innerHTML = origText;
    }
    } catch (err) { showToast(err.message, 'error'); }
}

async function startScan(siteId, btn) {
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<span class="spinner" aria-hidden="true"></span>Scanning\u2026';
    }

    // Inject a live progress banner at top of main-content
    const banner = document.createElement('div');
    banner.className = 'scan-progress';
    banner.setAttribute('role', 'status');
    banner.setAttribute('aria-live', 'polite');
    banner.setAttribute('aria-label', 'Scan in progress');
    banner.innerHTML = `
        <span class="sp-text"><span class="spinner" aria-hidden="true"></span>Scanning\u2026</span>
        <div class="scan-progress-track" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="0" aria-label="Scan progress">
            <div class="scan-progress-bar" style="width:0%"></div>
        </div>
        <span class="sp-pct" aria-hidden="true">0%</span>`;
    document.getElementById('main-content').prepend(banner);

    let pct = 0;
    const iv = setInterval(() => {
        pct = Math.min(pct + Math.random() * 4 + 1.5, 90);
        const bar = banner.querySelector('.scan-progress-bar');
        const track = banner.querySelector('[role=progressbar]');
        const pctEl = banner.querySelector('.sp-pct');
        if (bar) bar.style.width = pct.toFixed(0) + '%';
        if (track) track.setAttribute('aria-valuenow', pct.toFixed(0));
        if (pctEl) pctEl.textContent = pct.toFixed(0) + '%';
    }, 500);

    try {
        await API.req('POST', `/sites/${siteId}/scan`);
        showToast('Scan started!');
        setTimeout(async () => {
            clearInterval(iv);
            const bar = banner.querySelector('.scan-progress-bar');
            const track = banner.querySelector('[role=progressbar]');
            const pctEl = banner.querySelector('.sp-pct');
            if (bar) bar.style.width = '100%';
            if (track) track.setAttribute('aria-valuenow', '100');
            if (pctEl) pctEl.textContent = '100%';
            await loadStats();
            await loadCharts();
            if (currentSiteId === siteId) await openSite(siteId);
            else await loadSites();
            banner.remove();
        }, 8000);
    } catch (e) {
        clearInterval(iv);
        banner.remove();
        if (btn) { btn.disabled = false; btn.textContent = 'Scan Now'; }
        showToast(e.message, 'error');
    }
}

async function deleteSite(siteId) {
    if (!confirm('Delete this site and all its scans?')) return;
    try {
        await API.req('DELETE', `/sites/${siteId}`);
        showToast('Site deleted');
        await Promise.all([loadStats(), loadSites()]);
    } catch (e) { showToast(e.message, 'error'); }
}

function openEditSite(siteId, name, url) {
    const form = document.getElementById('edit-site-form');
    form.site_id.value = siteId;
    form.name.value = name;
    form.url.value = url;
    document.getElementById('edit-modal').classList.add('active');
    document.getElementById('edit-site-name').focus();
}

async function saveEditSite(e) {
    e.preventDefault();
    const form = e.target;
    const siteId = form.site_id.value;
    const btn = form.querySelector('button[type=submit]');
    btn.disabled = true;
    try {
        await API.req('PATCH', `/sites/${siteId}`, { name: form.name.value, url: form.url.value });
        document.getElementById('edit-modal').classList.remove('active');
        showToast('Site updated');
        await Promise.all([loadStats(), loadSites()]);
    } catch (err) {
        showToast(err.message, 'error');
    } finally {
        btn.disabled = false;
    }
}

async function upgradePlan(plan) {
    try {
        const data = await API.req('POST', `/billing/checkout/${plan}`);
        if (data?.checkout_url) window.location.href = data.checkout_url;
    } catch (e) { showToast(e.message, 'error'); }
}

// Charts
async function loadCharts() {
    if (typeof Chart === 'undefined') return;
    try {
        const data = await API.req('GET', '/dashboard/chart-data');
        if (!data) return;
        const hasScoreData = data.score_history.some(s => s.scans.length > 0);
        const hasSeverityData = Object.values(data.severity_totals).some(v => v > 0);
        const section = document.getElementById('charts-section');
        if (!hasScoreData && !hasSeverityData) { section.hidden = true; return; }
        section.hidden = false;
        if (hasScoreData) _renderScoreTrend(data.score_history);
        if (hasSeverityData) _renderSeverityChart(data.severity_totals);
    } catch (e) { console.error('Charts failed to load:', e); }
}

function _renderScoreTrend(scoreHistory) {
    const ctx = document.getElementById('score-trend-chart');
    if (!ctx) return;
    if (_scoreTrendChart) { _scoreTrendChart.destroy(); _scoreTrendChart = null; }

    // Build sorted union of all dates as category labels
    const allDatesSet = new Set();
    scoreHistory.forEach(site => site.scans.forEach(s => allDatesSet.add(s.date.substring(0, 10))));
    const allDates = [...allDatesSet].sort();
    const labels = allDates.map(d => {
        const dt = new Date(d + 'T00:00:00');
        return dt.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
    });

    const palette = ['#4f46e5', '#059669', '#d97706', '#dc2626', '#2563eb', '#7c3aed'];
    const datasets = scoreHistory.map((site, i) => {
        const byDate = Object.fromEntries(site.scans.map(s => [s.date.substring(0, 10), s.score]));
        return {
            label: site.site_name,
            data: allDates.map(d => byDate[d] ?? null),
            borderColor: palette[i % palette.length],
            backgroundColor: palette[i % palette.length] + '1a',
            tension: 0.35,
            pointRadius: 4,
            pointHoverRadius: 6,
            spanGaps: false,
            fill: false,
            borderWidth: 2,
        };
    });

    _scoreTrendChart = new Chart(ctx, {
        type: 'line',
        data: { labels, datasets },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    display: scoreHistory.length > 1,
                    labels: { color: '#1a1d23', font: { size: 12 }, usePointStyle: true, pointStyleWidth: 8 },
                },
                tooltip: {
                    callbacks: { label: c => ` ${c.dataset.label}: ${c.parsed.y !== null ? c.parsed.y.toFixed(1) : 'N/A'}` },
                },
            },
            scales: {
                x: { grid: { color: '#e2e5ea' }, ticks: { color: '#6b7280', font: { size: 11 } } },
                y: {
                    min: 0, max: 100,
                    grid: { color: '#e2e5ea' },
                    ticks: { color: '#6b7280', font: { size: 11 }, stepSize: 25, callback: v => v + '%' },
                },
            },
        },
    });
}

function _renderSeverityChart(totals) {
    const ctx = document.getElementById('severity-chart');
    if (!ctx) return;
    if (_severityChart) { _severityChart.destroy(); _severityChart = null; }

    _severityChart = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: ['Critical', 'Serious', 'Moderate', 'Minor'],
            datasets: [{
                data: [totals.critical, totals.serious, totals.moderate, totals.minor],
                backgroundColor: ['#dc2626', '#c2410c', '#d97706', '#2563eb'],
                borderWidth: 0,
                hoverOffset: 6,
            }],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            cutout: '65%',
            plugins: {
                legend: {
                    position: 'bottom',
                    labels: {
                        color: '#1a1d23', font: { size: 12 }, padding: 14,
                        usePointStyle: true, pointStyleWidth: 10,
                    },
                },
                tooltip: {
                    callbacks: {
                        label: c => {
                            const total = c.dataset.data.reduce((a, b) => a + b, 0);
                            const pct = total ? ((c.parsed / total) * 100).toFixed(1) : 0;
                            return ` ${c.label}: ${c.parsed} (${pct}%)`;
                        },
                    },
                },
            },
        },
    });
}
