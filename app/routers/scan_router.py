import asyncio
import datetime
from ipaddress import AddressValueError, ip_address, ip_network
from typing import Literal


import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from pydantic import BaseModel, HttpUrl, field_validator
import json
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from jose import JWTError, jwt
import html as _html
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, HttpUrl
from sqlalchemy import case, func, nullslast, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.config import settings
from app.database import get_db
from app.limiter import limiter
from app.database import async_session, get_db
from app.models import Issue, Scan, Site, User
from app.services.scan_progress import get_progress
from app.services.scan_runner import run_scan

# Lazy import: only load Celery machinery when it is actually enabled so
# that the app starts fine even without Redis / celery installed.
def _dispatch_scan(scan_id: int, max_pages: int, background_tasks: BackgroundTasks) -> None:
    """Send a scan to Celery if enabled, otherwise use BackgroundTasks."""
    if settings.USE_CELERY:
        from app.tasks import celery_run_scan  # noqa: PLC0415
        celery_run_scan.delay(scan_id, max_pages)
    else:
        background_tasks.add_task(_run_scan_task, scan_id, max_pages)

router = APIRouter(prefix="/api", tags=["scans"])
logger = structlog.get_logger("accesswave.scan")

# Private / reserved CIDR blocks that must not be scanned (SSRF protection)
_BLOCKED_NETWORKS = [
    ip_network("10.0.0.0/8"),
    ip_network("172.16.0.0/12"),
    ip_network("192.168.0.0/16"),
    ip_network("127.0.0.0/8"),
    ip_network("169.254.0.0/16"),   # link-local
    ip_network("0.0.0.0/8"),
    ip_network("100.64.0.0/10"),    # shared address space (RFC 6598)
    ip_network("192.0.0.0/24"),     # IETF protocol assignments
    ip_network("192.0.2.0/24"),     # TEST-NET-1
    ip_network("198.51.100.0/24"),  # TEST-NET-2
    ip_network("203.0.113.0/24"),   # TEST-NET-3
    ip_network("240.0.0.0/4"),      # reserved
    ip_network("::1/128"),
    ip_network("fc00::/7"),
    ip_network("fe80::/10"),
]

_BLOCKED_HOSTNAMES = frozenset({"localhost", "metadata.google.internal"})


