import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from backend.app.core.exceptions import MedTrustError


@pytest.mark.parametrize(
    ("exception", "code"),
    [
        (MedTrustError("private-test-marker"), "medtrust_error"),
        (RuntimeError("private-test-marker"), "internal_server_error"),
        (HTTPException(500, detail="private-test-marker"), "http_error"),
    ],
)
def test_errors_are_safe(app, exception, code):
    @app.get("/failure")
    async def failure():
        raise exception

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/failure")
    assert response.status_code == 500
    assert response.json()["error"]["code"] == code
    assert "private-test-marker" not in response.text
    assert "Traceback" not in response.text


def test_validation_does_not_echo_input(app):
    @app.get("/validate")
    async def validate(value: int):
        return value

    with TestClient(app) as client:
        response = client.get("/validate", params={"value": "private-test-marker"})
    assert response.status_code == 422
    assert response.json() == {
        "error": {"code": "validation_error", "message": "Request validation failed."}
    }


def test_not_found(client):
    assert client.get("/missing").json() == {
        "error": {"code": "http_error", "message": "Not Found"}
    }
