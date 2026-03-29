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
// Dark mode
function initDarkMode() {
    const html = document.documentElement;
    const btn = document.getElementById('dark-toggle');
    const stored = localStorage.getItem('aw_theme');
    const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    const isDark = stored ? stored === 'dark' : prefersDark;

    function applyTheme(dark) {
        if (dark) {
            html.setAttribute('data-theme', 'dark');
        } else {
            html.removeAttribute('data-theme');
        }
        if (btn) {
            btn.textContent = dark ? '☀' : '🌙';
            btn.setAttribute('aria-label', dark ? 'Switch to light mode' : 'Switch to dark mode');
            btn.setAttribute('aria-pressed', String(dark));
        }
    }

    applyTheme(isDark);

    if (btn) {
        btn.addEventListener('click', () => {
            const nowDark = html.getAttribute('data-theme') === 'dark';
            localStorage.setItem('aw_theme', nowDark ? 'light' : 'dark');
            applyTheme(!nowDark);
        });
    }

    // Keep in sync if another tab changes the preference
    window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', (e) => {
        if (!localStorage.getItem('aw_theme')) applyTheme(e.matches);
    });
}

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

/**
 * Build an accessible SVG arc gauge for a 0–100 accessibility score.
 * The arc spans 270° (gap at the bottom), colour-coded green/amber/red.
 * Call animateGauges(container) after injecting the returned HTML to run
 * the fill-in animation (double rAF so the initial dashoffset is painted first).
 *
 * @param {number} score   0–100
 * @param {number} size    SVG width/height in px (default 140)
 * @returns {string}       SVG HTML string
 */
function buildGauge(score, size = 140) {
    const sw    = Math.round(size * 0.09);          // stroke width
    const r     = (size - sw) / 2;                  // radius
    const cx    = size / 2, cy = size / 2;          // centre
    const arcLen = 0.75 * 2 * Math.PI * r;          // 270° arc length
    const gap    = 2 * Math.PI * r - arcLen + 1;    // remaining gap (+1 avoids hairline)

    const cls = score >= 80 ? 'gauge-good' : score >= 50 ? 'gauge-ok' : 'gauge-bad';
    const lbl = score >= 80 ? 'Good' : score >= 50 ? 'Needs improvement' : 'Poor';

    // Start at arcLen (empty) → animate to finalOffset via animateGauges()
    const finalOffset = arcLen * (1 - score / 100);

    // Typography — absolute px values so they scale with `size`
    const numSize  = Math.round(size * 0.2);                      // score number
    const lblSize  = Math.round(size * 0.09);                     // label
    const numY     = cy - numSize * 0.15;                         // slightly above centre
    const lblY     = numY + numSize * 0.55 + lblSize;             // below number

    // stroke-dasharray: <visible arc> <gap> — the gap ensures no repeat wraps
    const da = `${arcLen.toFixed(2)} ${gap.toFixed(2)}`;

    return `<svg role="meter"
        aria-label="Accessibility score: ${Math.round(score)} out of 100 – ${lbl}"
        aria-valuenow="${Math.round(score)}" aria-valuemin="0" aria-valuemax="100"
        width="${size}" height="${size}" viewBox="0 0 ${size} ${size}"
        class="score-gauge" focusable="false">
      <circle class="gauge-track"
        cx="${cx}" cy="${cy}" r="${r.toFixed(2)}"
        fill="none" stroke-width="${sw}"
        stroke-dasharray="${da}"
        transform="rotate(135, ${cx}, ${cy})"/>
      <circle class="gauge-fill ${cls}"
        cx="${cx}" cy="${cy}" r="${r.toFixed(2)}"
        fill="none" stroke-width="${sw}"
        stroke-dasharray="${da}"
        stroke-dashoffset="${arcLen.toFixed(2)}"
        data-final-offset="${finalOffset.toFixed(2)}"
        transform="rotate(135, ${cx}, ${cy})"/>
      <text class="gauge-score" aria-hidden="true"
        x="${cx}" y="${numY.toFixed(1)}"
        text-anchor="middle" dominant-baseline="middle"
        font-size="${numSize}">${Math.round(score)}</text>
      <text class="gauge-label" aria-hidden="true"
        x="${cx}" y="${lblY.toFixed(1)}"
        text-anchor="middle" dominant-baseline="middle"
        font-size="${lblSize}">${lbl}</text>
    </svg>`;
}

/**
 * Trigger the fill animation for every gauge inside `container`.
 * Must be called after the gauge HTML has been inserted into the DOM.
 */
function animateGauges(container) {
    // Double rAF: first frame paints the initial (empty) state,
    // second frame applies the target offset → CSS transition fires.
    requestAnimationFrame(() => requestAnimationFrame(() => {
        (container || document).querySelectorAll('.gauge-fill[data-final-offset]').forEach(el => {
            el.style.strokeDashoffset = el.dataset.finalOffset;
        });
    }));
}
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
function showToast(msg, type = 'success') {
    let c = document.querySelector('.toast-container');
    if (!c) {
        c = document.createElement('div');
        c.className = 'toast-container';
        c.setAttribute('role', 'status');
        c.setAttribute('aria-live', 'polite');
        c.setAttribute('aria-atomic', 'true');
        document.body.appendChild(c);
    }
    const t = document.createElement('div'); t.className = `toast ${type}`; t.textContent = msg; c.appendChild(t);
    setTimeout(() => { t.style.animation = 'toast-in 0.3s ease reverse forwards'; setTimeout(() => t.remove(), 300); }, 3000);
}

// ── Focus trap ────────────────────────────────────────────────────────────────
// Traps Tab/Shift+Tab focus within `el`. Returns a cleanup function.
function trapFocus(el) {
    const sel = 'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';
    const handler = (e) => {
        if (e.key !== 'Tab') return;
        const nodes = [...el.querySelectorAll(sel)];
        if (!nodes.length) { e.preventDefault(); return; }
        const first = nodes[0], last = nodes[nodes.length - 1];
        if (e.shiftKey) {
            if (document.activeElement === first) { e.preventDefault(); last.focus(); }
        } else {
            if (document.activeElement === last) { e.preventDefault(); first.focus(); }
        }
    };
    el.addEventListener('keydown', handler);
    return () => el.removeEventListener('keydown', handler);
}

// ── Modal helpers ─────────────────────────────────────────────────────────────
// Opens an overlay, traps focus, returns a close() function.
function openModal(overlay) {
    const returnFocus = document.activeElement;
    overlay.classList.add('active');
    overlay.setAttribute('aria-hidden', 'false');
    const inner = overlay.querySelector('.modal') || overlay;
    const releaseTrap = trapFocus(inner);
    // Focus first interactive element
    const firstFocusable = inner.querySelector('input, button, [tabindex]');
    firstFocusable?.focus();

    const close = () => {
        overlay.classList.remove('active');
        overlay.setAttribute('aria-hidden', 'true');
        releaseTrap();
        overlay.removeEventListener('keydown', escHandler);
        returnFocus?.focus();
    };
    const escHandler = (e) => { if (e.key === 'Escape') { e.preventDefault(); close(); } };
    overlay.addEventListener('keydown', escHandler);
    // Close on backdrop click
    overlay.addEventListener('click', (e) => { if (e.target === overlay) close(); }, { once: true });
    return close;
}

