
from pathlib import Path
import json

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "public" / "data"

JSON_FILES = {
    "books": DATA_DIR / "books.json",
    "shops": DATA_DIR / "shops.json",
    "media": DATA_DIR / "media.json",
}


def _read_all(collection):
    if collection not in JSON_FILES:
        raise ValueError(f"Unknown collection: {collection}")

    path = JSON_FILES[collection]

    if not path.is_file():
        raise FileNotFoundError(
            f"{path.name} not found at {path}"
        )

    with path.open("r", encoding="utf-8-sig") as file:
        data = json.load(file)

    if not isinstance(data, list):
        raise ValueError(
            f"{path.name} must contain a JSON array"
        )

    return data


def list_records(collection, include_deleted=False):
    records = _read_all(collection)

    if not include_deleted:
        records = [
            record for record in records
            if not record.get("delete_at")
        ]

    return sorted(
        records,
        key=lambda record: int(record.get("id", 0)),
        reverse=True,
    )


def get_record(collection, record_id):
    for record in list_records(collection):
        if str(record.get("id")) == str(record_id):
            return record

    return None
