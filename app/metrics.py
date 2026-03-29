"""Prometheus metrics definitions for AccessWave.

All metrics are module-level singletons so they are shared across the
process.  Import this module from scan_runner and auth_router to record
domain-specific events; the HTTP-level metrics are handled automatically
by prometheus-fastapi-instrumentator in main.py.
"""

from prometheus_client import Counter, Gauge, Histogram

# ---------------------------------------------------------------------------
# Scan lifecycle
# ---------------------------------------------------------------------------

SCANS_STARTED = Counter(
    "accesswave_scans_started_total",
    "Total number of scans that have been enqueued / started",
)

SCANS_COMPLETED = Counter(
    "accesswave_scans_completed_total",
    "Total number of scans that finished with status=completed",
)

SCANS_FAILED = Counter(
    "accesswave_scans_failed_total",
    "Total number of scans that finished with status=failed",
)

ACTIVE_SCANS = Gauge(
    "accesswave_active_scans",
    "Number of scans currently in the running state",
)

# ---------------------------------------------------------------------------
# Scan results
# ---------------------------------------------------------------------------

SCAN_SCORE = Histogram(
    "accesswave_scan_score",
    "Accessibility score (0–100) distribution across completed scans",
    buckets=[10, 20, 30, 40, 50, 60, 70, 75, 80, 85, 90, 95, 100],
)

SCAN_DURATION_SECONDS = Histogram(
    "accesswave_scan_duration_seconds",
    "Wall-clock seconds from scan start to scan completion",
    buckets=[5, 10, 30, 60, 120, 300, 600],
)

SCAN_PAGES_SCANNED = Histogram(
    "accesswave_scan_pages_scanned",
    "Number of pages successfully scanned per run",
    buckets=[1, 2, 5, 10, 20, 50, 100, 200],
)

ISSUES_FOUND = Counter(
    "accesswave_issues_found_total",
    "Cumulative accessibility issues found, labelled by WCAG severity",
    ["severity"],  # critical | serious | moderate | minor
)

# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------

AUTH_ATTEMPTS = Counter(
    "accesswave_auth_attempts_total",
    "Login/registration attempts labelled by endpoint and outcome",
    ["endpoint", "outcome"],  # endpoint: login|register  outcome: success|failure
)
