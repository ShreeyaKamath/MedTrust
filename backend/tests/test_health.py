from importlib import import_module

from fastapi import FastAPI

from backend.app import __version__


def test_application_imports():
    assert isinstance(import_module("backend.app.main").app, FastAPI)


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "medtrust-api",
        "environment": "test",
        "version": __version__,
    }
    assert response.json()["version"]


def test_default_startup():
    from fastapi.testclient import TestClient

    from backend.app.main import create_app

    with TestClient(create_app()) as client:
        assert client.get("/health").json()["environment"] == "development"
