
import json
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "public" / "data"

JSON_FILES = {
    "books": DATA_DIR / "books.json",
    "shops": DATA_DIR / "shops.json",
    "media": DATA_DIR / "media.json",
}


def _get_path(collection):
    """Allow only predefined JSON collections."""
    if collection not in JSON_FILES:
        raise ValueError(f"Unknown collection: {collection}")

    return JSON_FILES[collection]


def _read_all(collection):
    """Read records without creating or modifying files."""
    path = _get_path(collection)

    if not path.is_file():
        raise FileNotFoundError(
            f"Required JSON file does not exist: {path}"
        )

    try:
        with path.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"{path.name} contains invalid JSON: {exc}"
        ) from exc

    if not isinstance(data, list):
        raise ValueError(
            f"{path.name} must contain a JSON array."
        )

    for index, record in enumerate(data):
        if not isinstance(record, dict):
            raise ValueError(
                f"{path.name}: record at index {index} "
                "must be a JSON object."
            )

    return data


def _safe_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def list_records(collection, include_deleted=False):
    """
    Return records ordered by ID descending.
    Soft-deleted records are hidden by default.
    """
    records = _read_all(collection)

    if not include_deleted:
        records = [
            record
            for record in records
            if not record.get("delete_at")
        ]

    return sorted(
        records,
        key=lambda record: _safe_int(record.get("id")),
        reverse=True,
    )


def get_record(collection, record_id):
    """Return one non-deleted record, or None."""
    for record in list_records(collection):
        if str(record.get("id")) == str(record_id):
            return record

    return None
