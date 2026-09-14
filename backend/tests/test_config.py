import pytest
from pydantic import ValidationError

from backend.app.core.config import Settings, get_settings


def test_defaults_without_dotenv():
    settings = Settings(_env_file=None)
    assert settings.env == "development"
    assert settings.api_host == "127.0.0.1"
    assert settings.api_port == 8000
    assert settings.log_level == "INFO"
    assert get_settings() is get_settings()


def test_environment_overrides(monkeypatch):
    monkeypatch.setenv("MEDTRUST_ENV", "staging")
    monkeypatch.setenv("MEDTRUST_API_PORT", "9000")
    monkeypatch.setenv("MEDTRUST_API_HOST", "localhost")
    monkeypatch.setenv("MEDTRUST_LOG_LEVEL", "WARNING")
    settings = Settings(_env_file=None)
    assert (settings.env, settings.api_port, settings.api_host, settings.log_level) == (
        "staging",
        9000,
        "localhost",
        "WARNING",
    )


def test_dotenv_and_environment_precedence(tmp_path, monkeypatch):
    dotenv = tmp_path / ".env"
    dotenv.write_text("MEDTRUST_ENV=test\nMEDTRUST_API_PORT=9000\nDATABASE_URL=\n")
    monkeypatch.setenv("MEDTRUST_API_PORT", "9001")
    settings = Settings()
    assert settings.env == "test"
    assert settings.api_port == 9001


@pytest.mark.parametrize(
    "values",
    [
        {"env": "internal-host-name"},
        {"api_port": 0},
        {"api_port": 65536},
        {"log_level": "invalid"},
    ],
)
def test_invalid_configuration(values):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **values)
