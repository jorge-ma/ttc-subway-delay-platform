"""Download the latest TTC subway delay data and run ingestion."""

from pathlib import Path

from ingestion.download import download_file
from ingestion.ingest import main as ingest_main


RAW_FILE = Path("/tmp/ttc-subway-delays.csv")


def main() -> int:
    print("Starting TTC automated ingestion")

    download_file(RAW_FILE)

    return ingest_main(
        [
            "--input",
            str(RAW_FILE),
            "--processed-output",
            "/tmp/ttc-clean.csv",
            "--rejected-output",
            "/tmp/ttc-rejected.csv",
            "--duplicate-output",
            "/tmp/ttc-duplicates.csv",
            "--load-database",
        ]
    )


if __name__ == "__main__":
    raise SystemExit(main())

