
import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "public" / "data"

JSON_FILES = {
    "books": DATA_DIR / "books.json",
    "shops": DATA_DIR / "shops.json",
    "media": DATA_DIR / "media.json",
}


def _get_path(collection):
    if collection not in JSON_FILES:
        raise ValueError(f"Unknown collection: {collection}")
    return JSON_FILES[collection]


def _read_all(collection):
    path = _get_path(collection)

    if not path.is_file():
        raise FileNotFoundError(
            f"{collection}.json not found in public/data"
        )

    try:
        with path.open("r", encoding="utf-8-sig") as file:
            data = json.load(file)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"{collection}.json contains invalid JSON "
            f"at line {exc.lineno}, column {exc.colno}"
        ) from exc

    if not isinstance(data, list):
        raise ValueError(f"{collection}.json must contain a JSON array")

    if not all(isinstance(item, dict) for item in data):
        raise ValueError(
            f"{collection}.json must contain JSON objects in its array"
        )

    return data


def _safe_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def list_records(collection, include_deleted=False):
    records = _read_all(collection)

    if not include_deleted:
        records = [
            record for record in records
            if not record.get("delete_at")
        ]

    return sorted(
        records,
        key=lambda record: _safe_int(record.get("id")),
        reverse=True,
    )


def get_record(collection, record_id):
    for record in list_records(collection):
        if str(record.get("id")) == str(record_id):
            return record
    return None
