"""Download the current TTC subway delay CSV from Toronto Open Data."""

import json
import sys
import urllib.request
from pathlib import Path


PACKAGE_ID = "ttc-subway-delay-data"
CKAN_PACKAGE_URL = (
    "https://ckan0.cf.opendata.inter.prod-toronto.ca"
    "/api/3/action/package_show"
    f"?id={PACKAGE_ID}"
)

RESOURCE_NAME = "TTC Subway Delay Data since 2025.csv"


def get_resource_url() -> str:
    """Discover the current CSV resource URL from the Toronto Open Data catalogue."""

    with urllib.request.urlopen(CKAN_PACKAGE_URL, timeout=30) as response:
        payload = json.load(response)

    if not payload.get("success"):
        raise RuntimeError("Toronto Open Data catalogue request failed.")

    resources = payload["result"]["resources"]

    for resource in resources:
        if (
            resource.get("name") == RESOURCE_NAME
            and resource.get("format", "").upper() == "CSV"
        ):
            return resource["url"]

    raise RuntimeError(
        f"Could not find resource: {RESOURCE_NAME}"
    )


def download_file(destination: Path) -> Path:
    """Download the TTC CSV to destination."""

    resource_url = get_resource_url()

    destination.parent.mkdir(parents=True, exist_ok=True)

    print(f"Downloading: {RESOURCE_NAME}")
    print(f"Source: {resource_url}")
    print(f"Destination: {destination}")

    urllib.request.urlretrieve(resource_url, destination)

    print(f"Download completed: {destination}")
    return destination


def main() -> int:
    destination = Path(
        sys.argv[1] if len(sys.argv) > 1 else "/tmp/ttc-subway-delays.csv"
    )

    try:
        download_file(destination)
    except Exception as error:
        print(f"Download failed: {error}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