// ── Auth ──────────────────────────────────────────────────────────────────────
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

// ── Dashboard state ───────────────────────────────────────────────────────────
let currentView = 'sites'; // sites | scans | scan-detail
let currentSiteId = null;
let currentScanId = null;
let _scoreTrendChart = null;
let _severityChart = null;
let currentScan = null;
let currentIssues = [];
let closeAddModal = null;
let closeShortcutsModal = null;

// Scan filter & pagination state
let scanFilters = { status: '', min_score: '', max_score: '', sort: 'created_at', order: 'desc' };
let scanPage = 0;
const SCAN_PAGE_SIZE = 10;
let selectedSites = new Set();

// Scan comparison state
let compareMode = false;
let compareSelected = []; // up to 2 scan ids

async function initDashboard() {
    if (!API.isLoggedIn()) { window.location.href = '/login'; return; }

    document.getElementById('logout-btn')?.addEventListener('click', () => API.logout());
    document.getElementById('add-site-btn')?.addEventListener('click', () => document.getElementById('add-modal').classList.add('active'));
    document.getElementById('close-modal')?.addEventListener('click', () => {
        document.getElementById('add-modal').classList.remove('active');
        const form = document.getElementById('site-form');
        if (form) { form.reset(); clearFormValidation(form); }
    });
    document.getElementById('close-modal')?.addEventListener('click', () => document.getElementById('add-modal').classList.remove('active'));
    document.getElementById('close-badge-modal')?.addEventListener('click', () => document.getElementById('badge-modal').classList.remove('active'));
    document.getElementById('badge-modal')?.addEventListener('click', (e) => { if (e.target === e.currentTarget) e.currentTarget.classList.remove('active'); });
    document.getElementById('site-form')?.addEventListener('submit', addSite);
    document.getElementById('close-edit-modal')?.addEventListener('click', () => document.getElementById('edit-modal').classList.remove('active'));
    document.getElementById('edit-site-form')?.addEventListener('submit', saveEditSite);
    // Close modals when clicking the backdrop
    document.getElementById('add-modal')?.addEventListener('click', e => { if (e.target === e.currentTarget) e.currentTarget.classList.remove('active'); });
    document.getElementById('edit-modal')?.addEventListener('click', e => { if (e.target === e.currentTarget) e.currentTarget.classList.remove('active'); });

    // Add-site modal
    const addModal = document.getElementById('add-modal');
    document.getElementById('add-site-btn')?.addEventListener('click', () => {
        closeAddModal = openModal(addModal);
    });
    document.getElementById('close-modal')?.addEventListener('click', () => closeAddModal?.());
    document.getElementById('site-form')?.addEventListener('submit', addSite);

    // Keyboard shortcuts modal
    const shortcutsModal = document.getElementById('shortcuts-modal');
    document.getElementById('shortcuts-trigger')?.addEventListener('click', () => {
        closeShortcutsModal = openModal(shortcutsModal);
    });
    document.getElementById('close-shortcuts')?.addEventListener('click', () => closeShortcutsModal?.());

    // Keyboard event delegation for site/scan cards (Enter or Space)
    document.getElementById('dash-content')?.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' || e.key === ' ') {
            const card = e.target.closest('.site-card[data-action]');
            if (card) { e.preventDefault(); card.click(); }
        }
    });

    initKeyboardShortcuts();

    // Inject bulk action toolbar (persistent, shown/hidden via CSS transform)
    if (!document.getElementById('bulk-toolbar')) {
        const tb = document.createElement('div');
        tb.id = 'bulk-toolbar';
        tb.className = 'bulk-toolbar';
        tb.setAttribute('role', 'toolbar');
        tb.setAttribute('aria-label', 'Bulk actions for selected sites');
        tb.innerHTML = `
            <span class="bulk-count" id="bulk-count" aria-live="polite"></span>
            <button class="btn-bulk" onclick="bulkScan()">Scan Selected</button>
            <button class="btn-bulk btn-bulk-delete" onclick="bulkDelete()">Delete Selected</button>
            <button class="btn-bulk btn-bulk-cancel" onclick="clearSelection()">Cancel</button>`;
        document.body.appendChild(tb);
    }
    await loadStats();
    await Promise.all([loadSites(), loadCharts()]);
}

function setStatVal(id, val) {
    const el = document.getElementById(id);
    if (!el) return;
    el.classList.remove('sk');
    el.textContent = val;
}

// ── Keyboard shortcuts ────────────────────────────────────────────────────────
function initKeyboardShortcuts() {
    document.addEventListener('keydown', (e) => {
        // Never fire shortcuts while typing
        if (['INPUT', 'TEXTAREA', 'SELECT'].includes(e.target.tagName)) return;
        if (e.metaKey || e.ctrlKey || e.altKey) return;
        // Don't fire when a modal is open (modal handles Esc internally)
        const modalOpen = document.querySelector('.modal-overlay.active');
        if (modalOpen && e.key !== 'Escape') return;

        switch (e.key) {
            case 'n':
            case 'N':
                e.preventDefault();
                document.getElementById('add-site-btn')?.click();
                break;
            case 'b':
            case 'B':
                e.preventDefault();
                if (currentView === 'scan-detail') { openSite(currentSiteId); }
                else if (currentView === 'scans') { loadSites(); }
                break;
            case 'r':
            case 'R':
                e.preventDefault();
                refreshCurrentView();
                break;
            case '?':
                e.preventDefault();
                document.getElementById('shortcuts-trigger')?.click();
                break;
            case 'Escape':
                // Handled per-modal via openModal(); also navigate back if no modal open
                if (!modalOpen) {
                    if (currentView === 'scan-detail') openSite(currentSiteId);
                    else if (currentView === 'scans') loadSites();
                }
                break;
        }
    });
}

async function refreshCurrentView() {
    await loadStats();
    if (currentView === 'scan-detail' && currentScanId) await openScan(currentScanId);
    else if (currentView === 'scans' && currentSiteId) await openSite(currentSiteId);
    else await loadSites();
}

