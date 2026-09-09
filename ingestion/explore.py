"""Explore and validate the structure of a TTC subway-delay CSV file."""

import argparse
import re
import sys
from pathlib import Path

import pandas as pd
from pandas.errors import EmptyDataError, ParserError


# Toronto Open Data has used both ``_id`` and ``lsp_id`` for the source
# identifier. Column-name normalization converts ``_id`` to ``id``. Both
# variants are mapped to one stable internal name.
COLUMN_ALIASES = {
    "id": "source_id",
    "lsp_id": "source_id",
}


REQUIRED_COLUMNS = {
    "source_id",
    "date",
    "time",
    "day",
    "station",
    "code",
    "min_delay",
    "min_gap",
    "bound",
    "line",
    "vehicle",
}


def normalize_column_name(column_name: str) -> str:
    """Convert a column name to lowercase snake_case."""

    normalized = column_name.strip().lower()
    normalized = re.sub(r"[^a-z0-9]+", "_", normalized)

    return normalized.strip("_")


def normalize_columns(data: pd.DataFrame) -> pd.DataFrame:
    """Normalize source headers and apply known column aliases."""

    normalized_columns = [
        normalize_column_name(column)
        for column in data.columns
    ]

    data.columns = [
        COLUMN_ALIASES.get(column, column)
        for column in normalized_columns
    ]

    duplicate_columns = data.columns[data.columns.duplicated()].tolist()

    if duplicate_columns:
        duplicate_list = ", ".join(sorted(set(duplicate_columns)))
        raise ValueError(
            "Column normalization produced duplicate columns: "
            f"{duplicate_list}"
        )

    return data


def load_csv(file_path: Path) -> pd.DataFrame:
    """Load and validate a TTC subway-delay CSV file."""

    if not file_path.exists():
        raise FileNotFoundError(f"CSV file not found: {file_path}")

    if not file_path.is_file():
        raise ValueError(f"Path is not a file: {file_path}")

    if file_path.suffix.lower() != ".csv":
        raise ValueError(f"Expected a CSV file: {file_path}")

    try:
        data = pd.read_csv(file_path)
    except EmptyDataError as error:
        raise ValueError(f"CSV file is empty: {file_path}") from error
    except ParserError as error:
        raise ValueError(f"Unable to parse CSV file: {file_path}") from error
    except UnicodeDecodeError as error:
        raise ValueError(
            "CSV file is not using a supported text encoding: "
            f"{file_path}"
        ) from error

    if data.empty:
        raise ValueError(f"CSV file contains no data rows: {file_path}")

    data = normalize_columns(data)

    missing_columns = REQUIRED_COLUMNS - set(data.columns)

    if missing_columns:
        missing_list = ", ".join(sorted(missing_columns))
        raise ValueError(
            f"CSV file is missing required columns: {missing_list}"
        )

    return data


def display_summary(data: pd.DataFrame, file_path: Path) -> None:
    """Display a basic data-quality summary."""

    print("TTC Subway Delay Data Exploration")
    print("=" * 40)
    print(f"File: {file_path}")
    print(f"Rows: {len(data)}")
    print(f"Columns: {len(data.columns)}")

    print("\nColumn names")
    print("-" * 40)

    for column in data.columns:
        print(column)

    print("\nData types")
    print("-" * 40)
    print(data.dtypes.to_string())

    print("\nMissing values")
    print("-" * 40)
    print(data.isna().sum().to_string())

    duplicate_rows = int(data.duplicated().sum())
    duplicate_ids = int(data["source_id"].duplicated().sum())

    print("\nDuplicate information")
    print("-" * 40)
    print(f"Completely duplicated rows: {duplicate_rows}")
    print(f"Duplicate source_id values: {duplicate_ids}")

    print("\nSample records")
    print("-" * 40)
    print(data.head().to_string(index=False))


def parse_arguments() -> argparse.Namespace:
    """Parse command-line arguments."""

    parser = argparse.ArgumentParser(
        description="Explore a TTC subway-delay CSV file."
    )
    parser.add_argument(
        "csv_file",
        type=Path,
        help="Path to the TTC subway-delay CSV file.",
    )

    return parser.parse_args()


def main() -> int:
    """Run the CSV exploration program."""

    arguments = parse_arguments()

    try:
        data = load_csv(arguments.csv_file)
        display_summary(data, arguments.csv_file)
    except (FileNotFoundError, ValueError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
