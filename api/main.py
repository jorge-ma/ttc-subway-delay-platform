"""FastAPI application and TTC reliability endpoints."""

from typing import Annotated, Literal

from fastapi import FastAPI, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.exc import SQLAlchemyError

from api.reliability import (
    CauseReliability,
    LineReliability,
    MonthlyReliability,
    ReliabilitySummary,
    StationReliability,
    fetch_cause_reliability,
    fetch_line_reliability,
    fetch_monthly_reliability,
    fetch_reliability_summary,
    fetch_station_reliability,
)
from database.connection import (
    create_database_engine,
    verify_database_connection,
)


app = FastAPI(
    title="TTC Reliability Monitor API",
    description="Read-only API for TTC subway-delay reliability metrics.",
    version="0.1.0",
)


class HealthResponse(BaseModel):
    """Response returned by the process health probe."""

    status: Literal["healthy"]


class ReadinessResponse(BaseModel):
    """Response returned when application dependencies are available."""

    status: Literal["ready"]


@app.get(
    "/health",
    response_model=HealthResponse,
    tags=["platform"],
    summary="Check API process health",
)
def health() -> HealthResponse:
    """Report that the API process is running."""

    return HealthResponse(status="healthy")


@app.get(
    "/ready",
    response_model=ReadinessResponse,
    tags=["platform"],
    summary="Check API readiness",
)
def readiness() -> ReadinessResponse:
    """Report readiness only when PostgreSQL is reachable."""

    engine = None

    try:
        engine = create_database_engine()
        verify_database_connection(engine)
    except (RuntimeError, SQLAlchemyError) as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "status": "not_ready",
                "database": "unavailable",
            },
        ) from error
    finally:
        if engine is not None:
            engine.dispose()

    return ReadinessResponse(status="ready")


@app.get(
    "/api/v1/reliability/summary",
    response_model=ReliabilitySummary,
    tags=["reliability"],
    summary="Get system-wide TTC delay statistics",
)
def reliability_summary() -> ReliabilitySummary:
    """Return aggregate statistics across all stored delay events."""

    engine = None

    try:
        engine = create_database_engine()
        return fetch_reliability_summary(engine)
    except (RuntimeError, SQLAlchemyError) as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Reliability data is temporarily unavailable",
        ) from error
    finally:
        if engine is not None:
            engine.dispose()


@app.get(
    "/api/v1/reliability/lines",
    response_model=list[LineReliability],
    tags=["reliability"],
    summary="Rank TTC lines by delay impact",
)
def line_reliability(
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[LineReliability]:
    """Return line-level statistics ordered by total delay minutes."""

    engine = None

    try:
        engine = create_database_engine()
        return fetch_line_reliability(engine, limit=limit)
    except (RuntimeError, SQLAlchemyError) as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Reliability data is temporarily unavailable",
        ) from error
    finally:
        if engine is not None:
            engine.dispose()


@app.get(
    "/api/v1/reliability/stations",
    response_model=list[StationReliability],
    tags=["reliability"],
    summary="Rank TTC stations by delay impact",
)
def station_reliability(
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    line: Annotated[str | None, Query(min_length=1, max_length=20)] = None,
) -> list[StationReliability]:
    """Return station statistics, optionally filtered by TTC line."""

    normalized_line = line.strip().upper() if line is not None else None

    if normalized_line == "":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Line cannot be blank",
        )

    engine = None

    try:
        engine = create_database_engine()
        return fetch_station_reliability(
            engine,
            limit=limit,
            line=normalized_line,
        )
    except (RuntimeError, SQLAlchemyError) as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Reliability data is temporarily unavailable",
        ) from error
    finally:
        if engine is not None:
            engine.dispose()


@app.get(
    "/api/v1/reliability/causes",
    response_model=list[CauseReliability],
    tags=["reliability"],
    summary="Rank TTC incident causes by delay impact",
)
def cause_reliability(
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    line: Annotated[str | None, Query(min_length=1, max_length=20)] = None,
) -> list[CauseReliability]:
    """Return incident-code statistics, optionally filtered by line."""

    normalized_line = line.strip().upper() if line is not None else None

    if normalized_line == "":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Line cannot be blank",
        )

    engine = None

    try:
        engine = create_database_engine()
        return fetch_cause_reliability(
            engine,
            limit=limit,
            line=normalized_line,
        )
    except (RuntimeError, SQLAlchemyError) as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Reliability data is temporarily unavailable",
        ) from error
    finally:
        if engine is not None:
            engine.dispose()


@app.get(
    "/api/v1/reliability/monthly",
    response_model=list[MonthlyReliability],
    tags=["reliability"],
    summary="Get monthly TTC delay trends",
)
def monthly_reliability(
    line: Annotated[str | None, Query(min_length=1, max_length=20)] = None,
) -> list[MonthlyReliability]:
    """Return chronological monthly statistics, optionally by line."""

    normalized_line = line.strip().upper() if line is not None else None

    if normalized_line == "":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Line cannot be blank",
        )

    engine = None

    try:
        engine = create_database_engine()
        return fetch_monthly_reliability(
            engine,
            line=normalized_line,
        )
    except (RuntimeError, SQLAlchemyError) as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Reliability data is temporarily unavailable",
        ) from error
    finally:
        if engine is not None:
            engine.dispose()