class SiteCreate(BaseModel):
    name: str
    url: HttpUrl

    @field_validator("name")
    @classmethod
    def name_constraints(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Site name must not be empty")
        if len(v) > 100:
            raise ValueError("Site name must not exceed 100 characters")
        return v

    @field_validator("url")
    @classmethod
    def url_no_ssrf(cls, v: HttpUrl) -> HttpUrl:
        host = v.host
        if not host:
            raise ValueError("URL must contain a valid host")

        # Block well-known internal hostnames
        if host.lower() in _BLOCKED_HOSTNAMES:
            raise ValueError("URL must not point to a reserved hostname")

        # If the host looks like an IP address, check private/reserved ranges
        try:
            addr = ip_address(host)
            if any(addr in net for net in _BLOCKED_NETWORKS):
                raise ValueError("URL must not point to a private or reserved IP address")
        except (AddressValueError, ValueError) as exc:
            # Re-raise our own errors; ignore AddressValueError (host is a domain name)
            if "URL must not point" in str(exc):
                raise

        return v


class SiteUpdate(BaseModel):
    name: str | None = None
    url: HttpUrl | None = None


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


class ScanScorePoint(BaseModel):
    date: str
    score: float


class SiteScoreHistory(BaseModel):
    site_id: int
    site_name: str
    scans: list[ScanScorePoint]


class ChartDataOut(BaseModel):
    score_history: list[SiteScoreHistory]
    severity_totals: dict[str, int]


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
@limiter.limit(settings.RATE_LIMIT_DEFAULT)
async def create_site(request: Request, body: SiteCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    plan = settings.PLAN_LIMITS[user.plan]
    count = (await db.execute(select(func.count()).select_from(Site).where(Site.user_id == user.id))).scalar()
    if count >= plan["sites"]:
        raise HTTPException(status_code=403, detail=f"Site limit ({plan['sites']}) reached. Upgrade your plan.")
    site = Site(user_id=user.id, name=body.name, url=str(body.url))
    db.add(site)
    await db.commit()
    await db.refresh(site)
    logger.info("site_created", user_id=user.id, site_id=site.id, site_url=site.url)
    return SiteOut(id=site.id, name=site.name, url=site.url, created_at=site.created_at)


@router.patch("/sites/{site_id}", response_model=SiteOut)
async def update_site(
    site_id: int,
    body: SiteUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    site = await _get_user_site(site_id, user.id, db)
    if body.name is not None:
        site.name = body.name
    if body.url is not None:
        site.url = str(body.url)
    await db.commit()
    await db.refresh(site)
    return SiteOut(id=site.id, name=site.name, url=site.url, created_at=site.created_at)


@router.delete("/sites/{site_id}", status_code=204)
async def delete_site(site_id: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    site = await _get_user_site(site_id, user.id, db)
    logger.info("site_deleted", user_id=user.id, site_id=site.id, site_url=site.url)
    await db.delete(site)
    await db.commit()


# --- Scans ---

@router.post("/sites/{site_id}/scan", response_model=ScanOut, status_code=201)
@limiter.limit(settings.RATE_LIMIT_SCAN_START)
async def start_scan(
    request: Request,
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
    logger.info("scan_queued", user_id=user.id, site_id=site.id, scan_id=scan.id, max_pages=plan["pages_per_scan"])

    _dispatch_scan(scan.id, plan["pages_per_scan"], background_tasks)
    return scan


@router.get("/sites/{site_id}/scans", response_model=list[ScanOut])
async def list_scans(
    site_id: int,
    limit: int = Query(default=20, ge=1, le=50),
    status: str | None = Query(default=None),
    min_score: float | None = Query(default=None, ge=0, le=100),
    max_score: float | None = Query(default=None, ge=0, le=100),
    sort: str = Query(default="created_at", pattern="^(created_at|score|total_issues)$"),
    order: str = Query(default="desc", pattern="^(asc|desc)$"),
    limit: int = Query(default=20, ge=1, le=50),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_user_site(site_id, user.id, db)
    query = select(Scan).where(Scan.site_id == site_id)
    if status:
        query = query.where(Scan.status == status)
    if min_score is not None:
        query = query.where(Scan.score >= min_score)
    if max_score is not None:
        query = query.where(Scan.score <= max_score)
    sort_col = getattr(Scan, sort)
    order_expr = sort_col.desc() if order == "desc" else sort_col.asc()
    result = await db.execute(query.order_by(nullslast(order_expr)).offset(offset).limit(limit))
    return result.scalars().all()


@router.get("/scans/{scan_id}", response_model=ScanOut)
async def get_scan(scan_id: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    scan = await _get_user_scan(scan_id, user.id, db)
    return scan


@router.get("/scans/{scan_id}/issues", response_model=list[IssueOut])
async def get_issues(
    scan_id: int,
    severity: Literal["critical", "serious", "moderate", "minor"] | None = None,
    rule_id: str | None = Query(default=None, max_length=50),
    limit: int = Query(default=100, ge=1, le=500),
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


@router.get("/dashboard/chart-data", response_model=ChartDataOut)
async def dashboard_chart_data(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Score trend (per site, last 20 completed scans) + severity totals for charts."""
    sites_result = await db.execute(select(Site).where(Site.user_id == user.id))
    sites = sites_result.scalars().all()

    score_history: list[SiteScoreHistory] = []
    for site in sites:
        scans_result = await db.execute(
            select(Scan)
            .where(Scan.site_id == site.id, Scan.status == "completed", Scan.score.isnot(None))
            .order_by(Scan.completed_at.asc())
            .limit(20)
        )
        scans = scans_result.scalars().all()
        if scans:
            score_history.append(SiteScoreHistory(
                site_id=site.id,
                site_name=site.name,
                scans=[ScanScorePoint(date=s.completed_at.isoformat(), score=round(s.score, 1)) for s in scans],
            ))

    sev = (await db.execute(
        select(
            func.coalesce(func.sum(Scan.critical_count), 0).label("critical"),
            func.coalesce(func.sum(Scan.serious_count), 0).label("serious"),
            func.coalesce(func.sum(Scan.moderate_count), 0).label("moderate"),
            func.coalesce(func.sum(Scan.minor_count), 0).label("minor"),
        ).select_from(Scan).join(Site).where(Site.user_id == user.id, Scan.status == "completed")
    )).one()

    return ChartDataOut(
        score_history=score_history,
        severity_totals={
            "critical": int(sev.critical),
            "serious": int(sev.serious),
            "moderate": int(sev.moderate),
            "minor": int(sev.minor),
        },
# --- SSE scan progress stream ---

async def _get_user_from_query_token(
    token: str | None = Query(None, alias="token"),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Auth dependency that reads the JWT from ?token= for EventSource connections.

    The browser's EventSource API cannot set custom headers, so we accept the
    token as a query parameter for this endpoint only.
    """
    if token is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id = int(payload["sub"])
    except (JWTError, KeyError, ValueError):
        raise HTTPException(status_code=401, detail="Invalid token")
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")
    return user


@router.get("/scans/{scan_id}/stream")
async def scan_progress_stream(
    scan_id: int,
    user: User = Depends(_get_user_from_query_token),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """Stream live scan progress as Server-Sent Events.

    The client connects once and receives ``data: <json>`` events roughly every
    500 ms until the scan reaches ``completed`` or ``failed`` status.  The
    connection is closed automatically by the server at that point.

    Event payload fields:
    - ``status``: "crawling" | "scanning" | "completed" | "failed"
    - ``pages_done``: number of pages processed so far
    - ``pages_total``: total pages to process (null while crawling)
    - ``current_url``: URL currently being scanned (empty string otherwise)
    """
    # Authorise — raises 404 if scan does not belong to this user.
    await _get_user_scan(scan_id, user.id, db)

    # Maximum polling cycles before the stream self-terminates (~5 minutes).
    MAX_CYCLES = 600

    async def event_stream():
        cycles = 0
        try:
            while cycles < MAX_CYCLES:
                progress = get_progress(scan_id)
                if progress:
                    yield f"data: {json.dumps(progress)}\n\n"
                    if progress["status"] in ("completed", "failed"):
                        break
                else:
                    # Progress entry not yet written or already cleared — check DB.
                    async with async_session() as check_db:
                        result = await check_db.execute(select(Scan).where(Scan.id == scan_id))
                        db_scan = result.scalar_one_or_none()
                    if db_scan and db_scan.status in ("completed", "failed"):
                        yield f"data: {json.dumps({'status': db_scan.status, 'pages_done': db_scan.pages_scanned, 'pages_total': db_scan.pages_scanned, 'current_url': ''})}\n\n"
                        break
                cycles += 1
                await asyncio.sleep(0.5)
        except asyncio.CancelledError:
            pass

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
# --- Badge ---

@router.get("/sites/{site_id}/badge.svg", include_in_schema=True)
async def site_badge(site_id: int, db: AsyncSession = Depends(get_db)):
    """Public SVG badge showing a site's latest accessibility score. No auth required."""
    site_result = await db.execute(select(Site).where(Site.id == site_id))
    if not site_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Site not found")

    scan_result = await db.execute(
        select(Scan)
        .where(Scan.site_id == site_id, Scan.status == "completed")
        .order_by(Scan.completed_at.desc())
        .limit(1)
    )
    last_scan = scan_result.scalar_one_or_none()

    if last_scan and last_scan.score is not None:
        score = last_scan.score
        value = f"{score:.0f}/100"
        color = "#059669" if score >= 80 else ("#d97706" if score >= 50 else "#dc2626")
    else:
        value = "pending"
        color = "#6b7280"

    svg = _badge_svg("accessibility", value, color)
    return Response(
        content=svg,
        media_type="image/svg+xml",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )


def _badge_svg(label: str, value: str, color: str) -> str:
    """Render a flat shields.io-style SVG badge."""
    label_w = round(len(label) * 6.5 + 16)
    value_w = round(len(value) * 6.5 + 16)
    total_w = label_w + value_w
    lx = round(label_w / 2)
    vx = round(label_w + value_w / 2)
    sl = _html.escape(label)
    sv = _html.escape(value)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{total_w}" height="20"'
        f' role="img" aria-label="{sl}: {sv}">'
        f'<title>{sl}: {sv}</title>'
        f'<clipPath id="c"><rect width="{total_w}" height="20" rx="3"/></clipPath>'
        f'<g clip-path="url(#c)">'
        f'<rect width="{label_w}" height="20" fill="#555"/>'
        f'<rect x="{label_w}" width="{value_w}" height="20" fill="{color}"/>'
        f'</g>'
        f'<g fill="#fff" font-family="Verdana,Geneva,DejaVu Sans,sans-serif"'
        f' font-size="11" text-anchor="middle">'
        f'<text x="{lx}" y="15" fill="#010101" fill-opacity=".25">{sl}</text>'
        f'<text x="{lx}" y="14">{sl}</text>'
        f'<text x="{vx}" y="15" fill="#010101" fill-opacity=".25">{sv}</text>'
        f'<text x="{vx}" y="14">{sv}</text>'
        f'</g>'
        f'</svg>'
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