// ── Dashboard data ────────────────────────────────────────────────────────────
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
    selectedSites.clear();
    updateBulkToolbar();
    const el = document.getElementById('main-content');
    el.innerHTML = `<div class="sites-list" aria-busy="true" aria-label="Loading sites">${skSiteCards(3)}</div>`;
    currentView = 'sites'; currentSiteId = null; currentScanId = null;
    const el = document.getElementById('dash-content');
    try {
        const sites = await API.req('GET', '/sites');
        if (!sites?.length) {
            el.innerHTML = `<div class="empty-state"><div class="icon">\uD83C\uDF10</div><p>No sites added yet</p><p style="font-size:0.88rem">Add your first website to scan for accessibility issues.</p></div>`;
            return;
        }
        el.innerHTML = `<div class="sites-list">${sites.map(s => `
            <div class="site-card" tabindex="0" role="button" data-action="open-site" data-site-id="${s.id}" onclick="openSite(${s.id})" aria-label="View scans for ${esc(s.name)}">
                <div class="site-info">
                    ${s.last_score !== null ? `<div class="score-ring ${scoreClass(s.last_score)}" aria-label="Score: ${s.last_score.toFixed(0)}">${s.last_score.toFixed(0)}</div>` : `<div class="score-ring" style="background:var(--surface-2);color:var(--text-dim);border-color:var(--border)" aria-label="Not yet scored">--</div>`}
                    <div><div class="name">${esc(s.name)}</div><div class="url">${esc(s.url)}</div></div>
                </div>
                <div class="site-meta">
                    <span class="last-scan">${s.last_scan_at ? 'Scanned ' + timeAgo(s.last_scan_at) : 'Not scanned'}</span>
                    <button class="btn btn-sm btn-green" onclick="event.stopPropagation();startScan(${s.id})">Scan Now</button>
                    <button class="btn btn-sm btn-edit" aria-label="Edit ${esc(s.name)}" onclick="event.stopPropagation();openEditSite(${s.id},'${esc(s.name).replace(/'/g,"\\'")}','${esc(s.url).replace(/'/g,"\\'")}')">Edit</button>
                    <button class="btn btn-sm btn-green" onclick="event.stopPropagation();startScan(${s.id},this)">Scan Now</button>
                    <button class="btn btn-sm btn-outline" data-site-id="${s.id}" data-site-name="${esc(s.name)}" onclick="event.stopPropagation();showBadge(this.dataset.siteId,this.dataset.siteName)">Badge</button>
                    <button class="btn btn-sm btn-danger" onclick="event.stopPropagation();deleteSite(${s.id})">Delete</button>
                    <button class="btn btn-sm btn-green" onclick="event.stopPropagation();startScan(${s.id})" aria-label="Scan ${esc(s.name)} now">Scan Now</button>
                    <button class="btn btn-sm btn-danger" onclick="event.stopPropagation();deleteSite(${s.id})" aria-label="Delete ${esc(s.name)}">Delete</button>
                </div>
            </div>`).join('')}</div>`;
        el.innerHTML = `
            <div class="sites-toolbar">
                <label class="select-all-label">
                    <input type="checkbox" id="select-all-check" onchange="toggleSelectAll(this)" aria-label="Select all sites">
                    <span>Select all</span>
                </label>
                <span class="selection-info" id="selection-info" aria-live="polite"></span>
            </div>
            <div class="sites-list">${sites.map(s => {
                const scoreHtml = s.last_score !== null
                    ? `<div class="score-ring ${scoreClass(s.last_score)}">${s.last_score.toFixed(0)}</div>`
                    : `<div class="score-ring" style="background:var(--surface-2);color:var(--text-dim);border-color:var(--border)">--</div>`;
                return `
                <div class="site-card" data-site-id="${s.id}">
                    <label class="site-check-wrap">
                        <input type="checkbox" class="site-check" onchange="toggleSiteSelect(${s.id}, this)" aria-label="Select ${esc(s.name)}">
                    </label>
                    <div class="site-clickable" onclick="openSite(${s.id})" role="button" tabindex="0"
                         onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();openSite(${s.id})}">
                        ${scoreHtml}
                        <div><div class="name">${esc(s.name)}</div><div class="url">${esc(s.url)}</div></div>
                    </div>
                    <div class="site-meta">
                        <span class="last-scan">${s.last_scan_at ? 'Scanned ' + timeAgo(s.last_scan_at) : 'Not scanned'}</span>
                        <button class="btn btn-sm btn-green" onclick="startScan(${s.id})">Scan Now</button>
                        <button class="btn btn-sm btn-danger" onclick="deleteSite(${s.id})">Delete</button>
                    </div>
                </div>`;
            }).join('')}</div>`;
    } catch (e) { console.error(e); }
}

function toggleSiteSelect(siteId, checkbox) {
    if (checkbox.checked) selectedSites.add(siteId);
    else selectedSites.delete(siteId);
    const card = document.querySelector(`.site-card[data-site-id="${siteId}"]`);
    if (card) card.classList.toggle('selected', checkbox.checked);
    _syncSelectAll();
    updateBulkToolbar();
}

function toggleSelectAll(checkbox) {
    document.querySelectorAll('.site-check').forEach(ch => {
        const id = parseInt(ch.closest('.site-card').dataset.siteId);
        ch.checked = checkbox.checked;
        const card = ch.closest('.site-card');
        if (checkbox.checked) { selectedSites.add(id); card.classList.add('selected'); }
        else { selectedSites.delete(id); card.classList.remove('selected'); }
    });
    updateBulkToolbar();
}

function _syncSelectAll() {
    const all = document.querySelectorAll('.site-check');
    const checked = document.querySelectorAll('.site-check:checked');
    const sa = document.getElementById('select-all-check');
    if (!sa) return;
    sa.indeterminate = checked.length > 0 && checked.length < all.length;
    sa.checked = all.length > 0 && checked.length === all.length;
}

function updateBulkToolbar() {
    const toolbar = document.getElementById('bulk-toolbar');
    const info = document.getElementById('selection-info');
    if (!toolbar) return;
    const n = selectedSites.size;
    if (n > 0) {
        toolbar.classList.add('visible');
        document.getElementById('bulk-count').textContent = `${n} site${n !== 1 ? 's' : ''} selected`;
        if (info) info.textContent = `${n} selected`;
    } else {
        toolbar.classList.remove('visible');
        if (info) info.textContent = '';
    }
}

function clearSelection() {
    selectedSites.clear();
    document.querySelectorAll('.site-check').forEach(ch => { ch.checked = false; });
    document.querySelectorAll('.site-card.selected').forEach(c => c.classList.remove('selected'));
    const sa = document.getElementById('select-all-check');
    if (sa) { sa.checked = false; sa.indeterminate = false; }
    updateBulkToolbar();
}

async function bulkScan() {
    const ids = [...selectedSites];
    let started = 0, skipped = 0;
    for (const id of ids) {
        try { await API.req('POST', `/sites/${id}/scan`); started++; }
        catch (e) { skipped++; }
    }
    clearSelection();
    const msg = started
        ? `Started ${started} scan${started !== 1 ? 's' : ''}${skipped ? ` (${skipped} already running)` : ''}`
        : `All selected scans are already running`;
    showToast(msg, skipped === ids.length ? 'error' : 'success');
    await loadSites();
    setTimeout(async () => { await Promise.all([loadStats(), loadSites()]); }, 8000);
}

