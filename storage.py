
import json
import threading
from datetime import datetime
from pathlib import Path

# =========================================================
# Project paths
# =========================================================

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

# JSON ဖိုင်ရေးသားရာတွင် တစ်ချိန်တည်းဝင်ရောက်မှုကို
# ကာကွယ်ရန် process အတွင်း lock အသုံးပြုမည်။
_storage_lock = threading.RLock()


# =========================================================
# Initialization
# =========================================================

def init_storage():
    """လိုအပ်သော folder နှင့် JSON ဖိုင်များ မရှိသေးလျှင် ဖန်တီးမည်။"""

    for folder in (
        DATA_DIR,
        KB_DIR,
        UPLOAD_DIR,
        PRICE_DIR,
        BOOK_COVER_DIR,
        BOOK_PDF_DIR,
    ):
        folder.mkdir(parents=True, exist_ok=True)

    for path in JSON_FILES.values():
        if not path.exists():
            _write_json(path, [])


# =========================================================
# Internal helpers
# =========================================================

def _validate_collection(collection):
    """ခွင့်ပြုထားသော collection ကိုသာ အသုံးပြုစေမည်။"""

    if collection not in JSON_FILES:
        raise ValueError(
            f"Invalid collection: {collection}. "
            f"Allowed: {', '.join(JSON_FILES.keys())}"
        )

    return JSON_FILES[collection]


def _now():
    """MySQL TIMESTAMP အစား သုံးမည့် timestamp။"""

    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _read_json(path):
    """JSON ဖိုင်မှ record အားလုံးကို ဖတ်မည်။"""

    if not path.exists():
        return []

    try:
        with path.open("r", encoding="utf-8-sig") as file:
            data = json.load(file)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Invalid JSON file: {path}. "
            "Please fix the JSON format before writing."
        ) from exc

    if not isinstance(data, list):
        raise ValueError(
            f"{path.name} must contain a JSON array."
        )

    return data


def _write_json(path, records):
    """JSON ဖိုင်ကို UTF-8 ဖြင့် အစားထိုးသိမ်းမည်။"""

    path.parent.mkdir(parents=True, exist_ok=True)

    temp_path = path.with_name(path.name + ".tmp")

    try:
        with temp_path.open("w", encoding="utf-8") as file:
            json.dump(
                records,
                file,
                ensure_ascii=False,
                indent=2,
            )
            file.write("\n")

        # ရေးသားမှုအောင်မြင်ပြီးမှ မူရင်းဖိုင်ကို အစားထိုးမည်။
        temp_path.replace(path)

    finally:
        if temp_path.exists():
            temp_path.unlink()


def _next_id(records):
    """AUTO_INCREMENT အစား ID အသစ်ထုတ်ပေးမည်။"""

    ids = []

    for record in records:
        record_id = record.get("id")

        if isinstance(record_id, int) and not isinstance(record_id, bool):
            ids.append(record_id)

    return max(ids, default=0) + 1


def _find_record(records, record_id):
    """ID ကို string/int နှစ်မျိုးစလုံးဖြင့် ရှာနိုင်မည်။"""

    for record in records:
        if str(record.get("id")) == str(record_id):
            return record

    return None


# =========================================================
# READ
# =========================================================

def list_records(collection, include_deleted=False):
    """
    Collection ထဲမှ record အားလုံးကို ဖတ်မည်။

    Default:
        delete_at = null ဖြစ်သော record များသာ ပြမည်။

    include_deleted=True:
        ဖျက်ထားသော record များပါ ပြမည်။
    """

    path = _validate_collection(collection)

    with _storage_lock:
        records = _read_json(path)

        if include_deleted:
            return records

        return [
            record
            for record in records
            if record.get("delete_at") is None
        ]


