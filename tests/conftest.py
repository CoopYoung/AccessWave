"""Shared pytest fixtures for AccessWave tests.

Uses an in-memory SQLite database so tests are fully isolated and fast.
"""
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base, get_db
from app.limiter import limiter
from app.main import app

# ---------------------------------------------------------------------------
# In-memory test database
# ---------------------------------------------------------------------------
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

_test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)
_test_session_factory = async_sessionmaker(
    _test_engine, class_=AsyncSession, expire_on_commit=False
)


async def _override_get_db():
    async with _test_session_factory() as session:
        yield session


@pytest.fixture(scope="session", autouse=True)
async def create_tables():
    """Create all tables once for the test session."""
    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture(autouse=True)
async def clean_tables():
    """Truncate all tables and reset rate-limit counters between tests."""
    yield
    # Clear rate-limit in-memory state so tests don't bleed into each other
    limiter._storage.reset()
    async with _test_session_factory() as session:
        for table in reversed(Base.metadata.sorted_tables):
            await session.execute(table.delete())
        await session.commit()


@pytest.fixture
async def client():
    """AsyncClient wired to the FastAPI app with the test DB override."""
    app.dependency_overrides[get_db] = _override_get_db
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Convenience fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
async def registered_user(client: AsyncClient):
    """Register a user and return (email, password, access_token)."""
    email = "test@example.com"
    password = "password123"
    resp = await client.post(
        "/api/auth/register", json={"email": email, "password": password}
    )
    assert resp.status_code == 201
    token = resp.json()["access_token"]
    return {"email": email, "password": password, "token": token}


@pytest.fixture
def auth_headers(registered_user):
    return {"Authorization": f"Bearer {registered_user['token']}"}


@pytest.fixture
async def pro_user(client: AsyncClient):
    """Register a pro-plan user by directly upgrading their plan in the DB."""
    from sqlalchemy import select, update
    from app.models import User

    email = "pro@example.com"
    password = "password123"
    resp = await client.post(
        "/api/auth/register", json={"email": email, "password": password}
    )
    assert resp.status_code == 201
    token = resp.json()["access_token"]

    # Upgrade plan directly in the test DB
    async with _test_session_factory() as session:
        await session.execute(
            update(User).where(User.email == email).values(plan="pro")
        )
        await session.commit()

    return {"email": email, "password": password, "token": token}


@pytest.fixture
def pro_auth_headers(pro_user):
    return {"Authorization": f"Bearer {pro_user['token']}"}