async function bulkDelete() {
    const count = selectedSites.size;
    if (!confirm(`Delete ${count} site${count !== 1 ? 's' : ''} and all their scan history? This cannot be undone.`)) return;
    const ids = [...selectedSites];
    let deleted = 0, failed = 0;
    for (const id of ids) {
        try { await API.req('DELETE', `/sites/${id}`); deleted++; }
        catch (e) { failed++; }
    }
    clearSelection();
    showToast(
        `Deleted ${deleted} site${deleted !== 1 ? 's' : ''}${failed ? ` (${failed} failed)` : ''}`,
        failed > 0 && deleted === 0 ? 'error' : 'success'
    );
    await Promise.all([loadStats(), loadSites()]);
}

async function openSite(siteId) {
    currentSiteId = siteId;
    scanPage = 0;
    scanFilters = { status: '', min_score: '', max_score: '', sort: 'created_at', order: 'desc' };
    compareMode = false;
    compareSelected = [];
    const el = document.getElementById('main-content');
    el.innerHTML = `<a href="#" class="back-link" onclick="loadSites();return false">&larr; Back to sites</a>
        <div class="sites-list" aria-busy="true" aria-label="Loading scans">${skSiteCards(3)}</div>`;
    currentView = 'scans'; currentSiteId = siteId; currentScanId = null;
    const el = document.getElementById('dash-content');
    el.innerHTML = '<p style="color:var(--text-muted)">Loading scans...</p>';
    el.innerHTML = '<p style="color:var(--text-muted)">Loading...</p>';
    try {
        const sites = await API.req('GET', '/sites');
        const site = sites.find(s => s.id === siteId);
        if (!scans?.length) {
            el.innerHTML = `<a href="#" class="back-link" onclick="loadSites();return false">&larr; Back to sites</a>
                <div class="empty-state"><div class="icon">\uD83D\uDD0D</div><p>No scans yet for ${esc(site?.name || '')}</p>
                <button class="btn btn-green" onclick="startScan(${siteId},this)">Run First Scan</button></div>`;
            return;
        }
        const completedScans = scans.filter(s => s.status === 'completed');
        const compareBtn = completedScans.length >= 2
            ? `<button class="btn btn-outline btn-sm" id="compare-toggle-btn" onclick="toggleCompareMode()" aria-pressed="false">Compare Scans</button>`
            : '';
        el.innerHTML = `<a href="#" class="back-link" onclick="loadSites();return false">&larr; Back to sites</a>
            <h2 style="margin-bottom:16px">${esc(site?.name || '')}</h2>
            <div class="sites-list">${scans.map(s => `
                <div class="site-card" tabindex="0" role="button" data-action="open-scan" data-scan-id="${s.id}" onclick="openScan(${s.id})" aria-label="View details for Scan #${s.id}, status: ${s.status}">
                    <div class="site-info">
                        ${s.score !== null ? `<div class="score-ring ${scoreClass(s.score)}" aria-label="Score: ${s.score.toFixed(0)}">${s.score.toFixed(0)}</div>` : `<div class="score-ring" style="background:var(--surface-2);color:var(--text-dim);border-color:var(--border)" aria-label="${s.status === 'running' ? 'Scan running' : 'No score yet'}">${s.status === 'running' ? '...' : '--'}</div>`}
        const site = sites?.find(s => s.id === siteId);
        el.innerHTML = `
            <a href="#" class="back-link" onclick="loadSites();return false">&#x2190; Back to sites</a>
            <div class="site-header">
                <h2>${esc(site?.name || 'Site')}</h2>
                <button class="btn btn-sm btn-green" onclick="startScan(${siteId})">Scan Now</button>
            </div>
            <details class="scan-filters" id="scan-filter-panel">
                <summary class="filter-summary">Filter &amp; Sort
                    <span id="filter-badge" class="filter-active-badge" hidden aria-label="Filters are active"></span>
                </summary>
                <div class="filter-fields">
                    <div class="filter-group">
                        <label for="filter-status">Status</label>
                        <select id="filter-status" onchange="scanFilters.status=this.value">
                            <option value="">All statuses</option>
                            <option value="completed">Completed</option>
                            <option value="failed">Failed</option>
                            <option value="running">Running</option>
                            <option value="pending">Pending</option>
                        </select>
                    </div>
                    <div class="filter-group">
                        <label for="filter-min-score">Min score</label>
                        <input type="number" id="filter-min-score" min="0" max="100" placeholder="0"
                            oninput="scanFilters.min_score=this.value" class="filter-input">
                    </div>
                    <div class="filter-group">
                        <label for="filter-max-score">Max score</label>
                        <input type="number" id="filter-max-score" min="0" max="100" placeholder="100"
                            oninput="scanFilters.max_score=this.value" class="filter-input">
                    </div>
                    <div class="filter-group">
                        <label for="filter-sort">Sort by</label>
                        <select id="filter-sort" onchange="scanFilters.sort=this.value">
                            <option value="created_at">Date</option>
                            <option value="score">Score</option>
                            <option value="total_issues">Issues</option>
                        </select>
                    </div>
                    <div class="filter-group">
                        <label for="filter-order">Order</label>
                        <select id="filter-order" onchange="scanFilters.order=this.value">
                            <option value="desc">Newest first</option>
                            <option value="asc">Oldest first</option>
                        </select>
                    </div>
                    <div class="filter-actions">
                        <button class="btn btn-sm btn-primary" onclick="applyScanFilters()">Apply</button>
                        <button class="btn btn-sm btn-outline" onclick="resetScanFilters()">Reset</button>
                    </div>
                </div>
            </details>
            <p id="scan-count" role="status" aria-live="polite" class="scan-count-label"></p>
            <div id="scan-list"></div>
            <div class="pagination" id="scan-pagination" aria-label="Scan list pagination"></div>`;
        await _renderScans(siteId);
    } catch (e) {
        console.error(e);
        document.getElementById('main-content').innerHTML = '<p style="color:var(--red)">Failed to load site.</p>';
    }
}

function _updateFilterBadge() {
    const badge = document.getElementById('filter-badge');
    if (!badge) return;
    const active = scanFilters.status || scanFilters.min_score !== '' || scanFilters.max_score !== '' ||
        scanFilters.sort !== 'created_at' || scanFilters.order !== 'desc';
    badge.hidden = !active;
}

async function applyScanFilters() {
    scanPage = 0;
    _updateFilterBadge();
    await _renderScans(currentSiteId);
}

async function resetScanFilters() {
    scanFilters = { status: '', min_score: '', max_score: '', sort: 'created_at', order: 'desc' };
    scanPage = 0;
    const g = (id) => document.getElementById(id);
    if (g('filter-status')) g('filter-status').value = '';
    if (g('filter-min-score')) g('filter-min-score').value = '';
    if (g('filter-max-score')) g('filter-max-score').value = '';
    if (g('filter-sort')) g('filter-sort').value = 'created_at';
    if (g('filter-order')) g('filter-order').value = 'desc';
    _updateFilterBadge();
    await _renderScans(currentSiteId);
}

