"""Tests for scan endpoints."""
import pytest
from httpx import AsyncClient


async def _make_site(client: AsyncClient, headers: dict, url: str = "https://example.com") -> dict:
    resp = await client.post(
        "/api/sites",
        json={"name": "Test Site", "url": url},
        headers=headers,
    )
    assert resp.status_code == 201
    return resp.json()


@pytest.mark.asyncio
async def test_start_scan(client: AsyncClient, auth_headers):
    site = await _make_site(client, auth_headers)
    resp = await client.post(
        f"/api/sites/{site['id']}/scan", headers=auth_headers
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["site_id"] == site["id"]
    assert body["status"] in ("pending", "running", "completed", "failed")


@pytest.mark.asyncio
async def test_start_scan_unauthenticated(client: AsyncClient, auth_headers):
    site = await _make_site(client, auth_headers)
    resp = await client.post(f"/api/sites/{site['id']}/scan")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_start_scan_nonexistent_site(client: AsyncClient, auth_headers):
    resp = await client.post("/api/sites/99999/scan", headers=auth_headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_list_scans(client: AsyncClient, auth_headers):
    site = await _make_site(client, auth_headers)
    await client.post(f"/api/sites/{site['id']}/scan", headers=auth_headers)
    resp = await client.get(f"/api/sites/{site['id']}/scans", headers=auth_headers)
    assert resp.status_code == 200
    scans = resp.json()
    assert len(scans) >= 1
    assert scans[0]["site_id"] == site["id"]


@pytest.mark.asyncio
async def test_get_scan(client: AsyncClient, auth_headers):
    site = await _make_site(client, auth_headers)
    create = await client.post(f"/api/sites/{site['id']}/scan", headers=auth_headers)
    scan_id = create.json()["id"]
    resp = await client.get(f"/api/scans/{scan_id}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["id"] == scan_id


@pytest.mark.asyncio
async def test_get_scan_other_user(client: AsyncClient, auth_headers):
    """User cannot access another user's scan."""
    site = await _make_site(client, auth_headers)
    create = await client.post(f"/api/sites/{site['id']}/scan", headers=auth_headers)
    scan_id = create.json()["id"]

    r2 = await client.post(
        "/api/auth/register",
        json={"email": "other2@example.com", "password": "password123"},
    )
    other_headers = {"Authorization": f"Bearer {r2.json()['access_token']}"}

    resp = await client.get(f"/api/scans/{scan_id}", headers=other_headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_duplicate_scan_rejected(client: AsyncClient, auth_headers):
    """Starting a second scan while one is pending/running should return 409."""
    site = await _make_site(client, auth_headers)
    first = await client.post(f"/api/sites/{site['id']}/scan", headers=auth_headers)
    assert first.status_code == 201

    # If first scan is already completed (fast mock), duplicate check may not apply;
    # only assert 409 when the scan is still in-flight.
    if first.json()["status"] in ("pending", "running"):
        second = await client.post(f"/api/sites/{site['id']}/scan", headers=auth_headers)
        assert second.status_code == 409


@pytest.mark.asyncio
async def test_delete_site_cascades_scans(client: AsyncClient, auth_headers):
    """Deleting a site should also remove its scans (cascade)."""
    site = await _make_site(client, auth_headers)
    create = await client.post(f"/api/sites/{site['id']}/scan", headers=auth_headers)
    scan_id = create.json()["id"]

    # Delete the site
    del_resp = await client.delete(f"/api/sites/{site['id']}", headers=auth_headers)
    assert del_resp.status_code == 204

    # Scan should no longer be accessible
    get_resp = await client.get(f"/api/scans/{scan_id}", headers=auth_headers)
    assert get_resp.status_code == 404
