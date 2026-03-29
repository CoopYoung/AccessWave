"""Tests for authentication endpoints."""
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_register_success(client: AsyncClient):
    resp = await client.post(
        "/api/auth/register",
        json={"email": "user@example.com", "password": "securepass"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert "access_token" in body
    assert body["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_register_duplicate_email(client: AsyncClient):
    payload = {"email": "dup@example.com", "password": "securepass"}
    await client.post("/api/auth/register", json=payload)
    resp = await client.post("/api/auth/register", json=payload)
    assert resp.status_code == 400
    assert "already registered" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_register_short_password(client: AsyncClient):
    resp = await client.post(
        "/api/auth/register",
        json={"email": "short@example.com", "password": "1234567"},
    )
    assert resp.status_code in (400, 422)


@pytest.mark.asyncio
async def test_register_invalid_email(client: AsyncClient):
    resp = await client.post(
        "/api/auth/register",
        json={"email": "not-an-email", "password": "securepass"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_login_success(client: AsyncClient):
    await client.post(
        "/api/auth/register",
        json={"email": "login@example.com", "password": "securepass"},
    )
    resp = await client.post(
        "/api/auth/login",
        data={"username": "login@example.com", "password": "securepass"},
    )
    assert resp.status_code == 200
    assert "access_token" in resp.json()


@pytest.mark.asyncio
async def test_login_wrong_password(client: AsyncClient):
    await client.post(
        "/api/auth/register",
        json={"email": "wp@example.com", "password": "securepass"},
    )
    resp = await client.post(
        "/api/auth/login",
        data={"username": "wp@example.com", "password": "wrongpass"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_login_unknown_user(client: AsyncClient):
    resp = await client.post(
        "/api/auth/login",
        data={"username": "ghost@example.com", "password": "anypass"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_get_me(client: AsyncClient, registered_user, auth_headers):
    resp = await client.get("/api/auth/me", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["email"] == registered_user["email"]
    assert body["plan"] == "free"
    assert "id" in body


@pytest.mark.asyncio
async def test_get_me_unauthenticated(client: AsyncClient):
    resp = await client.get("/api/auth/me")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_update_profile(client: AsyncClient, auth_headers):
    resp = await client.put(
        "/api/auth/profile",
        json={"email": "updated@example.com"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["email"] == "updated@example.com"


@pytest.mark.asyncio
async def test_change_password(client: AsyncClient, registered_user, auth_headers):
    resp = await client.put(
        "/api/auth/password",
        json={
            "current_password": registered_user["password"],
            "new_password": "newpassword123",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_change_password_wrong_current(client: AsyncClient, auth_headers):
    resp = await client.put(
        "/api/auth/password",
        json={"current_password": "wrongcurrent", "new_password": "newpassword123"},
        headers=auth_headers,
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_delete_account(client: AsyncClient, registered_user, auth_headers):
    import json as _json
    resp = await client.request(
        "DELETE",
        "/api/auth/account",
        content=_json.dumps({"password": registered_user["password"]}),
        headers={**auth_headers, "Content-Type": "application/json"},
    )
    assert resp.status_code == 204

    # Confirm the user is gone
    resp2 = await client.get("/api/auth/me", headers=auth_headers)
    assert resp2.status_code == 401