async function _renderScans(siteId) {
    const listEl = document.getElementById('scan-list');
    const countEl = document.getElementById('scan-count');
    const pagEl = document.getElementById('scan-pagination');
    if (!listEl) return;
    listEl.innerHTML = '<p style="color:var(--text-muted)">Loading...</p>';
    const params = new URLSearchParams({ limit: SCAN_PAGE_SIZE, offset: scanPage * SCAN_PAGE_SIZE });
    if (scanFilters.status) params.set('status', scanFilters.status);
    if (scanFilters.min_score !== '') params.set('min_score', scanFilters.min_score);
    if (scanFilters.max_score !== '') params.set('max_score', scanFilters.max_score);
    if (scanFilters.sort) params.set('sort', scanFilters.sort);
    if (scanFilters.order) params.set('order', scanFilters.order);
    try {
        const scans = await API.req('GET', `/sites/${siteId}/scans?${params}`);
        if (!scans) return;
        const hasMore = scans.length === SCAN_PAGE_SIZE;
        const start = scanPage * SCAN_PAGE_SIZE + 1;
        const isFiltered = scanFilters.status || scanFilters.min_score !== '' || scanFilters.max_score !== '';
        if (countEl) {
            countEl.textContent = scans.length
                ? `Showing ${start}\u2013${start + scans.length - 1} scan${scans.length !== 1 ? 's' : ''}`
                : scanPage > 0 ? 'No more scans.' : 'No scans match the current filters.';
        }
        listEl.innerHTML = scans.length
            ? `<div class="sites-list">${scans.map(s => `
                <div class="site-card" onclick="openScan(${s.id})">
                    <div class="site-info">
                        ${s.score !== null
                            ? `<div class="score-ring ${scoreClass(s.score)}">${s.score.toFixed(0)}</div>`
                            : `<div class="score-ring" style="background:var(--surface-2);color:var(--text-dim);border-color:var(--border)">${s.status === 'running' ? '...' : '--'}</div>`}
                        <div>
                            <div class="name">Scan #${s.id} \u2014 ${esc(s.status)}</div>
                            <div class="url">${s.pages_scanned} pages, ${s.total_issues} issues \u2014 ${timeAgo(s.completed_at || s.created_at)}</div>
                        </div>
                    </div>
                    <div class="severity-bar">
                        ${s.critical_count ? `<span class="badge badge-critical">${s.critical_count} Critical</span>` : ''}
                        ${s.serious_count ? `<span class="badge badge-serious">${s.serious_count} Serious</span>` : ''}
                        ${s.moderate_count ? `<span class="badge badge-moderate">${s.moderate_count} Moderate</span>` : ''}
                        ${s.minor_count ? `<span class="badge badge-minor">${s.minor_count} Minor</span>` : ''}
                    </div>
                </div>`).join('')}</div>`
            : `<div class="empty-state">
                <div class="icon">\uD83D\uDD0D</div>
                <p>${isFiltered ? 'No scans match the current filters.' : 'No scans yet.'}</p>
                ${!isFiltered ? `<button class="btn btn-green" style="margin-top:12px" onclick="startScan(${siteId})">Run First Scan</button>` : ''}
               </div>`;
        if (pagEl) {
            pagEl.innerHTML = (scanPage > 0 || hasMore)
                ? `<button class="btn btn-sm btn-outline" onclick="changeScanPage(-1)"${scanPage === 0 ? ' disabled' : ''} aria-label="Previous page">&#x2190; Previous</button>
                   <span class="page-info">Page ${scanPage + 1}</span>
                   <button class="btn btn-sm btn-outline" onclick="changeScanPage(1)"${!hasMore ? ' disabled' : ''} aria-label="Next page">Next &#x2192;</button>`
                : '';
        }
    } catch (e) {
        console.error(e);
        listEl.innerHTML = '<p style="color:var(--red)">Failed to load scans.</p>';
    }
}

