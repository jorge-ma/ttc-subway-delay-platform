"""FastAPI application and TTC reliability endpoints."""

import time
from typing import Annotated, Literal

from fastapi import FastAPI, HTTPException, Query, Request, Response, status
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from api.ingestion import (
    IngestionStatus,
    fetch_latest_ingestion,
)
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
from database.models import IngestionRun


app = FastAPI(
    title="TTC Reliability Monitor API",
    description="Read-only API for TTC subway-delay reliability metrics.",
    version="0.1.0",
)


# ---------------------------------------------------------------------------
# Prometheus API metrics
# ---------------------------------------------------------------------------

API_REQUESTS_TOTAL = Counter(
    "ttc_api_requests_total",
    "Total number of HTTP requests handled by the TTC API.",
    ["method", "path", "status"],
)

API_REQUEST_DURATION_SECONDS = Histogram(
    "ttc_api_request_duration_seconds",
    "HTTP request duration for the TTC API.",
    ["method", "path"],
)


# ---------------------------------------------------------------------------
# Prometheus ingestion metrics
# ---------------------------------------------------------------------------

INGESTION_LAST_SUCCESS_TIMESTAMP_SECONDS = Gauge(
    "ttc_ingestion_last_success_timestamp_seconds",
    "Unix timestamp of the most recent successful ingestion.",
)

INGESTION_LAST_RUN_SUCCESS = Gauge(
    "ttc_ingestion_last_run_success",
    "Whether the most recent ingestion completed successfully: 1=yes, 0=no.",
)

INGESTION_SOURCE_ROWS = Gauge(
    "ttc_ingestion_source_rows",
    "Number of source rows in the most recent ingestion.",
)

INGESTION_VALID_ROWS = Gauge(
    "ttc_ingestion_valid_rows",
    "Number of valid rows in the most recent ingestion.",
)

INGESTION_REJECTED_ROWS = Gauge(
    "ttc_ingestion_rejected_rows",
    "Number of rejected rows in the most recent ingestion.",
)

INGESTION_DUPLICATE_ROWS = Gauge(
    "ttc_ingestion_duplicate_rows",
    "Number of duplicate rows in the most recent ingestion.",
)

INGESTION_INSERTED_ROWS = Gauge(
    "ttc_ingestion_inserted_rows",
    "Number of database inserts in the most recent ingestion.",
)

INGESTION_FAILED_RUNS = Gauge(
    "ttc_ingestion_failed_runs",
    "Total number of failed ingestion runs stored in PostgreSQL.",
)

INGESTION_METRICS_REFRESH_SUCCESS = Gauge(
    "ttc_ingestion_metrics_refresh_success",
    "Whether ingestion metrics were successfully refreshed from PostgreSQL.",
)


def refresh_ingestion_metrics() -> None:
    """Refresh ingestion Prometheus gauges from PostgreSQL."""

    engine = None

    try:
        engine = create_database_engine()

        with Session(engine) as session:
            latest_run = session.scalar(
                select(IngestionRun)
                .order_by(IngestionRun.id.desc())
                .limit(1)
            )

            latest_successful_run = session.scalar(
                select(IngestionRun)
                .where(IngestionRun.status == "completed")
                .order_by(IngestionRun.completed_at.desc())
                .limit(1)
            )

            failed_runs = session.scalar(
                select(func.count())
                .select_from(IngestionRun)
                .where(IngestionRun.status == "failed")
            )

        if latest_run is not None:
            INGESTION_SOURCE_ROWS.set(latest_run.source_rows)
            INGESTION_VALID_ROWS.set(latest_run.valid_rows)
            INGESTION_REJECTED_ROWS.set(latest_run.rejected_rows)
            INGESTION_DUPLICATE_ROWS.set(latest_run.duplicate_rows)
            INGESTION_INSERTED_ROWS.set(latest_run.inserted_rows)

            INGESTION_LAST_RUN_SUCCESS.set(
                1 if latest_run.status == "completed" else 0
            )

        if (
            latest_successful_run is not None
            and latest_successful_run.completed_at is not None
        ):
            INGESTION_LAST_SUCCESS_TIMESTAMP_SECONDS.set(
                latest_successful_run.completed_at.timestamp()
            )

        INGESTION_FAILED_RUNS.set(failed_runs or 0)
        INGESTION_METRICS_REFRESH_SUCCESS.set(1)

    except (RuntimeError, SQLAlchemyError):
        INGESTION_METRICS_REFRESH_SUCCESS.set(0)

    finally:
        if engine is not None:
            engine.dispose()


@app.middleware("http")
async def prometheus_middleware(request: Request, call_next):
    """Record HTTP request count and request duration."""

    start_time = time.perf_counter()

    response = await call_next(request)

    duration = time.perf_counter() - start_time
    path = request.url.path

    API_REQUESTS_TOTAL.labels(
        method=request.method,
        path=path,
        status=str(response.status_code),
    ).inc()

    API_REQUEST_DURATION_SECONDS.labels(
        method=request.method,
        path=path,
    ).observe(duration)

    return response


@app.get(
    "/metrics",
    include_in_schema=False,
)
def metrics() -> Response:
    """Expose application and ingestion metrics in Prometheus format."""

    refresh_ingestion_metrics()

    return Response(
        content=generate_latest(),
        headers={"Content-Type": CONTENT_TYPE_LATEST},
    )


# ---------------------------------------------------------------------------
# Platform response models
# ---------------------------------------------------------------------------

class HealthResponse(BaseModel):
    """Response returned by the process health probe."""

    status: Literal["healthy"]


class ReadinessResponse(BaseModel):
    """Response returned when application dependencies are available."""

    status: Literal["ready"]


# ---------------------------------------------------------------------------
# Platform endpoints
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Ingestion endpoints
# ---------------------------------------------------------------------------

@app.get(
    "/api/v1/ingestion/latest",
    response_model=IngestionStatus,
    tags=["ingestion"],
    summary="Get latest ingestion status",
)
def latest_ingestion() -> IngestionStatus:
    """Return the most recent TTC ingestion execution."""

    engine = None

    try:
        engine = create_database_engine()
        result = fetch_latest_ingestion(engine)

        if result is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No ingestion runs found",
            )

        return result

    except HTTPException:
        raise

    except (RuntimeError, SQLAlchemyError) as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Ingestion status is temporarily unavailable",
        ) from error

    finally:
        if engine is not None:
            engine.dispose()


# ---------------------------------------------------------------------------
# Reliability endpoints
# ---------------------------------------------------------------------------

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

        return fetch_line_reliability(
            engine,
            limit=limit,
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

    normalized_line = (
        line.strip().upper()
        if line is not None
        else None
    )

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

    normalized_line = (
        line.strip().upper()
        if line is not None
        else None
    )

    if normalized_line == "":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
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

    normalized_line = (
        line.strip().upper()
        if line is not None
        else None
    )

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
