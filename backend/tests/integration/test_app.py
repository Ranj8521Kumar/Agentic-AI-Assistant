"""
Integration test — health endpoint and app startup.
Uses httpx AsyncClient with the FastAPI test app.
No real DB or credentials required.
"""

import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import patch, AsyncMock


@pytest.fixture
def app():
    """Return the FastAPI app with tools bootstrapped."""
    from app.main import app
    return app


@pytest.mark.asyncio
async def test_health_check(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "version" in data


@pytest.mark.asyncio
async def test_chat_send_unauthenticated(app):
    """Unauthenticated requests to /chat/send must return 403 or 401."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/chat/send",
            json={"message": "hello"},
        )
    assert response.status_code in (401, 403)


@pytest.mark.asyncio
async def test_openapi_schema_available(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    assert "paths" in schema