def get_record(collection, record_id, include_deleted=False):
    """ID ဖြင့် record တစ်ခုကို ရှာမည်။"""

    path = _validate_collection(collection)

    with _storage_lock:
        records = _read_json(path)
        record = _find_record(records, record_id)

        if record is None:
            return None

        if not include_deleted and record.get("delete_at") is not None:
            return None

        return record


# =========================================================
# CREATE
# =========================================================

def create_record(collection, data):
    """
    Record အသစ်ထည့်မည်။

    id, create_at, update_at, delete_at ကို
    system က အလိုအလျောက် သတ်မှတ်မည်။
    """

    path = _validate_collection(collection)

    if not isinstance(data, dict):
        raise ValueError("Record data must be a JSON object.")

    protected_fields = {
        "id",
        "create_at",
        "update_at",
        "delete_at",
    }

    if protected_fields.intersection(data):
        raise ValueError(
            "id, create_at, update_at and delete_at "
            "are managed automatically."
        )

    with _storage_lock:
        records = _read_json(path)
        timestamp = _now()

        record = dict(data)
        record["id"] = _next_id(records)
        record["create_at"] = timestamp
        record["update_at"] = timestamp
        record["delete_at"] = None

        records.append(record)
        _write_json(path, records)

        return record


# =========================================================
# UPDATE
# =========================================================

def update_record(collection, record_id, updates):
    """ရှိပြီးသား record ကို ပြင်မည်။"""

    path = _validate_collection(collection)

    if not isinstance(updates, dict):
        raise ValueError("Updates must be a JSON object.")

    protected_fields = {
        "id",
        "create_at",
        "update_at",
        "delete_at",
    }

    if protected_fields.intersection(updates):
        raise ValueError(
            "id, create_at, update_at and delete_at "
            "cannot be changed directly."
        )

    with _storage_lock:
        records = _read_json(path)
        record = _find_record(records, record_id)

        if record is None or record.get("delete_at") is not None:
            return None

        record.update(updates)
        record["update_at"] = _now()

        _write_json(path, records)

        return record


# =========================================================
# DELETE (Soft Delete)
# =========================================================

def delete_record(collection, record_id):
    """
    MySQL: UPDATE table SET delete_at = CURRENT_TIMESTAMP
    အစား JSON record ၏ delete_at ကို သတ်မှတ်မည်။
    """

    path = _validate_collection(collection)

    with _storage_lock:
        records = _read_json(path)
        record = _find_record(records, record_id)

        if record is None or record.get("delete_at") is not None:
            return False

        timestamp = _now()
        record["delete_at"] = timestamp
        record["update_at"] = timestamp

        _write_json(path, records)

        return True


# =========================================================
# RESTORE
# =========================================================

def restore_record(collection, record_id):
    """Soft Delete လုပ်ထားသော record ကို ပြန်ဖော်မည်။"""

    path = _validate_collection(collection)

    with _storage_lock:
        records = _read_json(path)
        record = _find_record(records, record_id)

        if record is None or record.get("delete_at") is None:
            return False

        record["delete_at"] = None
        record["update_at"] = _now()

        _write_json(path, records)

        return True


# =========================================================
# STATUS
# =========================================================

def data_status():
    """JSON ဖိုင်များ၏ တည်ရှိမှုနှင့် record အရေအတွက်ကို ပြမည်။"""

    result = {}

    for collection, path in JSON_FILES.items():
        try:
            with _storage_lock:
                records = _read_json(path)

            result[collection] = {
                "exists": path.exists(),
                "path": str(path),
                "count": len(records),
                "active_count": sum(
                    1 for item in records
                    if item.get("delete_at") is None
                ),
                "deleted_count": sum(
                    1 for item in records
                    if item.get("delete_at") is not None
                ),
            }

        except (ValueError, OSError) as exc:
            result[collection] = {
                "exists": path.exists(),
                "path": str(path),
                "error": str(exc),
            }

    return result


# App စတင်ချိန်တွင် folder နှင့် JSON ဖိုင်များ ပြင်ဆင်မည်။
init_storage()
