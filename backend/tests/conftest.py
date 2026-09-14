"""Isolated tests: no local dotenv file or external service is needed."""

import pytest
from fastapi.testclient import TestClient

from backend.app.core.config import Settings, get_settings


@pytest.fixture(autouse=True)
def isolated_settings(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    for name in ("ENV", "API_HOST", "API_PORT", "LOG_LEVEL"):
        monkeypatch.delenv(f"MEDTRUST_{name}", raising=False)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def app():
    from backend.app.main import create_app

    return create_app(Settings(_env_file=None, env="test"))


@pytest.fixture
def client(app):
    with TestClient(app) as client:
        yield client
