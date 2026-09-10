"""Client functions for communicating with the TTC API."""

import os
from typing import Any

import httpx


DEFAULT_API_URL = "http://127.0.0.1:8000"


class APIClientError(RuntimeError):
    """Raised when the TTC API cannot return a valid response."""


def get_api_base_url() -> str:
    """Return the configured API base URL."""

    return os.getenv("TTC_API_BASE_URL", DEFAULT_API_URL).rstrip("/")


def get_json(
    path: str,
    parameters: dict[str, Any] | None = None,
) -> Any:
    """Request JSON data from a TTC API endpoint."""

    url = f"{get_api_base_url()}{path}"

    try:
        response = httpx.get(
            url,
            params=parameters,
            timeout=15.0,
        )
        response.raise_for_status()
        return response.json()

    except httpx.HTTPError as error:
        raise APIClientError(
            f"Unable to retrieve data from {url}: {error}"
        ) from error


def get_summary() -> dict[str, Any]:
    """Return system-wide reliability statistics."""

    return get_json("/api/v1/reliability/summary")


def get_lines(limit: int = 100) -> list[dict[str, Any]]:
    """Return TTC line reliability statistics."""

    return get_json(
        "/api/v1/reliability/lines",
        {"limit": limit},
    )


def get_stations(
    line: str | None = None,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Return station reliability statistics."""

    parameters: dict[str, Any] = {"limit": limit}

    if line:
        parameters["line"] = line

    return get_json(
        "/api/v1/reliability/stations",
        parameters,
    )


def get_causes(
    line: str | None = None,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Return incident-cause statistics."""

    parameters: dict[str, Any] = {"limit": limit}

    if line:
        parameters["line"] = line

    return get_json(
        "/api/v1/reliability/causes",
        parameters,
    )


def get_monthly(
    line: str | None = None,
) -> list[dict[str, Any]]:
    """Return monthly reliability statistics."""

    parameters = {"line": line} if line else None

    return get_json(
        "/api/v1/reliability/monthly",
        parameters,
    )
