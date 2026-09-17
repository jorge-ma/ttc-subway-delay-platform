"""Database queries and response models for TTC reliability metrics."""

import csv
from datetime import datetime
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel
from sqlalchemy import distinct, func, select
from sqlalchemy.engine import Engine

from database.models import DelayEvent


DELAY_CODE_FILE = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "reference"
    / "ttc-delay-codes.csv"
)


@lru_cache(maxsize=1)
def load_delay_code_descriptions() -> dict[str, str]:
    """Load TTC delay-code descriptions from the reference CSV."""

    descriptions: dict[str, str] = {}

    with DELAY_CODE_FILE.open(
        mode="r",
        encoding="utf-8-sig",
        newline="",
    ) as file:
        reader = csv.DictReader(file)

        for row in reader:
            code = row["code"].strip().upper()
            description = row["description"].strip()

            if code:
                descriptions[code] = description

    return descriptions


class ReliabilitySummary(BaseModel):
    """Aggregate reliability statistics across all stored events."""

    total_events: int
    total_delay_minutes: int
    average_delay_minutes: float
    maximum_delay_minutes: int
    affected_stations: int
    first_event_at: datetime | None
    last_event_at: datetime | None


class LineReliability(BaseModel):
    """Aggregate reliability statistics for one normalized TTC line."""

    line: str
    total_events: int
    total_delay_minutes: int
    average_delay_minutes: float
    maximum_delay_minutes: int
    affected_stations: int


class StationReliability(BaseModel):
    """Aggregate reliability statistics for one station and line."""

    station: str
    line: str
    total_events: int
    total_delay_minutes: int
    average_delay_minutes: float
    maximum_delay_minutes: int


class CauseReliability(BaseModel):
    """Aggregate reliability statistics for one TTC incident code."""

    code: str
    description: str
    total_events: int
    total_delay_minutes: int
    average_delay_minutes: float
    maximum_delay_minutes: int
    affected_stations: int


class MonthlyReliability(BaseModel):
    """Aggregate reliability statistics for one calendar month."""

    month: str
    total_events: int
    total_delay_minutes: int
    average_delay_minutes: float
    maximum_delay_minutes: int
    affected_stations: int


def fetch_reliability_summary(
    engine: Engine,
) -> ReliabilitySummary:
    """Return aggregate reliability statistics from PostgreSQL."""

    statement = select(
        func.count(DelayEvent.id).label("total_events"),
        func.coalesce(
            func.sum(DelayEvent.min_delay),
            0,
        ).label("total_delay_minutes"),
        func.coalesce(
            func.avg(DelayEvent.min_delay),
            0,
        ).label("average_delay_minutes"),
        func.coalesce(
            func.max(DelayEvent.min_delay),
            0,
        ).label("maximum_delay_minutes"),
        func.count(
            distinct(DelayEvent.station)
        ).label("affected_stations"),
        func.min(
            DelayEvent.event_datetime
        ).label("first_event_at"),
        func.max(
            DelayEvent.event_datetime
        ).label("last_event_at"),
    )

    with engine.connect() as connection:
        result = connection.execute(statement).one()

    return ReliabilitySummary(
        total_events=int(result.total_events),
        total_delay_minutes=int(
            result.total_delay_minutes
        ),
        average_delay_minutes=round(
            float(result.average_delay_minutes),
            2,
        ),
        maximum_delay_minutes=int(
            result.maximum_delay_minutes
        ),
        affected_stations=int(
            result.affected_stations
        ),
        first_event_at=result.first_event_at,
        last_event_at=result.last_event_at,
    )


def fetch_line_reliability(
    engine: Engine,
    limit: int = 20,
) -> list[LineReliability]:
    """Return TTC lines ranked by their total delay minutes."""

    total_delay = func.sum(DelayEvent.min_delay)

    statement = (
        select(
            DelayEvent.line.label("line"),
            func.count(
                DelayEvent.id
            ).label("total_events"),
            total_delay.label(
                "total_delay_minutes"
            ),
            func.avg(
                DelayEvent.min_delay
            ).label("average_delay_minutes"),
            func.max(
                DelayEvent.min_delay
            ).label("maximum_delay_minutes"),
            func.count(
                distinct(DelayEvent.station)
            ).label("affected_stations"),
        )
        .group_by(DelayEvent.line)
        .order_by(
            total_delay.desc(),
            DelayEvent.line.asc(),
        )
        .limit(limit)
    )

    with engine.connect() as connection:
        results = connection.execute(statement).all()

    return [
        LineReliability(
            line=result.line,
            total_events=int(result.total_events),
            total_delay_minutes=int(
                result.total_delay_minutes
            ),
            average_delay_minutes=round(
                float(result.average_delay_minutes),
                2,
            ),
            maximum_delay_minutes=int(
                result.maximum_delay_minutes
            ),
            affected_stations=int(
                result.affected_stations
            ),
        )
        for result in results
    ]


