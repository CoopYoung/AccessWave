import asyncio
import datetime
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel, HttpUrl
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.config import settings
from app.database import get_db
from app.models import Issue, Scan, Site, User
from app.services.scan_runner import run_scan

router = APIRouter(prefix="/api", tags=["scans"])


class SiteCreate(BaseModel):
    name: str
    url: HttpUrl


class SiteOut(BaseModel):
    id: int
    name: str
    url: str
    last_score: float | None = None
    last_scan_at: datetime.datetime | None = None
    created_at: datetime.datetime

    class Config:
        from_attributes = True


class ScanOut(BaseModel):
    id: int
    site_id: int
    status: str
    pages_scanned: int
    total_issues: int
    critical_count: int
    serious_count: int
    moderate_count: int
    minor_count: int
    score: float | None
    started_at: datetime.datetime | None
    completed_at: datetime.datetime | None
    created_at: datetime.datetime

    class Config:
        from_attributes = True


class IssueOut(BaseModel):
    id: int
    page_url: str
    rule_id: str
    severity: str
    wcag_criteria: str | None
    message: str
    element_html: str | None
    selector: str | None
    how_to_fix: str | None

    class Config:
        from_attributes = True


class ScanSummary(BaseModel):
    total_sites: int
    total_scans: int
    avg_score: float | None
    total_issues: int
    critical_issues: int


# --- Sites ---

@router.get("/sites", response_model=list[SiteOut])
async def list_sites(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Site).where(Site.user_id == user.id).order_by(Site.created_at.desc()))
    sites = result.scalars().all()
    out = []
    for site in sites:
        scan_result = await db.execute(
            select(Scan).where(Scan.site_id == site.id, Scan.status == "completed")
            .order_by(Scan.completed_at.desc()).limit(1)
        )
        last_scan = scan_result.scalar_one_or_none()
        out.append(SiteOut(
            id=site.id, name=site.name, url=site.url, created_at=site.created_at,
            last_score=last_scan.score if last_scan else None,
            last_scan_at=last_scan.completed_at if last_scan else None,
        ))
    return out


@router.post("/sites", response_model=SiteOut, status_code=201)
async def create_site(body: SiteCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    plan = settings.PLAN_LIMITS[user.plan]
    count = (await db.execute(select(func.count()).select_from(Site).where(Site.user_id == user.id))).scalar()
    if count >= plan["sites"]:
        raise HTTPException(status_code=403, detail=f"Site limit ({plan['sites']}) reached. Upgrade your plan.")
    site = Site(user_id=user.id, name=body.name, url=str(body.url))
    db.add(site)
    await db.commit()
    await db.refresh(site)
    return SiteOut(id=site.id, name=site.name, url=site.url, created_at=site.created_at)


@router.delete("/sites/{site_id}", status_code=204)
async def delete_site(site_id: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    site = await _get_user_site(site_id, user.id, db)
    await db.delete(site)
    await db.commit()


# --- Scans ---

@router.post("/sites/{site_id}/scan", response_model=ScanOut, status_code=201)
async def start_scan(
    site_id: int,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    site = await _get_user_site(site_id, user.id, db)
    plan = settings.PLAN_LIMITS[user.plan]

    # Check running scans
    running = (await db.execute(
        select(func.count()).select_from(Scan).where(Scan.site_id == site_id, Scan.status.in_(["pending", "running"]))
    )).scalar()
    if running > 0:
        raise HTTPException(status_code=409, detail="A scan is already running for this site.")

    scan = Scan(site_id=site.id)
    db.add(scan)
    await db.commit()
    await db.refresh(scan)

    background_tasks.add_task(_run_scan_task, scan.id, plan["pages_per_scan"])
    return scan


@router.get("/sites/{site_id}/scans", response_model=list[ScanOut])
async def list_scans(
    site_id: int, limit: int = Query(default=20, le=50),
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    await _get_user_site(site_id, user.id, db)
    result = await db.execute(
        select(Scan).where(Scan.site_id == site_id).order_by(Scan.created_at.desc()).limit(limit)
    )
    return result.scalars().all()


@router.get("/scans/{scan_id}", response_model=ScanOut)
async def get_scan(scan_id: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    scan = await _get_user_scan(scan_id, user.id, db)
    return scan


@router.get("/scans/{scan_id}/issues", response_model=list[IssueOut])
async def get_issues(
    scan_id: int,
    severity: str | None = None,
    rule_id: str | None = None,
    limit: int = Query(default=100, le=500),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_user_scan(scan_id, user.id, db)
    query = select(Issue).where(Issue.scan_id == scan_id)
    if severity:
        query = query.where(Issue.severity == severity)
    if rule_id:
        query = query.where(Issue.rule_id == rule_id)
    query = query.order_by(
        case(
            (Issue.severity == "critical", 0),
            (Issue.severity == "serious", 1),
            (Issue.severity == "moderate", 2),
            else_=3,
        ),
        Issue.id,
    ).limit(limit)
    result = await db.execute(query)
    return result.scalars().all()


# --- Dashboard stats ---

@router.get("/dashboard/stats", response_model=ScanSummary)
async def dashboard_stats(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    sites = (await db.execute(select(func.count()).select_from(Site).where(Site.user_id == user.id))).scalar() or 0
    scans = (await db.execute(
        select(func.count()).select_from(Scan)
        .join(Site).where(Site.user_id == user.id, Scan.status == "completed")
    )).scalar() or 0
    avg = (await db.execute(
        select(func.avg(Scan.score)).join(Site).where(Site.user_id == user.id, Scan.status == "completed")
    )).scalar()
    total_issues = (await db.execute(
        select(func.sum(Scan.total_issues)).join(Site).where(Site.user_id == user.id, Scan.status == "completed")
    )).scalar() or 0
    critical = (await db.execute(
        select(func.sum(Scan.critical_count)).join(Site).where(Site.user_id == user.id, Scan.status == "completed")
    )).scalar() or 0

    return ScanSummary(
        total_sites=sites, total_scans=scans,
        avg_score=round(avg, 1) if avg else None,
        total_issues=total_issues, critical_issues=critical,
    )


# --- Helpers ---

async def _get_user_site(site_id: int, user_id: int, db: AsyncSession) -> Site:
    result = await db.execute(select(Site).where(Site.id == site_id, Site.user_id == user_id))
    site = result.scalar_one_or_none()
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")
    return site


async def _get_user_scan(scan_id: int, user_id: int, db: AsyncSession) -> Scan:
    result = await db.execute(
        select(Scan).join(Site).where(Scan.id == scan_id, Site.user_id == user_id)
    )
    scan = result.scalar_one_or_none()
    if not scan:
        raise HTTPException(status_code=404, detail="Scan not found")
    return scan


async def _run_scan_task(scan_id: int, max_pages: int):
    """Wrapper to run scan in background."""
    await run_scan(scan_id, max_pages=max_pages)
