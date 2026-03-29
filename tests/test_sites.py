"""Tests for site management endpoints."""
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_create_site(client: AsyncClient, auth_headers):
    resp = await client.post(
        "/api/sites",
        json={"name": "My Site", "url": "https://example.com"},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "My Site"
    assert "example.com" in body["url"]
    assert "id" in body


@pytest.mark.asyncio
async def test_create_site_unauthenticated(client: AsyncClient):
    resp = await client.post(
        "/api/sites",
        json={"name": "Test", "url": "https://example.com"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_list_sites(client: AsyncClient, pro_auth_headers):
    """Pro plan supports multiple sites."""
    await client.post(
        "/api/sites",
        json={"name": "Site A", "url": "https://a.example.com"},
        headers=pro_auth_headers,
    )
    await client.post(
        "/api/sites",
        json={"name": "Site B", "url": "https://b.example.com"},
        headers=pro_auth_headers,
    )
    resp = await client.get("/api/sites", headers=pro_auth_headers)
    assert resp.status_code == 200
    sites = resp.json()
    assert len(sites) == 2
    names = {s["name"] for s in sites}
    assert names == {"Site A", "Site B"}


@pytest.mark.asyncio
async def test_list_sites_empty(client: AsyncClient, auth_headers):
    resp = await client.get("/api/sites", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_update_site(client: AsyncClient, auth_headers):
    create = await client.post(
        "/api/sites",
        json={"name": "Original", "url": "https://orig.example.com"},
        headers=auth_headers,
    )
    site_id = create.json()["id"]
    resp = await client.patch(
        f"/api/sites/{site_id}",
        json={"name": "Updated"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "Updated"


@pytest.mark.asyncio
async def test_delete_site(client: AsyncClient, auth_headers):
    create = await client.post(
        "/api/sites",
        json={"name": "To Delete", "url": "https://del.example.com"},
        headers=auth_headers,
    )
    site_id = create.json()["id"]
    resp = await client.delete(f"/api/sites/{site_id}", headers=auth_headers)
    assert resp.status_code == 204

    # Confirm gone from list
    list_resp = await client.get("/api/sites", headers=auth_headers)
    ids = [s["id"] for s in list_resp.json()]
    assert site_id not in ids


@pytest.mark.asyncio
async def test_delete_site_other_user(client: AsyncClient, auth_headers):
    """User cannot delete another user's site."""
    create = await client.post(
        "/api/sites",
        json={"name": "Protected", "url": "https://protected.example.com"},
        headers=auth_headers,
    )
    site_id = create.json()["id"]

    # Register a second user
    r2 = await client.post(
        "/api/auth/register",
        json={"email": "other@example.com", "password": "password123"},
    )
    other_token = r2.json()["access_token"]
    other_headers = {"Authorization": f"Bearer {other_token}"}

    resp = await client.delete(f"/api/sites/{site_id}", headers=other_headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_create_site_ssrf_blocked(client: AsyncClient, auth_headers):
    """Private/loopback URLs must be rejected (SSRF protection)."""
    resp = await client.post(
        "/api/sites",
        json={"name": "SSRF", "url": "http://192.168.1.1"},
        headers=auth_headers,
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_site_localhost_blocked(client: AsyncClient, auth_headers):
    resp = await client.post(
        "/api/sites",
        json={"name": "Local", "url": "http://localhost/admin"},
        headers=auth_headers,
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_free_plan_site_limit(client: AsyncClient, auth_headers):
    """Free plan allows only 1 site."""
    await client.post(
        "/api/sites",
        json={"name": "First", "url": "https://first.example.com"},
        headers=auth_headers,
    )
    resp = await client.post(
        "/api/sites",
        json={"name": "Second", "url": "https://second.example.com"},
        headers=auth_headers,
    )
    assert resp.status_code == 403
    assert "limit" in resp.json()["detail"].lower()
