"""
conftest.py — shared pytest fixtures and test configuration.
"""
from __future__ import annotations
import pytest
from unittest.mock import AsyncMock, MagicMock


@pytest.fixture(autouse=True)
def mock_settings(monkeypatch):
    """
    Patch critical settings so tests never need real credentials or a DB.
    """
    from app.config import settings
    from cryptography.fernet import Fernet

    monkeypatch.setattr(settings, "DATABASE_URL",
                        "postgresql+asyncpg://postgres:postgres@localhost:5432/agentic_test")
    monkeypatch.setattr(settings, "REDIS_URL", "redis://localhost:6379/1")
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "sk-test-key")
    monkeypatch.setattr(settings, "SECRET_KEY", "test-secret-key-for-pytest-only")
    monkeypatch.setattr(settings, "FERNET_KEY", Fernet.generate_key().decode())
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_ID", "test-google-client")
    monkeypatch.setattr(settings, "MICROSOFT_CLIENT_ID", "test-ms-client")
    monkeypatch.setattr(settings, "SLACK_CLIENT_ID", "test-slack-client")
