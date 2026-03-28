"""Orchestrates a full site scan: crawl -> check each page -> save results."""

import datetime
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.models import Issue, Scan, Site
from app.services.crawler import crawl_site
from app.services.scanner import IssueFound, calculate_score, scan_html

logger = logging.getLogger("accesswave.runner")


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

        try:
            pages = await crawl_site(site.url, max_pages=max_pages)
            all_issues: list[IssueFound] = []

            for page in pages:
                if not page.get("html"):
                    continue
                page_issues = scan_html(page["html"], page["url"])
                all_issues.extend(page_issues)

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

            scan.pages_scanned = len([p for p in pages if p.get("html")])
            scan.total_issues = len(all_issues)
            scan.critical_count = sum(1 for i in all_issues if i.severity == "critical")
            scan.serious_count = sum(1 for i in all_issues if i.severity == "serious")
            scan.moderate_count = sum(1 for i in all_issues if i.severity == "moderate")
            scan.minor_count = sum(1 for i in all_issues if i.severity == "minor")
            scan.score = calculate_score(all_issues)
            scan.status = "completed"
            scan.completed_at = datetime.datetime.utcnow()

            logger.info(f"Scan {scan.id} complete: {scan.pages_scanned} pages, {scan.total_issues} issues, score {scan.score}")

        except Exception as e:
            logger.error(f"Scan {scan.id} failed: {e}")
            scan.status = "failed"
            scan.completed_at = datetime.datetime.utcnow()

        await db.commit()
