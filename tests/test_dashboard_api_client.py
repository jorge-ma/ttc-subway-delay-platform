"""Tests for the Streamlit dashboard API client."""

from unittest.mock import Mock, patch

import httpx
import pytest

from dashboard.api_client import (
    APIClientError,
    get_api_base_url,
    get_causes,
    get_json,
    get_monthly,
    get_stations,
    get_summary,
)


def test_default_api_base_url(monkeypatch):
    monkeypatch.delenv("TTC_API_BASE_URL", raising=False)

    assert get_api_base_url() == "http://127.0.0.1:8000"


def test_configured_api_base_url(monkeypatch):
    monkeypatch.setenv(
        "TTC_API_BASE_URL",
        "http://api.example.test:8000/",
    )

    assert get_api_base_url() == "http://api.example.test:8000"


@patch("dashboard.api_client.httpx.get")
def test_get_json_returns_response_data(get_mock):
    response = Mock()
    response.json.return_value = {"status": "healthy"}
    get_mock.return_value = response

    result = get_json("/health")

    assert result == {"status": "healthy"}
    response.raise_for_status.assert_called_once_with()


@patch("dashboard.api_client.httpx.get")
def test_get_json_converts_http_errors(get_mock):
    get_mock.side_effect = httpx.ConnectError(
        "Connection refused"
    )

    with pytest.raises(APIClientError) as error:
        get_json("/health")

    assert "Unable to retrieve data" in str(error.value)


@patch("dashboard.api_client.get_json")
def test_summary_uses_summary_endpoint(get_json_mock):
    get_json_mock.return_value = {"total_events": 43105}

    result = get_summary()

    assert result == {"total_events": 43105}
    get_json_mock.assert_called_once_with(
        "/api/v1/reliability/summary"
    )


@patch("dashboard.api_client.get_json")
def test_station_filter_is_sent_to_api(get_json_mock):
    get_json_mock.return_value = []

    get_stations(line="BD", limit=5)

    get_json_mock.assert_called_once_with(
        "/api/v1/reliability/stations",
        {
            "limit": 5,
            "line": "BD",
        },
    )


@patch("dashboard.api_client.get_json")
def test_cause_filter_is_sent_to_api(get_json_mock):
    get_json_mock.return_value = []

    get_causes(line="YU", limit=7)

    get_json_mock.assert_called_once_with(
        "/api/v1/reliability/causes",
        {
            "limit": 7,
            "line": "YU",
        },
    )


@patch("dashboard.api_client.get_json")
def test_monthly_request_without_line_filter(get_json_mock):
    get_json_mock.return_value = []

    get_monthly()

    get_json_mock.assert_called_once_with(
        "/api/v1/reliability/monthly",
        None,
    )


@patch("dashboard.api_client.get_json")
def test_monthly_request_with_line_filter(get_json_mock):
    get_json_mock.return_value = []

    get_monthly(line="SHP")

    get_json_mock.assert_called_once_with(
        "/api/v1/reliability/monthly",
        {
            "line": "SHP",
        },
    )