async function changeScanPage(delta) {
    scanPage = Math.max(0, scanPage + delta);
    await _renderScans(currentSiteId);
    document.getElementById('scan-list')?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px">
                <h2>${esc(site?.name || '')}</h2>
                ${compareBtn}
            </div>
            <div id="compare-toolbar" style="display:none" role="status" aria-live="polite"></div>
            <div class="sites-list" id="scans-list">${renderScanCards(scans)}</div>`;
    } catch (e) { console.error(e); }
}

function renderScanCards(scans) {
    return scans.map(s => {
        const scoreEl = s.score !== null
            ? `<div class="score-ring ${scoreClass(s.score)}">${s.score.toFixed(0)}</div>`
            : `<div class="score-ring" style="background:var(--surface-2);color:var(--text-dim);border-color:var(--border)">${s.status === 'running' ? '...' : '--'}</div>`;
        const badges = [
            s.critical_count ? `<span class="badge badge-critical">${s.critical_count} Critical</span>` : '',
            s.serious_count  ? `<span class="badge badge-serious">${s.serious_count} Serious</span>`   : '',
            s.moderate_count ? `<span class="badge badge-moderate">${s.moderate_count} Moderate</span>` : '',
            s.minor_count    ? `<span class="badge badge-minor">${s.minor_count} Minor</span>`          : '',
        ].join('');
        const isCompleted = s.status === 'completed';
        return `<div class="site-card${compareMode && isCompleted ? ' scan-card-compare' : ''}" id="scan-card-${s.id}"
                     onclick="${compareMode && isCompleted ? `toggleCompareSelect(${s.id})` : `openScan(${s.id})`}"
                     role="${compareMode && isCompleted ? 'checkbox' : 'button'}"
                     aria-checked="${compareMode && isCompleted ? 'false' : undefined}"
                     tabindex="0"
                     onkeydown="if(event.key==='Enter'||event.key===' '){this.click();event.preventDefault()}">
            <div class="site-info">
                ${scoreEl}
                <div>
                    <div class="name">Scan #${s.id} &mdash; ${s.status}</div>
                    <div class="url">${s.pages_scanned} pages, ${s.total_issues} issues &mdash; ${timeAgo(s.completed_at || s.created_at)}</div>
                </div>
            </div>
            <div class="severity-bar">${badges}</div>
        </div>`;
    }).join('');
}

function toggleCompareMode() {
    compareMode = !compareMode;
    compareSelected = [];
    const btn = document.getElementById('compare-toggle-btn');
    if (btn) {
        btn.textContent = compareMode ? 'Cancel' : 'Compare Scans';
        btn.setAttribute('aria-pressed', compareMode ? 'true' : 'false');
        btn.classList.toggle('btn-danger', compareMode);
        btn.classList.toggle('btn-outline', !compareMode);
    }
    updateCompareToolbar();
    // Re-render cards to add/remove checkboxes
    const listEl = document.getElementById('scans-list');
    if (!listEl) return;
    // Re-fetch scans from existing rendered data via DOM isn't reliable; re-open
    openSite(currentSiteId);
}

function toggleCompareSelect(scanId) {
    const card = document.getElementById(`scan-card-${scanId}`);
    const idx = compareSelected.indexOf(scanId);
    if (idx > -1) {
        compareSelected.splice(idx, 1);
        card?.classList.remove('selected');
        card?.setAttribute('aria-checked', 'false');
    } else {
        if (compareSelected.length >= 2) {
            showToast('Select exactly 2 scans to compare.', 'info');
            return;
        }
        compareSelected.push(scanId);
        card?.classList.add('selected');
        card?.setAttribute('aria-checked', 'true');
    }
    updateCompareToolbar();
}

function updateCompareToolbar() {
    const toolbar = document.getElementById('compare-toolbar');
    if (!toolbar) return;
    if (!compareMode) { toolbar.style.display = 'none'; return; }
    toolbar.style.display = 'block';
    const count = compareSelected.length;
    const readyBtn = count === 2
        ? `<button class="btn btn-primary btn-sm" onclick="runComparison()">Compare Selected</button>`
        : `<button class="btn btn-primary btn-sm" disabled aria-disabled="true">Compare Selected</button>`;
    toolbar.innerHTML = `<div class="compare-toolbar">
        <p>${count === 0 ? 'Select 2 scans to compare' : count === 1 ? '1 scan selected — select one more' : '2 scans selected'}</p>
        ${readyBtn}
    </div>`;
}

async function runComparison() {
    if (compareSelected.length !== 2) return;
    const [a, b] = compareSelected;
    try {
        const result = await API.req('GET', `/scans/compare?scan_a=${a}&scan_b=${b}`);
        showComparisonModal(result);
    } catch (e) { showToast(e.message, 'error'); }
}

function deltaDisplay(value, invertedPolarity = false) {
    // invertedPolarity = true means lower is better (issues, critical counts)
    if (value === 0) return { text: '±0', cls: 'delta-neutral' };
    const better = invertedPolarity ? value < 0 : value > 0;
    const sign = value > 0 ? '+' : '';
    return { text: `${sign}${value}`, cls: better ? 'delta-better' : 'delta-worse' };
}

function showComparisonModal(r) {
    const existing = document.getElementById('compare-modal');
    if (existing) existing.remove();

    const scoreA = r.scan_a.score !== null ? r.scan_a.score.toFixed(1) : '--';
    const scoreB = r.scan_b.score !== null ? r.scan_b.score.toFixed(1) : '--';
    const scoreDeltaHtml = r.score_delta !== null
        ? (() => { const d = deltaDisplay(r.score_delta, false); return `<div class="delta-cell"><div class="delta-label">Score</div><div class="delta-value ${d.cls}">${d.text}</div></div>`; })()
        : '';

    const deltas = [
        { label: 'Issues',    value: r.issues_delta,   inv: true },
        { label: 'Critical',  value: r.critical_delta,  inv: true },
        { label: 'Serious',   value: r.serious_delta,   inv: true },
        { label: 'Moderate',  value: r.moderate_delta,  inv: true },
        { label: 'Minor',     value: r.minor_delta,     inv: true },
    ];
    const deltaGrid = `<div class="compare-delta-grid">
        ${scoreDeltaHtml}
        ${deltas.map(d => { const dd = deltaDisplay(d.value, d.inv); return `<div class="delta-cell"><div class="delta-label">${d.label}</div><div class="delta-value ${dd.cls}">${dd.text}</div></div>`; }).join('')}
    </div>`;

    const fixedHtml = r.fixed_rules.length
        ? `<ul>${r.fixed_rules.map(rule => `<li class="rule-fixed" role="listitem">&#10003; ${esc(rule)}</li>`).join('')}</ul>`
        : `<p class="compare-rules-empty">No rules fixed between these scans.</p>`;
    const newHtml = r.new_rules.length
        ? `<ul>${r.new_rules.map(rule => `<li class="rule-new" role="listitem">&#43; ${esc(rule)}</li>`).join('')}</ul>`
        : `<p class="compare-rules-empty">No new rules introduced between these scans.</p>`;

    const modal = document.createElement('div');
    modal.id = 'compare-modal';
    modal.className = 'modal-overlay active';
    modal.setAttribute('role', 'dialog');
    modal.setAttribute('aria-modal', 'true');
    modal.setAttribute('aria-label', `Comparison of Scan #${r.scan_a.id} and Scan #${r.scan_b.id}`);
    modal.innerHTML = `<div class="modal compare-modal">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:20px">
            <h3 style="margin:0">Scan Comparison</h3>
            <button class="btn btn-outline btn-sm" onclick="document.getElementById('compare-modal').remove()" aria-label="Close comparison">&#10005;</button>
        </div>
        <div class="compare-header" aria-label="Score comparison">
            <div class="compare-scan-box">
                <div class="label">Scan #${r.scan_a.id} (Baseline)</div>
                <div class="score-large ${r.scan_a.score !== null ? scoreClass(r.scan_a.score) : ''}" style="color:inherit">${scoreA}</div>
                <div class="scan-meta">${r.scan_a.pages_scanned} pages &middot; ${r.scan_a.total_issues} issues</div>
            </div>
            <div class="compare-arrow" aria-hidden="true">&rarr;</div>
            <div class="compare-scan-box">
                <div class="label">Scan #${r.scan_b.id} (Compared)</div>
                <div class="score-large ${r.scan_b.score !== null ? scoreClass(r.scan_b.score) : ''}" style="color:inherit">${scoreB}</div>
                <div class="scan-meta">${r.scan_b.pages_scanned} pages &middot; ${r.scan_b.total_issues} issues</div>
            </div>
        </div>
        <h4 style="margin-bottom:10px;font-size:0.85rem;text-transform:uppercase;letter-spacing:0.5px;color:var(--text-muted)">Changes</h4>
        ${deltaGrid}
        <div class="compare-rules">
            <div class="compare-rules-section">
                <h4 style="color:var(--green)">&#10003; Rules Fixed (${r.fixed_rules.length})</h4>
                ${fixedHtml}
            </div>
            <div class="compare-rules-section">
                <h4 style="color:var(--red)">&#43; New Rules Introduced (${r.new_rules.length})</h4>
                ${newHtml}
            </div>
        </div>
    </div>`;

    // Close on backdrop click
    modal.addEventListener('click', (e) => { if (e.target === modal) modal.remove(); });
    // Close on Escape
    modal.addEventListener('keydown', (e) => { if (e.key === 'Escape') modal.remove(); });
    document.body.appendChild(modal);
    // Focus the close button for accessibility
    modal.querySelector('button[aria-label="Close comparison"]')?.focus();
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
    currentView = 'scan-detail'; currentScanId = scanId;
    const el = document.getElementById('dash-content');
    el.innerHTML = '<p style="color:var(--text-muted)">Loading issues...</p>';
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
                    ${scan.score !== null ? `<div class="score-ring ${scoreClass(scan.score)}" style="width:64px;height:64px;font-size:1.2rem" aria-label="Accessibility score: ${scan.score.toFixed(0)} out of 100">${scan.score.toFixed(0)}</div>` : ''}
                <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px">
                    <h3>Scan #${scan.id}</h3>
                    <div style="display:flex;align-items:center;gap:12px">
                        ${scan.score !== null ? `<div class="score-ring ${scoreClass(scan.score)}" style="width:64px;height:64px;font-size:1.2rem">${scan.score.toFixed(0)}</div>` : ''}
                        ${scan.status === 'completed' ? `<button class="btn btn-outline btn-sm" id="share-btn-${scan.id}" onclick="toggleSharePanel(${scan.id})" aria-expanded="false" aria-controls="share-panel-${scan.id}">&#x1F517; Share</button>` : ''}
                    </div>
                </div>
                <div id="share-panel-${scan.id}" class="share-panel" hidden>
                    <div class="share-panel-inner">
                        <p class="share-panel-label">Share this report publicly &mdash; anyone with the link can view it.</p>
                        <div class="share-link-row">
                            <input type="text" id="share-link-input-${scan.id}" class="share-link-input" readonly aria-label="Public report link" placeholder="Generating link&hellip;">
                            <button class="btn btn-sm btn-primary" onclick="copyShareLink(${scan.id})" aria-label="Copy link to clipboard">Copy</button>
                        </div>
                        <div class="share-actions">
                            <button class="btn btn-sm btn-outline" onclick="generateShareLink(${scan.id})">&#x21BB; Regenerate</button>
                            <button class="btn btn-sm btn-danger" onclick="revokeShareLink(${scan.id})">Revoke link</button>
                        </div>
                    </div>
                </div>
                <p style="color:var(--text-muted);margin:8px 0">${scan.pages_scanned} pages scanned &mdash; ${scan.total_issues} issues found</p>
                <div class="severity-bar">
                    <span class="severity-count" style="background:var(--red-light);color:var(--red)">${scan.critical_count} Critical</span>
                    <span class="severity-count" style="background:var(--serious-light);color:var(--serious)">${scan.serious_count} Serious</span>
                    <span class="severity-count" style="background:var(--amber-light);color:var(--amber)">${scan.moderate_count} Moderate</span>
                    <span class="severity-count" style="background:var(--blue-light);color:var(--blue)">${scan.minor_count} Minor</span>
                <div class="scan-summary">
                    <div class="scan-summary-info">
                        <h3>Scan #${scan.id}</h3>
                        <p style="color:var(--text-muted);margin:8px 0">${scan.pages_scanned} pages scanned &mdash; ${scan.total_issues} issues found</p>
                        <div class="severity-bar">
                            <span class="severity-count" style="background:var(--red-light);color:var(--red)">${scan.critical_count} Critical</span>
                            <span class="severity-count" style="background:#fff7ed;color:#c2410c">${scan.serious_count} Serious</span>
                            <span class="severity-count" style="background:var(--amber-light);color:var(--amber)">${scan.moderate_count} Moderate</span>
                            <span class="severity-count" style="background:var(--blue-light);color:var(--blue)">${scan.minor_count} Minor</span>
                        </div>
                    </div>
                    ${scan.score !== null ? buildGauge(scan.score, 140) : ''}
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
        animateGauges(el);
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
        await API.req('POST', '/sites', { name: form.name.value, url: form.url.value });
        closeAddModal?.();
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
        const scan = await API.req('POST', `/sites/${siteId}/scan`);
        if (!scan) return;
        showToast('Scan started!');
        trackScanProgress(siteId, scan.id);
    } catch (e) { showToast(e.message, 'error'); }
}

