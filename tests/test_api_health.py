"""Tests for API metadata, health, and readiness endpoints."""

from unittest.mock import Mock, patch

from fastapi.testclient import TestClient

from api.main import app


client = TestClient(app)


def test_health_endpoint():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


def test_openapi_metadata_and_platform_paths():
    response = client.get("/openapi.json")
    document = response.json()

    assert response.status_code == 200
    assert document["info"]["title"] == "TTC Reliability Monitor API"
    assert document["info"]["version"] == "0.1.0"
    assert "/health" in document["paths"]
    assert "/ready" in document["paths"]


@patch("api.main.verify_database_connection")
@patch("api.main.create_database_engine")
def test_readiness_endpoint_when_database_is_available(
    create_engine_mock,
    verify_connection_mock,
):
    engine = Mock()
    create_engine_mock.return_value = engine
    verify_connection_mock.return_value = (
        "ttc_reliability_v2",
        "ttc_v2_app",
    )

    response = client.get("/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready"}
    engine.dispose.assert_called_once_with()


@patch("api.main.create_database_engine")
def test_readiness_endpoint_when_database_is_unavailable(
    create_engine_mock,
):
    create_engine_mock.side_effect = RuntimeError(
        "database unavailable"
    )

    response = client.get("/ready")

    assert response.status_code == 503
    assert response.json() == {
        "detail": {
            "status": "not_ready",
            "database": "unavailable",
        }
    }
