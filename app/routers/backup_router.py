"""Backup and restore endpoints.

GET  /api/backup/export  – Download all user data as a JSON file.
POST /api/backup/import  – Upload a previously exported JSON file to restore data.

Import is additive: sites that already exist (matched by URL) are skipped; new
sites (and their scans/issues) are created fresh.  Completed scans that share
an identical created_at timestamp with an existing scan on the same site are
also skipped to prevent duplicates on repeated imports.
"""

import datetime
import json

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_db
from app.models import Issue, Scan, Site, User

router = APIRouter(prefix="/api/backup", tags=["backup"])
logger = structlog.get_logger("accesswave.backup")

_EXPORT_VERSION = "1.0"
_MAX_IMPORT_BYTES = 50 * 1024 * 1024  # 50 MB


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

@router.get("/export")
async def export_data(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Stream the authenticated user's data as a JSON file download."""
    sites_result = await db.execute(
        select(Site).where(Site.user_id == user.id).order_by(Site.created_at)
    )
    sites = sites_result.scalars().all()

    sites_payload = []
    for site in sites:
        scans_result = await db.execute(
            select(Scan).where(Scan.site_id == site.id).order_by(Scan.created_at)
        )
        scans = scans_result.scalars().all()

        scans_payload = []
        for scan in scans:
            issues_result = await db.execute(
                select(Issue).where(Issue.scan_id == scan.id)
            )
            issues = issues_result.scalars().all()

            scans_payload.append({
                "status": scan.status,
                "pages_scanned": scan.pages_scanned,
                "total_issues": scan.total_issues,
                "critical_count": scan.critical_count,
                "serious_count": scan.serious_count,
                "moderate_count": scan.moderate_count,
                "minor_count": scan.minor_count,
                "score": scan.score,
                "started_at": scan.started_at.isoformat() if scan.started_at else None,
                "completed_at": scan.completed_at.isoformat() if scan.completed_at else None,
                "created_at": scan.created_at.isoformat() if scan.created_at else None,
                "issues": [
                    {
                        "page_url": issue.page_url,
                        "rule_id": issue.rule_id,
                        "severity": issue.severity,
                        "wcag_criteria": issue.wcag_criteria,
                        "message": issue.message,
                        "element_html": issue.element_html,
                        "selector": issue.selector,
                        "how_to_fix": issue.how_to_fix,
                    }
                    for issue in issues
                ],
            })

        sites_payload.append({
            "url": site.url,
            "name": site.name,
            "schedule": site.schedule,
            "created_at": site.created_at.isoformat() if site.created_at else None,
            "scans": scans_payload,
        })

    payload = {
        "version": _EXPORT_VERSION,
        "exported_at": datetime.datetime.utcnow().isoformat(),
        "user": {
            "email": user.email,
            "plan": user.plan,
        },
        "sites": sites_payload,
    }

    data = json.dumps(payload, indent=2, ensure_ascii=False)
    filename = f"accesswave-backup-{datetime.date.today().isoformat()}.json"

    logger.info("data_exported", user_id=user.id, site_count=len(sites))

    return StreamingResponse(
        iter([data]),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------------------------------------------------------------------------
# Import
# ---------------------------------------------------------------------------

@router.post("/import", status_code=200)
async def import_data(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Import data from a previously exported backup JSON file.

    Returns counts of created vs skipped sites/scans.
    """
    raw = await file.read(_MAX_IMPORT_BYTES + 1)
    if len(raw) > _MAX_IMPORT_BYTES:
        raise HTTPException(status_code=413, detail="Backup file exceeds 50 MB limit")

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {exc}")

    if not isinstance(payload, dict) or "sites" not in payload:
        raise HTTPException(status_code=400, detail="Unrecognised backup format")

    sites_created = 0
    sites_skipped = 0
    scans_created = 0
    scans_skipped = 0

    for site_data in payload.get("sites", []):
        url = (site_data.get("url") or "").strip()
        name = (site_data.get("name") or url or "").strip()
        if not url:
            continue

        # Check if site already exists for this user
        existing = await db.execute(
            select(Site).where(Site.user_id == user.id, Site.url == url)
        )
        site = existing.scalar_one_or_none()

        if site is None:
            site = Site(
                user_id=user.id,
                url=url,
                name=name[:255],
                schedule=site_data.get("schedule", "none"),
                created_at=_parse_dt(site_data.get("created_at")),
            )
            db.add(site)
            await db.flush()  # get site.id
            sites_created += 1
        else:
            sites_skipped += 1

        # Collect existing scan timestamps to avoid duplicates
        existing_scans_res = await db.execute(
            select(Scan.created_at).where(Scan.site_id == site.id)
        )
        existing_ts = {r[0] for r in existing_scans_res.all() if r[0] is not None}

        for scan_data in site_data.get("scans", []):
            scan_created_at = _parse_dt(scan_data.get("created_at"))
            if scan_created_at and scan_created_at in existing_ts:
                scans_skipped += 1
                continue

            scan = Scan(
                site_id=site.id,
                status=scan_data.get("status", "completed"),
                pages_scanned=scan_data.get("pages_scanned", 0),
                total_issues=scan_data.get("total_issues", 0),
                critical_count=scan_data.get("critical_count", 0),
                serious_count=scan_data.get("serious_count", 0),
                moderate_count=scan_data.get("moderate_count", 0),
                minor_count=scan_data.get("minor_count", 0),
                score=scan_data.get("score"),
                started_at=_parse_dt(scan_data.get("started_at")),
                completed_at=_parse_dt(scan_data.get("completed_at")),
                created_at=scan_created_at,
            )
            db.add(scan)
            await db.flush()

            for issue_data in scan_data.get("issues", []):
                page_url = (issue_data.get("page_url") or "").strip()
                rule_id = (issue_data.get("rule_id") or "").strip()
                severity = (issue_data.get("severity") or "minor").strip()
                message = (issue_data.get("message") or "").strip()
                if not (page_url and rule_id and message):
                    continue
                issue = Issue(
                    scan_id=scan.id,
                    page_url=page_url[:2048],
                    rule_id=rule_id[:50],
                    severity=severity[:20],
                    wcag_criteria=(issue_data.get("wcag_criteria") or "")[:20] or None,
                    message=message,
                    element_html=issue_data.get("element_html"),
                    selector=(issue_data.get("selector") or "")[:500] or None,
                    how_to_fix=issue_data.get("how_to_fix"),
                )
                db.add(issue)

            scans_created += 1

    await db.commit()

    logger.info(
        "data_imported",
        user_id=user.id,
        sites_created=sites_created,
        sites_skipped=sites_skipped,
        scans_created=scans_created,
        scans_skipped=scans_skipped,
    )

    return {
        "sites_created": sites_created,
        "sites_skipped": sites_skipped,
        "scans_created": scans_created,
        "scans_skipped": scans_skipped,
    }


def _parse_dt(value) -> datetime.datetime | None:
    """Parse an ISO-8601 datetime string; return None on failure."""
    if not value:
        return None
    try:
        return datetime.datetime.fromisoformat(str(value))
    except (ValueError, TypeError):
        return None
