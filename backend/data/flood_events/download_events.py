"""Download only catalogued, licensed bulk event datasets with recorded provenance."""

import argparse
import hashlib
import json
import tempfile
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.data.flood_events.discover_sources import (
    DATA_DIR,
    INVENTORY_PATH,
    load_inventory,
    require_permitted_event_source,
)

RAW_DIR = DATA_DIR / "raw"
MAX_DOWNLOAD_BYTES = 250 * 1024 * 1024
ALLOWED_EXTENSIONS = {".csv", ".json", ".geojson"}


def download_source(source_name: str, output_dir: Path = RAW_DIR) -> dict[str, Any]:
    inventory = load_inventory()
    source = next(
        (item for item in inventory["sources"] if item.get("source_name") == source_name),
        None,
    )
    if source is None:
        raise ValueError(f"Unknown source name {source_name!r}; add it to {INVENTORY_PATH} first.")

    url = source.get("bulk_download_url")
    if source.get("access_status") != "public_bulk_download" or not url:
        raise ValueError(
            f"{source_name!r} is not marked as a verified public bulk download; "
            "no request was made."
        )
    if urllib.parse.urlparse(url).scheme != "https":
        raise ValueError(f"{source_name!r} must use HTTPS for bulk downloads.")
    if not source.get("license"):
        raise ValueError(f"{source_name!r} has no documented license; refusing the download.")
    require_permitted_event_source(source_name)

    extension = Path(urllib.parse.urlparse(url).path).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise ValueError(f"Unsupported source file extension {extension!r}.")

    output_dir.mkdir(parents=True, exist_ok=True)
    safe_name = "".join(char.lower() if char.isalnum() else "_" for char in source_name).strip("_")
    destination = output_dir / f"{safe_name}{extension}"
    provenance_path = destination.with_suffix(destination.suffix + ".provenance.json")
    if destination.exists() or provenance_path.exists():
        raise FileExistsError(
            f"Download destination already exists for {source_name!r}; "
            "choose another output directory to preserve prior source files."
        )
    digest = hashlib.sha256()
    byte_count = 0
    request = urllib.request.Request(url, headers={"User-Agent": "MumbaiFloodIntelligenceData/1.0"})
    temporary_destination = None
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            if urllib.parse.urlparse(response.geturl()).scheme != "https":
                raise ValueError("The bulk download redirected away from HTTPS.")
            with tempfile.NamedTemporaryFile(
                mode="wb",
                dir=output_dir,
                prefix=f".{destination.name}.",
                suffix=".part",
                delete=False,
            ) as target:
                temporary_destination = Path(target.name)
                while True:
                    chunk = response.read(64 * 1024)
                    if not chunk:
                        break
                    byte_count += len(chunk)
                    if byte_count > MAX_DOWNLOAD_BYTES:
                        raise ValueError(
                            f"Download exceeded the {MAX_DOWNLOAD_BYTES}-byte safety limit."
                        )
                    digest.update(chunk)
                    target.write(chunk)
        if temporary_destination is None:
            raise RuntimeError("Temporary download file was not created.")
        if destination.exists() or provenance_path.exists():
            raise FileExistsError(
                f"Download destination appeared during transfer for {source_name!r}."
            )
        temporary_destination.replace(destination)
    except Exception:
        if temporary_destination is not None:
            temporary_destination.unlink(missing_ok=True)
        raise

    provenance = {
        "source_name": source_name,
        "source_url": source["source_url"],
        "bulk_download_url": url,
        "publisher": source.get("publisher"),
        "license": source["license"],
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "file_name": destination.name,
        "bytes": byte_count,
        "sha256": digest.hexdigest(),
    }
    with provenance_path.open("x", encoding="utf-8") as file:
        file.write(json.dumps(provenance, indent=2, ensure_ascii=False) + "\n")
    return provenance


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, help="Exact source_name from sources.json.")
    parser.add_argument("--output-dir", type=Path, default=RAW_DIR)
    args = parser.parse_args()
    try:
        result = download_source(args.source, args.output_dir)
    except Exception as exc:
        parser.error(str(exc))
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
