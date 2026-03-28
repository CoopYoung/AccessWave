"""Lightweight async crawler — fetches pages from a site for scanning."""

import asyncio
import logging
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from app.config import settings

logger = logging.getLogger("accesswave.crawler")


async def crawl_site(base_url: str, max_pages: int = 5) -> list[dict]:
    """Crawl a site starting from base_url. Returns list of {url, html, status_code}."""
    parsed = urlparse(base_url)
    domain = parsed.netloc
    visited: set[str] = set()
    results: list[dict] = []
    queue: list[tuple[str, int]] = [(base_url, 0)]  # (url, depth)

    async with httpx.AsyncClient(
        timeout=settings.SCAN_TIMEOUT,
        follow_redirects=True,
        verify=False,
        headers={"User-Agent": "AccessWave/1.0 (Accessibility Scanner)"},
    ) as client:
        while queue and len(results) < max_pages:
            url, depth = queue.pop(0)
            normalized = _normalize_url(url)

            if normalized in visited:
                continue
            visited.add(normalized)

            try:
                resp = await client.get(url)
                content_type = resp.headers.get("content-type", "")
                if "text/html" not in content_type:
                    continue

                html = resp.text
                results.append({"url": url, "html": html, "status_code": resp.status_code})
                logger.info(f"Crawled {url} ({resp.status_code})")

                # Extract links for further crawling
                if depth < settings.MAX_CRAWL_DEPTH:
                    soup = BeautifulSoup(html, "lxml")
                    for a in soup.find_all("a", href=True):
                        href = a["href"]
                        full_url = urljoin(url, href)
                        full_parsed = urlparse(full_url)

                        # Same domain, not fragment, not file
                        if (full_parsed.netloc == domain
                                and not full_parsed.fragment
                                and full_parsed.scheme in ("http", "https")
                                and not any(full_url.lower().endswith(ext) for ext in (".pdf", ".jpg", ".png", ".gif", ".zip", ".css", ".js"))):
                            norm = _normalize_url(full_url)
                            if norm not in visited:
                                queue.append((full_url, depth + 1))

            except httpx.TimeoutException:
                logger.warning(f"Timeout: {url}")
                results.append({"url": url, "html": "", "status_code": 0, "error": "timeout"})
            except Exception as e:
                logger.warning(f"Error crawling {url}: {e}")
                results.append({"url": url, "html": "", "status_code": 0, "error": str(e)[:200]})

    return results


def _normalize_url(url: str) -> str:
    """Normalize URL for deduplication."""
    parsed = urlparse(url)
    path = parsed.path.rstrip("/") or "/"
    return f"{parsed.scheme}://{parsed.netloc}{path}"
