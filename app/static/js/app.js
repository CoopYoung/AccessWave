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

// Auth
function initAuth(type) {
    if (API.isLoggedIn()) { window.location.href = '/dashboard'; return; }
    const form = document.getElementById('auth-form'), err = document.getElementById('error-msg');
    if (!form) return;
    form.addEventListener('submit', async (e) => {
        e.preventDefault(); err.style.display = 'none';
        const btn = form.querySelector('button[type=submit]'); btn.disabled = true;
        try {
            let data;
            if (type === 'register') {
                data = await API.req('POST', '/auth/register', { email: form.email.value, password: form.password.value });
            } else {
                const fd = new URLSearchParams(); fd.append('username', form.email.value); fd.append('password', form.password.value);
                const r = await fetch('/api/auth/login', { method: 'POST', body: fd }); data = await r.json();
                if (!r.ok) throw new Error(data.detail || 'Login failed');
            }
            API.setToken(data.access_token); window.location.href = '/dashboard';
        } catch (e) { err.textContent = e.message; err.style.display = 'block'; btn.disabled = false; }
    });
}

// Dashboard
let currentView = 'sites'; // sites, scan-detail
let currentSiteId = null;
let currentScanId = null;
let _scoreTrendChart = null;
let _severityChart = null;

async function initDashboard() {
    if (!API.isLoggedIn()) { window.location.href = '/login'; return; }
    document.getElementById('logout-btn')?.addEventListener('click', () => API.logout());
    document.getElementById('add-site-btn')?.addEventListener('click', () => document.getElementById('add-modal').classList.add('active'));
    document.getElementById('close-modal')?.addEventListener('click', () => document.getElementById('add-modal').classList.remove('active'));
    document.getElementById('site-form')?.addEventListener('submit', addSite);
    await loadStats();
    await Promise.all([loadSites(), loadCharts()]);
}

async function loadStats() {
    try {
        const s = await API.req('GET', '/dashboard/stats');
        if (!s) return;
        animateCounter(document.getElementById('stat-sites'), s.total_sites);
        animateCounter(document.getElementById('stat-scans'), s.total_scans);
        document.getElementById('stat-score').textContent = s.avg_score !== null ? s.avg_score : '--';
        animateCounter(document.getElementById('stat-issues'), s.total_issues);
        animateCounter(document.getElementById('stat-critical'), s.critical_issues);
    } catch (e) { console.error(e); }
}

async function loadSites() {
    const el = document.getElementById('main-content');
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
                    <button class="btn btn-sm btn-danger" onclick="event.stopPropagation();deleteSite(${s.id})">Delete</button>
                </div>
            </div>`).join('')}</div>`;
    } catch (e) { console.error(e); }
}

async function openSite(siteId) {
    currentSiteId = siteId;
    const el = document.getElementById('main-content');
    el.innerHTML = '<p style="color:var(--text-muted)">Loading scans...</p>';
    try {
        const scans = await API.req('GET', `/sites/${siteId}/scans`);
        const sites = await API.req('GET', '/sites');
        const site = sites.find(s => s.id === siteId);
        if (!scans?.length) {
            el.innerHTML = `<a href="#" class="back-link" onclick="loadSites();return false">&larr; Back to sites</a>
                <div class="empty-state"><div class="icon">\uD83D\uDD0D</div><p>No scans yet for ${esc(site?.name || '')}</p>
                <button class="btn btn-green" onclick="startScan(${siteId})">Run First Scan</button></div>`;
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
    el.innerHTML = '<p style="color:var(--text-muted)">Loading issues...</p>';
    try {
        const [scan, issues] = await Promise.all([
            API.req('GET', `/scans/${scanId}`),
            API.req('GET', `/scans/${scanId}/issues`),
        ]);
        el.innerHTML = `
            <a href="#" class="back-link" onclick="openSite(${scan.site_id});return false">&larr; Back to scans</a>
            <div class="scan-detail">
                <div style="display:flex;justify-content:space-between;align-items:center">
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
            <h3 style="margin-bottom:12px">Issues (${issues.length})</h3>
            <div class="issues-list">${issues.map(i => `
                <div class="issue-card">
                    <div class="issue-header">
                        <span class="badge badge-${i.severity}">${i.severity}</span>
                        ${i.wcag_criteria ? `<span class="wcag">WCAG ${i.wcag_criteria}</span>` : ''}
                        <span style="color:var(--text-dim);font-size:0.82rem">${i.rule_id}</span>
                    </div>
                    <div class="issue-message">${esc(i.message)}</div>
                    <div style="color:var(--text-muted);font-size:0.82rem">${esc(i.page_url)}</div>
                    ${i.element_html ? `<div class="issue-code">${esc(i.element_html)}</div>` : ''}
                    ${i.how_to_fix ? `<div class="issue-fix">${esc(i.how_to_fix)}</div>` : ''}
                </div>`).join('')}</div>`;
    } catch (e) { console.error(e); }
}

async function addSite(e) {
    e.preventDefault();
    const form = e.target;
    try {
        await API.req('POST', '/sites', { name: form.name.value, url: form.url.value });
        document.getElementById('add-modal').classList.remove('active');
        form.reset();
        showToast('Site added');
        await Promise.all([loadStats(), loadSites()]);
    } catch (e) { showToast(e.message, 'error'); }
}

async function startScan(siteId) {
    try {
        const scan = await API.req('POST', `/sites/${siteId}/scan`);
        showToast('Scan started! Refresh in a few seconds to see results.');
        // Poll for completion
        setTimeout(async () => {
            await loadStats();
            await loadCharts();
            if (currentSiteId === siteId) await openSite(siteId);
            else await loadSites();
        }, 8000);
    } catch (e) { showToast(e.message, 'error'); }
}

async function deleteSite(siteId) {
    if (!confirm('Delete this site and all its scans?')) return;
    try {
        await API.req('DELETE', `/sites/${siteId}`);
        showToast('Site deleted');
        await Promise.all([loadStats(), loadSites()]);
    } catch (e) { showToast(e.message, 'error'); }
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
