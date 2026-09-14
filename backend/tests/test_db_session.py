"""Configuration and session lifecycle tests without PostgreSQL."""

import pytest
from sqlalchemy import create_engine, text

from backend.app.core.config import Settings, get_settings
from backend.app.db import session as db


def test_database_url_is_optional_and_redacted(monkeypatch):
    assert Settings(_env_file=None).database_url.get_secret_value() == ""
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://test:private-marker@localhost/test")
    settings = Settings(_env_file=None)
    assert "private-marker" in settings.database_url.get_secret_value()
    assert "private-marker" not in repr(settings)
    assert "private-marker" not in settings.model_dump_json()


def test_missing_database_url_fails_only_on_use():
    db.get_engine.cache_clear()
    with pytest.raises(RuntimeError, match="DATABASE_URL must be configured"):
        db.get_engine()


def test_dependency_rolls_back_and_explicit_commit_persists(monkeypatch):
    engine = create_engine("sqlite://")
    monkeypatch.setattr(db, "get_engine", lambda: engine)
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE fixture (value INTEGER)"))
    generator = db.get_db()
    session = next(generator)
    session.execute(text("INSERT INTO fixture VALUES (1)"))
    generator.close()
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM fixture")) == 0
    generator = db.get_db()
    session = next(generator)
    session.execute(text("INSERT INTO fixture VALUES (2)"))
    session.commit()
    generator.close()
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT value FROM fixture")) == 2
    engine.dispose()


def test_engine_creation_is_lazy(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://test@127.0.0.1:1/test")
    get_settings.cache_clear()
    db.get_engine.cache_clear()
    engine = db.get_engine()
    try:
        assert db.get_engine() is engine
        assert engine.echo is False and engine.hide_parameters is True
    finally:
        engine.dispose()
        db.get_engine.cache_clear()
