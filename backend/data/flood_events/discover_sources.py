"""Emit the checked source inventory without mistaking rainfall or news for labels."""

import argparse
import json
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).resolve().parent
INVENTORY_PATH = DATA_DIR / "sources.json"


def load_inventory() -> dict[str, Any]:
    with INVENTORY_PATH.open(encoding="utf-8") as file:
        inventory = json.load(file)
    if not isinstance(inventory.get("sources"), list):
        raise ValueError(f"{INVENTORY_PATH} has no sources list.")
    return inventory


def require_permitted_event_source(source_name: str) -> dict[str, Any]:
    """Require an inventoried flood-event source with documented processing permission."""
    inventory = load_inventory()
    source = next(
        (item for item in inventory["sources"] if item.get("source_name") == source_name),
        None,
    )
    if source is None:
        raise ValueError(f"Unknown source name {source_name!r}; add it to sources.json first.")
    if source.get("record_type") != "flood_event_records":
        raise ValueError(f"{source_name!r} is not catalogued as flood event records.")
    if source.get("permission_status") not in {"public_license", "written_permission"}:
        raise ValueError(f"{source_name!r} has no documented permission to process event records.")
    if not (source.get("license") or source.get("usage_terms")):
        raise ValueError(f"{source_name!r} has no documented license or usage terms.")
    return source


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="Optional path to write the inventory JSON.")
    args = parser.parse_args()

    inventory = load_inventory()
    rendered = json.dumps(inventory, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")


if __name__ == "__main__":
    main()
