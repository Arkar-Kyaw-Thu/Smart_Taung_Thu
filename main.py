
import os
import json
import re
from pathlib import Path

from flask import (
    Flask,
    render_template,
    send_from_directory,
    jsonify,
)
from werkzeug.utils import secure_filename


# --------------------------------------------------
# PATHS AND APP CONFIGURATION
# --------------------------------------------------

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

PUBLIC_DATA_DIR = Path(BASE_DIR) / "public" / "data"

if os.environ.get("VERCEL") == "1":
    UPLOAD_FOLDER = "/tmp/uploads"
else:
    UPLOAD_FOLDER = os.path.join(
        BASE_DIR, "public", "uploads"
    )

PRICE_FOLDER = os.path.join(UPLOAD_FOLDER, "price")

app = Flask(
    __name__,
    template_folder=os.path.join(BASE_DIR, "templates"),
    static_folder=os.path.join(BASE_DIR, "static"),
)

app.secret_key = os.environ.get("SECRET_KEY", "change-this-secret-key")

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024

app.json.ensure_ascii = False


# --------------------------------------------------
# READ-ONLY JSON STORAGE
# --------------------------------------------------

ALLOWED_COLLECTIONS = {
    "books": "books.json",
    "shops": "shops.json",
    "media": "media.json",
}


def load_records(collection):
    """public/data ထဲမှ JSON records များကို ဖတ်သည်။"""

    filename = ALLOWED_COLLECTIONS.get(collection)

    if filename is None:
        raise ValueError("Unknown data collection")

    file_path = PUBLIC_DATA_DIR / filename

    with file_path.open("r", encoding="utf-8") as file:
        records = json.load(file)

    if not isinstance(records, list):
        raise ValueError(
            f"{filename} must contain a JSON list"
        )

    # Soft-deleted records များကို မပြပါ။
    return [
        record
        for record in records
        if isinstance(record, dict)
        and not record.get("delete_at")
    ]


# --------------------------------------------------
# HELPERS
# --------------------------------------------------

def extract_month_day(filename):
    """Excel filename မှ လနှင့်ရက်ကို ထုတ်ယူသည်။"""

    name_without_ext = os.path.splitext(filename)[0]

    match = re.search(
        r"([\u1000-\u109F]+လ_[\u1040-\u1049\d]+)",
        name_without_ext,
    )

    if match:
        return match.group(1).replace("_", " ")

    return name_without_ext


# --------------------------------------------------
# HOME / HEALTH CHECK
# --------------------------------------------------

@app.route("/")
def index():
    """Read-only Admin Dashboard."""

    try:
        books = load_records("books")
        shops = load_records("shops")
        media = load_records("media")

    except (OSError, ValueError, json.JSONDecodeError):
        app.logger.exception(
            "Unable to load dashboard JSON data"
        )
        return "Dashboard data ကို ဖတ်မရပါ။ JSON ဖိုင်များကို စစ်ဆေးပါ။", 500

    price_files = []

    if os.path.isdir(PRICE_FOLDER):
        try:
            for filename in os.listdir(PRICE_FOLDER):
                if filename.lower().endswith((".xlsx", ".xls")):
                    file_path = os.path.join(
                        PRICE_FOLDER, filename
                    )

                    if os.path.isfile(file_path):
                        price_files.append({
                            "raw_name": filename,
                            "display_name": extract_month_day(
                                filename
                            ),
                        })

        except OSError:
            app.logger.exception(
                "Unable to list market price files"
            )

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


@app.route("/api/health")
def health_check():
    return jsonify({
        "success": True,
        "status": "healthy",
        "read_only": True,
    })


# --------------------------------------------------
# FLUTTER READ-ONLY JSON API
# --------------------------------------------------

@app.route("/api/<collection>", methods=["GET"])
def flutter_read_data(collection):
    if collection not in ALLOWED_COLLECTIONS:
        return jsonify({
            "success": False,
            "message": "Data category not found",
        }), 404

    try:
        records = load_records(collection)

        return jsonify({
            "success": True,
            "count": len(records),
            "data": records,
        }), 200

    except FileNotFoundError:
        app.logger.warning(
            "JSON file not found for collection: %s",
            collection,
        )
        return jsonify({
            "success": False,
            "message": "JSON data file not found",
        }), 404

    except (json.JSONDecodeError, ValueError):
        app.logger.exception(
            "Invalid JSON data: %s", collection
        )
        return jsonify({
            "success": False,
            "message": "JSON data is invalid",
        }), 500

    except OSError:
        app.logger.exception(
            "Unable to read collection: %s", collection
        )
        return jsonify({
            "success": False,
            "message": "Unable to read data",
        }), 500


# --------------------------------------------------
# MARKET PRICE: READ / DOWNLOAD ONLY
# --------------------------------------------------

@app.route("/download-price/<path:filename>", methods=["GET"])
def download_price(filename):
    # Filename ကို ကန့်သတ်စစ်ဆေးသည်။
    safe_filename = secure_filename(filename)

    if not safe_filename or safe_filename != filename:
        return "Invalid filename", 400

    file_path = os.path.join(
        PRICE_FOLDER, safe_filename
    )

    if not os.path.isfile(file_path):
        return "File not found", 404

    return send_from_directory(
        PRICE_FOLDER,
        safe_filename,
        as_attachment=True,
    )


# --------------------------------------------------
# UPLOADED FILES: READ / DOWNLOAD ONLY
# --------------------------------------------------

@app.route("/files/<path:filename>", methods=["GET"])
def custom_static(filename):
    return send_from_directory(
        app.config["UPLOAD_FOLDER"],
        filename,
    )


# --------------------------------------------------
# LOCAL DEVELOPMENT
# --------------------------------------------------

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "8000")),
        debug=False,
    )
