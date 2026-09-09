"""Tests for database connection configuration."""

import pytest

from database.connection import get_database_url


def make_settings(**overrides: str) -> dict[str, str]:
    settings = {
        "POSTGRES_HOST": "127.0.0.1",
        "POSTGRES_PORT": "5432",
        "POSTGRES_DB": "ttc_reliability_v2_test",
        "POSTGRES_USER": "ttc_v2_app",
        "POSTGRES_PASSWORD": "test-only-password",
    }
    settings.update(overrides)

    return settings


def test_database_url_uses_supplied_settings():
    database_url = get_database_url(make_settings())

    assert database_url.drivername == "postgresql+psycopg"
    assert database_url.host == "127.0.0.1"
    assert database_url.port == 5432
    assert database_url.database == "ttc_reliability_v2_test"
    assert database_url.username == "ttc_v2_app"


def test_database_url_preserves_special_password_characters():
    database_url = get_database_url(
        make_settings(POSTGRES_PASSWORD="p@ss:/word")
    )

    assert database_url.password == "p@ss:/word"


def test_missing_database_setting_is_rejected():
    settings = make_settings()
    settings.pop("POSTGRES_PASSWORD")

    with pytest.raises(
        RuntimeError,
        match="Missing required database settings: POSTGRES_PASSWORD",
    ):
        get_database_url(settings)


@pytest.mark.parametrize("port", ["invalid", "0", "65536"])
def test_invalid_database_port_is_rejected(port):
    with pytest.raises(RuntimeError, match="POSTGRES_PORT"):
        get_database_url(make_settings(POSTGRES_PORT=port))
