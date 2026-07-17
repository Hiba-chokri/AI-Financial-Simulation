"""Shared pytest fixtures."""
import pytest
from starlette.testclient import TestClient

TEST_API_KEY = "test-key-123"


@pytest.fixture()
def api_key() -> str:
    return TEST_API_KEY


@pytest.fixture()
def client(api_key: str) -> TestClient:
    """
    A TestClient with auth forced ON and a single known key.

    We set the config attributes at runtime (the security dependency reads them
    live), so the tests are deterministic regardless of any local .env.
    """
    import main
    from app.core import config

    config.API_KEYS = {api_key}
    config.AUTH_ENABLED = True
    return TestClient(main.app)


@pytest.fixture()
def auth_headers(api_key: str) -> dict:
    return {"X-API-Key": api_key}
