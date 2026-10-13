
import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

DATA_DIR = BASE_DIR / "data"
KB_DIR = BASE_DIR / "kb"
UPLOAD_DIR = BASE_DIR / "uploads"

PRICE_DIR = UPLOAD_DIR / "price"
BOOK_COVER_DIR = UPLOAD_DIR / "book_cover"
BOOK_PDF_DIR = UPLOAD_DIR / "book_pdf"

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
            f"{path.name} not found at {path}"
        )

    with path.open("r", encoding="utf-8-sig") as file:
        data = json.load(file)

    if not isinstance(data, list):
        raise ValueError(
            f"{path.name} must contain a JSON array"
        )

    if not all(isinstance(item, dict) for item in data):
        raise ValueError(
            f"{path.name} must contain JSON objects"
        )

    return data


def list_records(collection, include_deleted=False):
    records = _read_all(collection)

    if not include_deleted:
        records = [
            record for record in records
            if not record.get("delete_at")
        ]

    def record_id(record):
        try:
            return int(record.get("id", 0))
        except (TypeError, ValueError):
            return 0

    return sorted(records, key=record_id, reverse=True)


def get_record(collection, record_id):
    for record in list_records(collection):
        if str(record.get("id")) == str(record_id):
            return record
    return None


def data_status():
    result = {}

    for collection, path in JSON_FILES.items():
        result[collection] = {
            "path": str(path),
            "exists": path.is_file(),
        }

    return result
