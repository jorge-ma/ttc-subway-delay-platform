"""Create and verify PostgreSQL connections for the TTC application."""

import os
import sys
from collections.abc import Mapping

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, URL


load_dotenv()

REQUIRED_SETTINGS = (
    "POSTGRES_HOST",
    "POSTGRES_PORT",
    "POSTGRES_DB",
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
)


def get_database_url(
    settings: Mapping[str, str] | None = None,
) -> URL:
    """Build a SQLAlchemy URL from supplied or environment settings."""

    source = os.environ if settings is None else settings
    missing_settings = [
        setting
        for setting in REQUIRED_SETTINGS
        if not source.get(setting)
    ]

    if missing_settings:
        missing_list = ", ".join(missing_settings)
        raise RuntimeError(
            f"Missing required database settings: {missing_list}"
        )

    try:
        port = int(source["POSTGRES_PORT"])
    except ValueError as error:
        raise RuntimeError(
            "POSTGRES_PORT must be an integer"
        ) from error

    if not 1 <= port <= 65535:
        raise RuntimeError(
            "POSTGRES_PORT must be between 1 and 65535"
        )

    return URL.create(
        drivername="postgresql+psycopg",
        username=source["POSTGRES_USER"],
        password=source["POSTGRES_PASSWORD"],
        host=source["POSTGRES_HOST"],
        port=port,
        database=source["POSTGRES_DB"],
    )


def create_database_engine(
    database_url: URL | str | None = None,
) -> Engine:
    """Create a SQLAlchemy database engine."""

    return create_engine(
        database_url or get_database_url(),
        pool_pre_ping=True,
    )


def verify_database_connection(engine: Engine) -> tuple[str, str]:
    """Return the connected database and user names."""

    query = text(
        "SELECT current_database() AS database_name, "
        "current_user AS user_name"
    )

    with engine.connect() as connection:
        result = connection.execute(query).one()

    return result.database_name, result.user_name


def main() -> int:
    """Verify application connectivity to PostgreSQL."""

    engine: Engine | None = None

    try:
        engine = create_database_engine()
        database_name, user_name = verify_database_connection(engine)
    except Exception as error:
        print(f"Database connection failed: {error}", file=sys.stderr)
        return 1
    finally:
        if engine is not None:
            engine.dispose()

    print("Database connection successful")
    print(f"Database: {database_name}")
    print(f"User: {user_name}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
