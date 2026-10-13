
import json
import os
import threading
from datetime import datetime, timezone
from storage import list_records


BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Vercel allows temporary writes under /tmp.
# Local development continues using public/data.

DATA_DIR = os.path.join(BASE_DIR, "public", "data")

JSON_FILES = {
    "books": os.path.join(DATA_DIR, "books.json"),
    "shops": os.path.join(DATA_DIR, "shops.json"),
    "media": os.path.join(DATA_DIR, "media.json"),
}

# Protect simultaneous read/write operations within one process.
_STORAGE_LOCK = threading.RLock()


def _now_iso():
    """Return current UTC time as an ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()


def _get_path(collection):
    """Return the JSON path for an allowed collection."""
    if collection not in JSON_FILES:
        raise ValueError(f"Unknown collection: {collection}")

    return JSON_FILES[collection]


def _ensure_file(collection):
    """Create the data directory and an empty JSON array if needed."""
    os.makedirs(DATA_DIR, exist_ok=True)

    path = _get_path(collection)

    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as file:
            json.dump([], file, ensure_ascii=False, indent=2)

    return path


def _read_all(collection):
    """Read all records, including soft-deleted records."""
    path = _ensure_file(collection)

    try:
        with open(path, "r", encoding="utf-8") as file:
            data = json.load(file)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"{collection}.json is invalid JSON. "
            "Restore a valid backup before continuing."
        ) from exc

    if not isinstance(data, list):
        raise RuntimeError(
            f"{collection}.json must contain a JSON array."
        )

    return data


def _write_all(collection, records):
    """Write records to JSON with UTF-8 Burmese text support."""
    path = _ensure_file(collection)
    temp_path = path + ".tmp"

    with open(temp_path, "w", encoding="utf-8") as file:
        json.dump(
            records,
            file,
            ensure_ascii=False,
            indent=2,
        )
        file.flush()
        os.fsync(file.fileno())

    # Replace the original file after the temporary file is complete.
    os.replace(temp_path, path)


def _next_id(records):
    """Generate the next numeric ID."""
    numeric_ids = []

    for record in records:
        try:
            numeric_ids.append(int(record.get("id", 0)))
        except (TypeError, ValueError):
            continue

    return max(numeric_ids, default=0) + 1


def _same_id(record, record_id):
    """Compare IDs safely, allowing string IDs from HTML forms."""
    return str(record.get("id")) == str(record_id)



def load_records(collection):
    """Read records through the existing storage module."""

    if collection not in ("books", "shops", "media"):
        raise ValueError("Unknown collection")

    return list_records(collection)


def get_record(collection, record_id):
    """Return one non-deleted record, or None if not found."""
    with _STORAGE_LOCK:
        records = _read_all(collection)

        for record in records:
            if (
                _same_id(record, record_id)
                and not record.get("delete_at")
            ):
                return record

    return None


def create_record(collection, fields):
    """
    Create a record and return the saved dictionary.

    Reserved fields (id, created_at, updated_at, delete_at)
    are controlled by this module.
    """
    if not isinstance(fields, dict):
        raise ValueError("fields must be a dictionary")

    reserved = {"id", "created_at", "updated_at", "delete_at"}
    if reserved.intersection(fields):
        raise ValueError("Cannot provide reserved record fields")

    with _STORAGE_LOCK:
        records = _read_all(collection)

        record = {
            "id": _next_id(records),
            **fields,
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
            "delete_at": None,
        }

        records.append(record)
        _write_all(collection, records)

        return record


def update_record(collection, record_id, fields):
    """
    Update an existing non-deleted record.

    Returns True if updated, otherwise False.
    """
    if not isinstance(fields, dict):
        raise ValueError("fields must be a dictionary")

    reserved = {"id", "created_at", "updated_at", "delete_at"}
    if reserved.intersection(fields):
        raise ValueError("Cannot update reserved record fields")

    with _STORAGE_LOCK:
        records = _read_all(collection)

        for record in records:
            if (
                _same_id(record, record_id)
                and not record.get("delete_at")
            ):
                record.update(fields)
                record["updated_at"] = _now_iso()

                _write_all(collection, records)
                return True

    return False


def soft_delete_record(collection, record_id):
    """
    Soft-delete a record by setting delete_at.

    Returns True if deleted, otherwise False.
    """
    with _STORAGE_LOCK:
        records = _read_all(collection)

        for record in records:
            if (
                _same_id(record, record_id)
                and not record.get("delete_at")
            ):
                record["delete_at"] = _now_iso()
                record["updated_at"] = _now_iso()

                _write_all(collection, records)
                return True

    return False


def restore_record(collection, record_id):
    """Restore a soft-deleted record."""
    with _STORAGE_LOCK:
        records = _read_all(collection)

        for record in records:
            if (
                _same_id(record, record_id)
                and record.get("delete_at")
            ):
                record["delete_at"] = None
                record["updated_at"] = _now_iso()

                _write_all(collection, records)
                return True

    return False


def hard_delete_record(collection, record_id):
    """
    Permanently remove a record.

    Use only when permanent deletion is intended.
    """
    with _STORAGE_LOCK:
        records = _read_all(collection)

        remaining = [
            record
            for record in records
            if not _same_id(record, record_id)
        ]

        if len(remaining) == len(records):
            return False

        _write_all(collection, remaining)
        return True


def _safe_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
