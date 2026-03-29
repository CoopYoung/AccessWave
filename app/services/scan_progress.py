"""In-memory scan progress store for Server-Sent Events streaming.

Keyed by scan_id.  The scan runner writes here as each page is processed;
the SSE endpoint reads here and pushes updates to the browser.

The store is intentionally process-local and ephemeral — it is cleared a few
seconds after a scan finishes so that stale entries do not accumulate.
"""
from __future__ import annotations

from typing import Dict


# {scan_id: {"pages_done": int, "pages_total": int | None, "status": str, "current_url": str}}
_progress: Dict[int, dict] = {}


def update_progress(
    scan_id: int,
    *,
    pages_done: int,
    pages_total: int | None,
    status: str,
    current_url: str = "",
) -> None:
    _progress[scan_id] = {
        "pages_done": pages_done,
        "pages_total": pages_total,
        "status": status,
        "current_url": current_url,
    }


def get_progress(scan_id: int) -> dict | None:
    return _progress.get(scan_id)


def clear_progress(scan_id: int) -> None:
    _progress.pop(scan_id, None)
