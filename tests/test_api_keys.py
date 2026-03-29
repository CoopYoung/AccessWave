"""Tests for API key management endpoints."""
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_create_api_key(client: AsyncClient, auth_headers):
    resp = await client.post(
        "/api/keys",
        json={"name": "My Key"},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "My Key"
    assert "key" in body
    assert body["key"].startswith("aw_")
    assert "key_prefix" in body


@pytest.mark.asyncio
async def test_list_api_keys(client: AsyncClient, auth_headers):
    await client.post("/api/keys", json={"name": "Key 1"}, headers=auth_headers)
    await client.post("/api/keys", json={"name": "Key 2"}, headers=auth_headers)
    resp = await client.get("/api/keys", headers=auth_headers)
    assert resp.status_code == 200
    keys = resp.json()
    assert len(keys) == 2
    # raw_key must NOT appear in the list response
    for key in keys:
        assert "raw_key" not in key


@pytest.mark.asyncio
async def test_revoke_api_key(client: AsyncClient, auth_headers):
    create = await client.post(
        "/api/keys", json={"name": "Revoke Me"}, headers=auth_headers
    )
    key_id = create.json()["id"]
    resp = await client.delete(f"/api/keys/{key_id}", headers=auth_headers)
    assert resp.status_code == 204

    # Key should be gone from the list
    list_resp = await client.get("/api/keys", headers=auth_headers)
    ids = [k["id"] for k in list_resp.json()]
    assert key_id not in ids


@pytest.mark.asyncio
async def test_authenticate_with_api_key(client: AsyncClient, auth_headers):
    """API keys must work as Bearer tokens for authenticated routes."""
    create = await client.post(
        "/api/keys", json={"name": "Auth Test"}, headers=auth_headers
    )
    raw_key = create.json()["key"]
    api_key_headers = {"Authorization": f"Bearer {raw_key}"}

    resp = await client.get("/api/auth/me", headers=api_key_headers)
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_create_api_key_unauthenticated(client: AsyncClient):
    resp = await client.post("/api/keys", json={"name": "No Auth"})
    assert resp.status_code == 401
