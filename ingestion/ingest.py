"""Run the TTC CSV cleaning pipeline and write controlled outputs."""

import argparse
import os
import sys
from pathlib import Path
from tempfile import NamedTemporaryFile

import pandas as pd

from ingestion.cleaning import CleaningResult, clean_data
from ingestion.explore import load_csv


DEFAULT_PROCESSED_OUTPUT = Path(
    "data/processed/ttc-subway-delays-clean.csv"
)
DEFAULT_REJECTED_OUTPUT = Path(
    "data/rejected/ttc-subway-delays-rejected.csv"
)
DEFAULT_DUPLICATE_OUTPUT = Path(
    "data/rejected/ttc-subway-delays-duplicates.csv"
)


def validate_paths(
    input_path: Path,
    processed_output: Path,
    rejected_output: Path,
    duplicate_output: Path,
) -> None:
    """Prevent any output from overwriting another pipeline file."""

    paths = (
        input_path,
        processed_output,
        rejected_output,
        duplicate_output,
    )
    resolved_paths = [path.resolve() for path in paths]

    if len(set(resolved_paths)) != len(resolved_paths):
        raise ValueError(
            "Input and output paths must all be different"
        )


def write_csv_atomically(data: pd.DataFrame, output_path: Path) -> None:
    """Write a CSV through a temporary file to avoid partial output."""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None

    try:
        with NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="",
            prefix=f".{output_path.name}.",
            suffix=".tmp",
            dir=output_path.parent,
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
            data.to_csv(temporary_file, index=False)

        os.replace(temporary_path, output_path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def run_ingestion(
    input_path: Path,
    processed_output: Path = DEFAULT_PROCESSED_OUTPUT,
    rejected_output: Path = DEFAULT_REJECTED_OUTPUT,
    duplicate_output: Path = DEFAULT_DUPLICATE_OUTPUT,
) -> CleaningResult:
    """Load, clean, validate, deduplicate, and write TTC records."""

    validate_paths(
        input_path=input_path,
        processed_output=processed_output,
        rejected_output=rejected_output,
        duplicate_output=duplicate_output,
    )

    raw_data = load_csv(input_path)
    result = clean_data(raw_data)

    write_csv_atomically(result.valid_data, processed_output)
    write_csv_atomically(result.rejected_data, rejected_output)
    write_csv_atomically(result.duplicate_data, duplicate_output)

    return result


def parse_arguments() -> argparse.Namespace:
    """Parse ingestion command-line arguments."""

    parser = argparse.ArgumentParser(
        description=(
            "Clean, validate, and deduplicate TTC subway-delay data."
        )
    )
    parser.add_argument(
        "--input",
        required=True,
        type=Path,
        help="Path to the source TTC CSV file.",
    )
    parser.add_argument(
        "--processed-output",
        type=Path,
        default=DEFAULT_PROCESSED_OUTPUT,
        help="Destination for valid, deduplicated records.",
    )
    parser.add_argument(
        "--rejected-output",
        type=Path,
        default=DEFAULT_REJECTED_OUTPUT,
        help="Destination for invalid records and rejection reasons.",
    )
    parser.add_argument(
        "--duplicate-output",
        type=Path,
        default=DEFAULT_DUPLICATE_OUTPUT,
        help="Destination for duplicate records.",
    )

    return parser.parse_args()


def main() -> int:
    """Execute the command-line ingestion pipeline."""

    arguments = parse_arguments()

    try:
        result = run_ingestion(
            input_path=arguments.input,
            processed_output=arguments.processed_output,
            rejected_output=arguments.rejected_output,
            duplicate_output=arguments.duplicate_output,
        )
    except (FileNotFoundError, OSError, ValueError) as error:
        print(f"Ingestion failed: {error}", file=sys.stderr)
        return 1

    print("TTC ingestion completed")
    print(f"Source rows: {result.source_rows}")
    print(f"Valid rows: {len(result.valid_data)}")
    print(f"Rejected rows: {len(result.rejected_data)}")
    print(f"Duplicate rows: {len(result.duplicate_data)}")
    print(f"Processed output: {arguments.processed_output}")
    print(f"Rejected output: {arguments.rejected_output}")
    print(f"Duplicate output: {arguments.duplicate_output}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
