
import os
import re
import json
from pathlib import Path

from flask import (
    Flask,
    jsonify,
    render_template,
    send_from_directory,
)

from werkzeug.utils import secure_filename

from storage import list_records


# =========================================================
# PATHS
# =========================================================

BASE_DIR = Path(__file__).resolve().parent

DATA_DIR = BASE_DIR / "public" / "data"

UPLOAD_FOLDER = (
    Path("/tmp/uploads")
    if os.environ.get("VERCEL") == "1"
    else BASE_DIR / "public" / "uploads"
)

PRICE_FOLDER = UPLOAD_FOLDER / "price"


# =========================================================
# FLASK APP
# =========================================================

app = Flask(
    __name__,
    template_folder=str(BASE_DIR / "templates"),
    static_folder=str(BASE_DIR / "static"),
)

app.secret_key = os.environ.get(
    "SECRET_KEY",
    "change-this-secret-key-before-deployment",
)

app.json.ensure_ascii = False

app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024

# Upload directories are only for files; JSON data is read-only.
try:
    UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)
    PRICE_FOLDER.mkdir(parents=True, exist_ok=True)
except OSError:
    app.logger.warning("Could not create upload directories")


# =========================================================
# HELPERS
# =========================================================

ALLOWED_COLLECTIONS = {"books", "shops", "media"}


def extract_month_day(filename):
    name_without_ext = os.path.splitext(filename)[0]

    match = re.search(
        r"([\u1000-\u109F]+လ_[\u1040-\u1049\d]+)",
        name_without_ext,
    )

    if match:
        return match.group(1).replace("_", " ")

    return name_without_ext


def json_error(message, status=400):
    return jsonify({
        "success": False,
        "message": str(message),
    }), status


# =========================================================
# DASHBOARD
# =========================================================

@app.route("/", methods=["GET"])
def index():
    try:
        books = list_records("books")
        shops = list_records("shops")
        media = list_records("media")

        price_files = []

        if PRICE_FOLDER.is_dir():
            for filename in os.listdir(PRICE_FOLDER):
                if filename.lower().endswith((".xlsx", ".xls")):
                    price_files.append({
                        "raw_name": filename,
                        "display_name": extract_month_day(filename),
                    })

        price_files.sort(
            key=lambda item: item["raw_name"],
            reverse=True,
        )

        return render_template(
            "index.html",
            books=books,
            shops=shops,
            media=media,
            price_files=price_files,
            read_only=True,
        )

    except Exception as exc:
        app.logger.exception("Dashboard data loading failed")

        return (
            f"Dashboard data error: {type(exc).__name__}: {exc}",
            500,
        )


# =========================================================
# HEALTH CHECK
# =========================================================

@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({
        "success": True,
        "message": "API is running",
        "read_only": True,
    })


# =========================================================
# FLUTTER READ-ONLY JSON API
# =========================================================

@app.route("/api/<collection>", methods=["GET"])
def get_collection(collection):
    if collection not in ALLOWED_COLLECTIONS:
        return json_error("Unknown collection", 404)

    try:
        records = list_records(collection)

        return jsonify({
            "success": True,
            "count": len(records),
            "data": records,
        })

    except Exception:
        app.logger.exception(
            "Failed to read collection: %s",
            collection,
        )
        return json_error(
            f"Unable to read {collection} data",
            500,
        )


@app.route("/api/<collection>/<record_id>", methods=["GET"])
def get_single_record(collection, record_id):
    if collection not in ALLOWED_COLLECTIONS:
        return json_error("Unknown collection", 404)

    try:
        records = list_records(collection)

        for record in records:
            if str(record.get("id")) == str(record_id):
                return jsonify({
                    "success": True,
                    "data": record,
                })

        return json_error("Record not found", 404)

    except Exception:
        app.logger.exception(
            "Failed to read %s record %s",
            collection,
            record_id,
        )
        return json_error("Unable to read record", 500)


# =========================================================
# TEMPORARY DATA DIAGNOSTICS
# Open /api/debug-data to verify deployed JSON files.
# Remove this endpoint after troubleshooting.
# =========================================================

@app.route("/api/debug-data", methods=["GET"])
def debug_data():
    result = {}

    for name in ("books", "shops", "media"):
        path = DATA_DIR / f"{name}.json"

        try:
            with path.open("r", encoding="utf-8-sig") as file:
                data = json.load(file)

            if not isinstance(data, list):
                result[name] = {
                    "exists": True,
                    "valid_json": True,
                    "valid_structure": False,
                    "error": "JSON root must be an array",
                }
                continue

            result[name] = {
                "exists": True,
                "valid_json": True,
                "valid_structure": all(
                    isinstance(item, dict) for item in data
                ),
                "count": len(data),
            }

        except Exception as exc:
            result[name] = {
                "exists": path.is_file(),
                "error": f"{type(exc).__name__}: {exc}",
            }

    return jsonify(result)


# =========================================================
# READ-ONLY FILE ACCESS
# =========================================================

@app.route("/files/<path:filename>", methods=["GET"])
def uploaded_file(filename):
    return send_from_directory(
        str(UPLOAD_FOLDER),
        filename,
    )


@app.route("/download-price/<path:filename>", methods=["GET"])
def download_price(filename):
    safe_filename = secure_filename(filename)

    if not safe_filename or safe_filename != filename:
        return "Invalid filename", 400

    file_path = PRICE_FOLDER / safe_filename

    if not file_path.is_file():
        return "File not found", 404

    return send_from_directory(
        str(PRICE_FOLDER),
        safe_filename,
        as_attachment=True,
    )


# =========================================================
# LOCAL DEVELOPMENT
# Vercel imports the Flask app directly.
# =========================================================

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 8000)),
        debug=False,
    )
