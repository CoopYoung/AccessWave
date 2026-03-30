"""Orchestrates a full site scan: crawl -> check each page -> save results."""

import asyncio
import datetime

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.metrics import (
    ACTIVE_SCANS,
    ISSUES_FOUND,
    SCANS_COMPLETED,
    SCANS_FAILED,
    SCANS_STARTED,
    SCAN_DURATION_SECONDS,
    SCAN_PAGES_SCANNED,
    SCAN_SCORE,
)
from app.models import Issue, Scan, Site, User, Webhook
from app.services.crawler import crawl_site
from app.services.email_service import send_scan_completed, send_scan_failed
from app.services.scan_progress import clear_progress, update_progress
from app.services.scanner import IssueFound, calculate_score, scan_html
from app.services.webhook_sender import fire_event

logger = structlog.get_logger("accesswave.runner")


async def run_scan(scan_id: int, max_pages: int = 5) -> None:
    """Execute a full scan. Updates the Scan record in place."""
    async with async_session() as db:
        result = await db.execute(select(Scan).where(Scan.id == scan_id))
        scan = result.scalar_one_or_none()
        if not scan:
            return

        site_result = await db.execute(select(Site).where(Site.id == scan.site_id))
        site = site_result.scalar_one_or_none()
        if not site:
            return

        scan.status = "running"
        scan.started_at = datetime.datetime.utcnow()
        await db.commit()

        logger.info("scan_started", scan_id=scan.id, site_id=scan.site_id, site_url=site.url, max_pages=max_pages)
        SCANS_STARTED.inc()
        ACTIVE_SCANS.inc()

        try:
            update_progress(scan.id, pages_done=0, pages_total=None, status="crawling")
            pages = await crawl_site(site.url, max_pages=max_pages)
            html_pages = [p for p in pages if p.get("html")]
            pages_total = len(html_pages)

            all_issues: list[IssueFound] = []
            pages_done = 0

            for page in pages:
                if not page.get("html"):
                    continue
                update_progress(
                    scan.id,
                    pages_done=pages_done,
                    pages_total=pages_total,
                    status="scanning",
                    current_url=page["url"],
                )
                page_issues = scan_html(page["html"], page["url"])
                all_issues.extend(page_issues)
                pages_done += 1

                for issue in page_issues:
                    db.add(Issue(
                        scan_id=scan.id,
                        page_url=page["url"],
                        rule_id=issue.rule_id,
                        severity=issue.severity,
                        wcag_criteria=issue.wcag_criteria,
                        message=issue.message,
                        element_html=issue.element_html,
                        selector=issue.selector,
                        how_to_fix=issue.how_to_fix,
                    ))

            scan.pages_scanned = pages_total
            scan.total_issues = len(all_issues)
            scan.critical_count = sum(1 for i in all_issues if i.severity == "critical")
            scan.serious_count = sum(1 for i in all_issues if i.severity == "serious")
            scan.moderate_count = sum(1 for i in all_issues if i.severity == "moderate")
            scan.minor_count = sum(1 for i in all_issues if i.severity == "minor")
            scan.score = calculate_score(all_issues)
            scan.status = "completed"
            scan.completed_at = datetime.datetime.utcnow()

            logger.info(
                "scan_complete",
                scan_id=scan.id,
                site_id=scan.site_id,
                pages_scanned=scan.pages_scanned,
                total_issues=scan.total_issues,
                critical=scan.critical_count,
                serious=scan.serious_count,
                moderate=scan.moderate_count,
                minor=scan.minor_count,
                score=scan.score,
            )
            # Record per-severity issue counts
            for severity in ("critical", "serious", "moderate", "minor"):
                count = sum(1 for i in all_issues if i.severity == severity)
                if count:
                    ISSUES_FOUND.labels(severity=severity).inc(count)

            # Record result distributions
            SCAN_SCORE.observe(scan.score)
            SCAN_PAGES_SCANNED.observe(scan.pages_scanned)
            if scan.started_at and scan.completed_at:
                duration = (scan.completed_at - scan.started_at).total_seconds()
                SCAN_DURATION_SECONDS.observe(duration)

            SCANS_COMPLETED.inc()
            update_progress(scan.id, pages_done=pages_total, pages_total=pages_total, status="completed")
            logger.info(f"Scan {scan.id} complete: {scan.pages_scanned} pages, {scan.total_issues} issues, score {scan.score}")

            # Fire scan.completed webhooks for the site owner
            wh_result = await db.execute(
                select(Webhook).where(Webhook.user_id == site.user_id, Webhook.is_active == True)
            )
            webhooks = wh_result.scalars().all()
            await fire_event(webhooks, "scan.completed", {
                "scan_id": scan.id,
                "site_id": site.id,
                "site_name": site.name,
                "site_url": site.url,
                "score": scan.score,
                "pages_scanned": scan.pages_scanned,
                "total_issues": scan.total_issues,
                "critical_count": scan.critical_count,
                "serious_count": scan.serious_count,
                "moderate_count": scan.moderate_count,
                "minor_count": scan.minor_count,
            })

            # Send email notification if the owner has opted in
            try:
                owner_result = await db.execute(select(User).where(User.id == site.user_id))
                owner = owner_result.scalar_one_or_none()
                if owner and owner.email_notify_on_complete:
                    await send_scan_completed(
                        to_address=owner.email,
                        site_name=site.name,
                        site_url=site.url,
                        scan_id=scan.id,
                        score=scan.score,
                        pages_scanned=scan.pages_scanned,
                        total_issues=scan.total_issues,
                        critical_count=scan.critical_count,
                        serious_count=scan.serious_count,
                        score_threshold=owner.email_score_threshold,
                    )
            except Exception:
                pass  # Never let email errors mask the scan result

        except Exception as e:
            logger.error("scan_failed", scan_id=scan.id, site_id=scan.site_id, error=str(e), exc_info=True)
            scan.status = "failed"
            scan.completed_at = datetime.datetime.utcnow()
            SCANS_FAILED.inc()
            update_progress(scan.id, pages_done=0, pages_total=0, status="failed")

            # Fire scan.failed webhooks
            try:
                wh_result = await db.execute(
                    select(Webhook).where(Webhook.user_id == site.user_id, Webhook.is_active == True)
                )
                webhooks = wh_result.scalars().all()
                await fire_event(webhooks, "scan.failed", {
                    "scan_id": scan.id,
                    "site_id": site.id,
                    "site_name": site.name,
                    "site_url": site.url,
                    "error": str(e),
                })
            except Exception:
                pass  # Never let webhook errors mask the original failure

            # Send failure email notification if the owner has opted in
            try:
                owner_result = await db.execute(select(User).where(User.id == site.user_id))
                owner = owner_result.scalar_one_or_none()
                if owner and owner.email_notify_on_failure:
                    await send_scan_failed(
                        to_address=owner.email,
                        site_name=site.name,
                        site_url=site.url,
                        scan_id=scan.id,
                        error=str(e),
                    )
            except Exception:
                pass  # Never let email errors mask the original failure

        finally:
            ACTIVE_SCANS.dec()

        await db.commit()
        # Keep the final progress entry briefly so SSE clients can receive it,
        # then remove it to prevent stale accumulation.
        await asyncio.sleep(10)
        clear_progress(scan.id)