function trackScanProgress(siteId, scanId) {
    const progressId = `scan-progress-${siteId}`;
    let banner = document.getElementById(progressId);
    if (!banner) {
        banner = document.createElement('div');
        banner.id = progressId;
        banner.className = 'scan-progress-banner';
        banner.setAttribute('role', 'status');
        banner.setAttribute('aria-live', 'polite');
        banner.setAttribute('aria-label', 'Scan in progress');
        const content = document.getElementById('main-content');
        content.insertBefore(banner, content.firstChild);
    }
    banner.innerHTML = `
        <div class="scan-progress-header">
            <span class="scan-progress-text" id="scan-progress-text-${siteId}">Connecting…</span>
        </div>
        <div class="scan-progress-bar-track"
             role="progressbar" aria-valuenow="0" aria-valuemin="0" aria-valuemax="100"
             aria-labelledby="scan-progress-text-${siteId}">
            <div class="scan-progress-bar-fill" id="scan-progress-fill-${siteId}" style="width:0%"></div>
        </div>`;

    const es = new EventSource(`/api/scans/${scanId}/stream?token=${API.token}`);

    es.onmessage = (e) => {
        const data = JSON.parse(e.data);
        const fill = document.getElementById(`scan-progress-fill-${siteId}`);
        const text = document.getElementById(`scan-progress-text-${siteId}`);
        const track = banner.querySelector('[role=progressbar]');
        if (!fill || !text) return;

        let pct = 0;
        if (data.status === 'crawling') {
            pct = 10;
            text.textContent = 'Crawling pages…';
        } else if (data.status === 'scanning') {
            if (data.pages_total) {
                pct = 10 + Math.round((data.pages_done / data.pages_total) * 85);
                text.textContent = `Scanning page ${data.pages_done + 1} of ${data.pages_total}…`;
            } else {
                pct = 15;
                text.textContent = 'Scanning…';
            }
        } else if (data.status === 'completed') {
            pct = 100;
            text.textContent = `Scan complete — ${data.pages_total || data.pages_done} page(s) scanned`;
        } else if (data.status === 'failed') {
            pct = 100;
            text.textContent = 'Scan failed.';
            if (fill) fill.style.background = 'var(--red)';
        }

        if (fill) fill.style.width = `${pct}%`;
        if (track) track.setAttribute('aria-valuenow', pct);

        if (data.status === 'completed' || data.status === 'failed') {
            es.close();
            setTimeout(async () => {
                banner.remove();
                await loadStats();
                if (currentSiteId === siteId) await openSite(siteId);
                else await loadSites();
            }, 1500);
        }
    };

    es.onerror = () => {
        es.close();
        const text = document.getElementById(`scan-progress-text-${siteId}`);
        if (text) text.textContent = 'Lost connection — refreshing…';
async function startScan(siteId) {
    try {
        await API.req('POST', `/sites/${siteId}/scan`);
        showToast('Scan started! Refresh in a few seconds to see results.');
        setTimeout(async () => {
            banner?.remove();
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
        }, 3000);
    };
}

async function deleteSite(siteId) {
    if (!confirm('Delete this site and all its scans?')) return;
    try {
        await API.req('DELETE', `/sites/${siteId}`);
        selectedSites.delete(siteId);
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
// Badge
function showBadge(siteId, siteName) {
    const badgeUrl = `${window.location.origin}/api/sites/${siteId}/badge.svg`;
    document.getElementById('badge-img').src = badgeUrl;
    document.getElementById('badge-img').alt = `Accessibility score badge for ${siteName}`;
    document.getElementById('badge-site-name').textContent = siteName;
    document.getElementById('badge-html-code').textContent =
        `<img src="${badgeUrl}" alt="accessibility score" />`;
    document.getElementById('badge-md-code').textContent =
        `![accessibility score](${badgeUrl})`;
    document.getElementById('badge-modal').classList.add('active');
    document.getElementById('close-badge-modal').focus();
}

function copyBadgeCode(type) {
    const id = type === 'html' ? 'badge-html-code' : 'badge-md-code';
    const text = document.getElementById(id).textContent;
    const btn = document.querySelector(`[onclick="copyBadgeCode('${type}')"]`);
    navigator.clipboard.writeText(text).then(() => {
        btn.textContent = 'Copied!';
        btn.classList.add('copied');
        setTimeout(() => { btn.textContent = 'Copy'; btn.classList.remove('copied'); }, 2000);
    }).catch(() => showToast('Copy failed — please copy manually', 'error'));
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
// Settings page
async function initSettings() {
    if (!API.isLoggedIn()) { window.location.href = '/login'; return; }
    document.getElementById('logout-btn')?.addEventListener('click', () => API.logout());
    document.getElementById('open-delete-modal')?.addEventListener('click', openDeleteModal);
    document.getElementById('close-delete-modal')?.addEventListener('click', closeDeleteModal);
    document.getElementById('delete-modal')?.addEventListener('click', (e) => {
        if (e.target === document.getElementById('delete-modal')) closeDeleteModal();
    });
    document.getElementById('profile-form')?.addEventListener('submit', saveProfile);
    document.getElementById('password-form')?.addEventListener('submit', changePassword);
    document.getElementById('delete-form')?.addEventListener('submit', deleteAccount);
    await loadProfile();
}

async function loadProfile() {
    try {
        const user = await API.req('GET', '/auth/me');
        if (!user) return;
        const emailInput = document.getElementById('profile-email');
        if (emailInput) emailInput.value = user.email;
        const planBadge = document.getElementById('profile-plan');
        if (planBadge) planBadge.textContent = user.plan;
        const since = document.getElementById('profile-since');
        if (since) {
            const d = new Date(user.created_at);
            since.textContent = d.toLocaleDateString(undefined, { year: 'numeric', month: 'long', day: 'numeric' });
        }
    } catch (e) { console.error(e); }
}

async function saveProfile(e) {
    e.preventDefault();
    const banner = document.getElementById('profile-banner');
    const btn = e.target.querySelector('button[type=submit]');
    btn.disabled = true;
    hideBanner(banner);
    try {
        const email = document.getElementById('profile-email').value.trim();
        await API.req('PUT', '/auth/profile', { email });
        showBanner(banner, 'Email updated successfully.', 'success');
        showToast('Profile saved');
    } catch (err) {
        showBanner(banner, err.message, 'error');
    } finally {
        btn.disabled = false;
    }
}

async function changePassword(e) {
    e.preventDefault();
    const banner = document.getElementById('password-banner');
    const btn = e.target.querySelector('button[type=submit]');
    const newPw = document.getElementById('new-password').value;
    const confirmPw = document.getElementById('confirm-password').value;
    hideBanner(banner);
    if (newPw !== confirmPw) { showBanner(banner, 'New passwords do not match.', 'error'); return; }
    btn.disabled = true;
    try {
        await API.req('PUT', '/auth/password', {
            current_password: document.getElementById('current-password').value,
            new_password: newPw,
        });
        e.target.reset();
        showBanner(banner, 'Password changed successfully.', 'success');
        showToast('Password updated');
    } catch (err) {
        showBanner(banner, err.message, 'error');
    } finally {
        btn.disabled = false;
    }
}

function openDeleteModal() {
    const modal = document.getElementById('delete-modal');
    modal.classList.add('active');
    document.getElementById('delete-password')?.focus();
}

function closeDeleteModal() {
    document.getElementById('delete-modal').classList.remove('active');
    document.getElementById('delete-form')?.reset();
    hideBanner(document.getElementById('delete-banner'));
}

async function deleteAccount(e) {
    e.preventDefault();
    const banner = document.getElementById('delete-banner');
    const btn = e.target.querySelector('button[type=submit]');
    btn.disabled = true;
    hideBanner(banner);
    try {
        await API.req('DELETE', '/auth/account', { password: document.getElementById('delete-password').value });
        API.logout();
    } catch (err) {
        showBanner(banner, err.message, 'error');
        btn.disabled = false;
    }
}

function showBanner(el, msg, type) {
    if (!el) return;
    el.textContent = msg;
    el.className = `settings-banner ${type}`;
    el.hidden = false;
}

function hideBanner(el) {
    if (!el) return;
    el.hidden = true;
    el.textContent = '';
// Share
function toggleSharePanel(scanId) {
    const panel = document.getElementById(`share-panel-${scanId}`);
    const btn = document.getElementById(`share-btn-${scanId}`);
    const isOpen = !panel.hidden;
    panel.hidden = isOpen;
    btn.setAttribute('aria-expanded', String(!isOpen));
    if (!isOpen) {
        const input = document.getElementById(`share-link-input-${scanId}`);
        if (!input.value) generateShareLink(scanId);
    }
}

async function generateShareLink(scanId) {
    const input = document.getElementById(`share-link-input-${scanId}`);
    input.value = 'Generating…';
    try {
        const data = await API.req('POST', `/scans/${scanId}/share`);
        input.value = data.share_url;
    } catch (e) {
        input.value = '';
        showToast(e.message, 'error');
    }
}

async function copyShareLink(scanId) {
    const input = document.getElementById(`share-link-input-${scanId}`);
    if (!input.value || input.value === 'Generating…') return;
    try {
        await navigator.clipboard.writeText(input.value);
        showToast('Link copied to clipboard!');
    } catch (_) {
        input.select();
        document.execCommand('copy');
        showToast('Link copied!');
    }
}

async function revokeShareLink(scanId) {
    if (!confirm('Revoke the public share link? Anyone with the current link will lose access.')) return;
    try {
        await API.req('DELETE', `/scans/${scanId}/share`);
        const input = document.getElementById(`share-link-input-${scanId}`);
        input.value = '';
        showToast('Share link revoked.', 'info');
    } catch (e) { showToast(e.message, 'error'); }
}