def fetch_station_reliability(
    engine: Engine,
    limit: int = 20,
    line: str | None = None,
) -> list[StationReliability]:
    """Return real stations ranked by delay, optionally for one TTC line."""

    total_delay = func.sum(DelayEvent.min_delay)

    station_upper = func.upper(
        func.trim(DelayEvent.station)
    )

    statement = select(
        DelayEvent.station.label("station"),
        DelayEvent.line.label("line"),
        func.count(
            DelayEvent.id
        ).label("total_events"),
        total_delay.label(
            "total_delay_minutes"
        ),
        func.avg(
            DelayEvent.min_delay
        ).label("average_delay_minutes"),
        func.max(
            DelayEvent.min_delay
        ).label("maximum_delay_minutes"),
    )

    # TTC source data occasionally uses the Station field for
    # line-wide incidents rather than an actual station.
    #
    # These events remain in PostgreSQL and still contribute to
    # line, monthly, cause, and overall statistics. They are only
    # excluded from the station-ranking endpoint.
    statement = statement.where(
        ~station_upper.in_(
            [
                "LINE 1",
                "LINE 2",
                "LINE 4",
            ]
        ),
        ~station_upper.like("LINE 1%"),
        ~station_upper.like("LINE 2%"),
        ~station_upper.like("LINE 4%"),
        ~station_upper.like("%LINE 1"),
        ~station_upper.like("%LINE 2"),
        ~station_upper.like("%LINE 4"),
    )

    if line is not None:
        statement = statement.where(
            DelayEvent.line == line
        )

    statement = (
        statement
        .group_by(
            DelayEvent.station,
            DelayEvent.line,
        )
        .order_by(
            total_delay.desc(),
            DelayEvent.station.asc(),
            DelayEvent.line.asc(),
        )
        .limit(limit)
    )

    with engine.connect() as connection:
        results = connection.execute(statement).all()

    return [
        StationReliability(
            station=result.station,
            line=result.line,
            total_events=int(result.total_events),
            total_delay_minutes=int(
                result.total_delay_minutes
            ),
            average_delay_minutes=round(
                float(result.average_delay_minutes),
                2,
            ),
            maximum_delay_minutes=int(
                result.maximum_delay_minutes
            ),
        )
        for result in results
    ]


def fetch_cause_reliability(
    engine: Engine,
    limit: int = 20,
    line: str | None = None,
) -> list[CauseReliability]:
    """Return incident causes ranked by total delay minutes."""

    descriptions = load_delay_code_descriptions()

    total_delay = func.sum(DelayEvent.min_delay)

    statement = select(
        DelayEvent.code.label("code"),
        func.count(
            DelayEvent.id
        ).label("total_events"),
        total_delay.label(
            "total_delay_minutes"
        ),
        func.avg(
            DelayEvent.min_delay
        ).label("average_delay_minutes"),
        func.max(
            DelayEvent.min_delay
        ).label("maximum_delay_minutes"),
        func.count(
            distinct(DelayEvent.station)
        ).label("affected_stations"),
    )

    if line is not None:
        statement = statement.where(
            DelayEvent.line == line
        )

    statement = (
        statement
        .group_by(DelayEvent.code)
        .order_by(
            total_delay.desc(),
            DelayEvent.code.asc(),
        )
        .limit(limit)
    )

    with engine.connect() as connection:
        results = connection.execute(statement).all()

    return [
        CauseReliability(
            code=result.code,
            description=descriptions.get(
                result.code.strip().upper(),
                "Undocumented TTC code",
            ),
            total_events=int(result.total_events),
            total_delay_minutes=int(
                result.total_delay_minutes
            ),
            average_delay_minutes=round(
                float(result.average_delay_minutes),
                2,
            ),
            maximum_delay_minutes=int(
                result.maximum_delay_minutes
            ),
            affected_stations=int(
                result.affected_stations
            ),
        )
        for result in results
    ]


def fetch_monthly_reliability(
    engine: Engine,
    line: str | None = None,
) -> list[MonthlyReliability]:
    """Return chronological monthly metrics, optionally for one line."""

    month = func.date_trunc(
        "month",
        DelayEvent.event_datetime,
    )

    statement = select(
        month.label("month"),
        func.count(
            DelayEvent.id
        ).label("total_events"),
        func.sum(
            DelayEvent.min_delay
        ).label("total_delay_minutes"),
        func.avg(
            DelayEvent.min_delay
        ).label("average_delay_minutes"),
        func.max(
            DelayEvent.min_delay
        ).label("maximum_delay_minutes"),
        func.count(
            distinct(DelayEvent.station)
        ).label("affected_stations"),
    )

    if line is not None:
        statement = statement.where(
            DelayEvent.line == line
        )

    statement = (
        statement
        .group_by(month)
        .order_by(month.asc())
    )

    with engine.connect() as connection:
        results = connection.execute(statement).all()

    return [
        MonthlyReliability(
            month=result.month.strftime("%Y-%m"),
            total_events=int(result.total_events),
            total_delay_minutes=int(
                result.total_delay_minutes
            ),
            average_delay_minutes=round(
                float(result.average_delay_minutes),
                2,
            ),
            maximum_delay_minutes=int(
                result.maximum_delay_minutes
            ),
            affected_stations=int(
                result.affected_stations
            ),
        )
        for result in results
    ]

