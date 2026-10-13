
import json
from pathlib import Path
import re

from flask import (
    Flask,
    jsonify,
    render_template,
    send_from_directory,
    abort,
)

from storage import (
    BASE_DIR,
    DATA_DIR,
    UPLOAD_DIR,
    PRICE_DIR,
    BOOK_COVER_DIR,
    BOOK_PDF_DIR,
    JSON_FILES,
    list_records,
    get_record,
    data_status,
)

# --------------------------------------------------
# App configuration
# --------------------------------------------------

app = Flask(
    __name__,
    template_folder=str(BASE_DIR / "templates"),
    static_folder=str(BASE_DIR / "static"),
)

# Project folders:
#
# project/
# ├── data/
# │   ├── books.json
# │   ├── shops.json
# │   └── media.json
# ├── kb/
# ├── uploads/
# │   ├── price/
# │   ├── book_cover/
# │   └── book_pdf/
# ├── templates/
# │   └── index.html
# ├── static/
# ├── main.py
# ├── storage.py
# └── rag_service.py

UPLOAD_FOLDER = UPLOAD_DIR
PRICE_FOLDER = PRICE_DIR
BOOK_COVER_FOLDER = BOOK_COVER_DIR
BOOK_PDF_FOLDER = BOOK_PDF_DIR

ALLOWED_COLLECTIONS = {"books", "shops", "media"}
EXCEL_EXTENSIONS = {".xlsx", ".xls", ".xlsm"}


# --------------------------------------------------
# Read existing Excel files only
# Do not create folders or write files
# --------------------------------------------------


def get_price_files():
    if not PRICE_FOLDER.is_dir():
        return []

    files = []

    for file in PRICE_FOLDER.iterdir():
        if not file.is_file():
            continue

        if file.suffix.lower() not in EXCEL_EXTENSIONS:
            continue

        raw_name = file.name
        name = file.stem

        # ဖိုင်နာမည်ထဲက မြန်မာလနဲ့ ရက်ကိုသာ ရှာမယ်
        match = re.search(
            r"_(ဇန်နဝါရီလ|ဖေဖော်ဝါရီလ|မတ်လ|ဧပြီလ|မေလ|ဇွန်လ|ဇူလိုင်လ|ဩဂုတ်လ|စက်တင်ဘာလ|အောက်တိုဘာလ|နိုဝင်ဘာလ|ဒီဇင်ဘာလ)_(\d{2}|[၀-၉]{2})",
            name
        )

        if match:
            month = match.group(1)
            day = match.group(2)
            display_name = f"{month} {day} ရက်"
        else:
            # လနဲ့ရက် မတွေ့ရင် ဖိုင်နာမည်အပြည့် မပြပါနဲ့
            display_name = "ဈေးနှုန်းဖိုင်"

        files.append({
            "raw_name": raw_name,
            "display_name": display_name,
        })

    return sorted(files, key=lambda item: item["raw_name"], reverse=True)


# --------------------------------------------------
# Dashboard
# Requires templates/index.html
# --------------------------------------------------

@app.route("/", methods=["GET"])
def index():
    try:
        books = list_records("books")
        shops = list_records("shops")
        media = list_records("media")

        return render_template(
            "index.html",
            books=books,
            shops=shops,
            media=media,
            price_files=get_price_files(),
            read_only=True,
        )

    except Exception as exc:
        app.logger.exception("Dashboard data loading failed")

        return (
            f"Dashboard data error: "
            f"{type(exc).__name__}: {exc}",
            500,
        )


# --------------------------------------------------
# Health check
# GET /api/health
# --------------------------------------------------

@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({
        "status": "ok",
        "read_only": True,

        "base_directory": str(BASE_DIR),

        "data_directory": str(DATA_DIR),
        "data": data_status(),

        "upload_directory": str(UPLOAD_FOLDER),

        "price_directory": str(PRICE_FOLDER),
        "price_directory_exists": PRICE_FOLDER.is_dir(),
        "price_files": get_price_files(),

        "book_cover_directory": str(BOOK_COVER_FOLDER),
        "book_cover_directory_exists": (
            BOOK_COVER_FOLDER.is_dir()
        ),

        "book_pdf_directory": str(BOOK_PDF_FOLDER),
        "book_pdf_directory_exists": (
            BOOK_PDF_FOLDER.is_dir()
        ),
    })


# --------------------------------------------------
# Flutter API: list records
#
# GET /api/books
# GET /api/shops
# GET /api/media
# --------------------------------------------------

@app.route("/api/<collection>", methods=["GET"])
def api_list(collection):
    if collection not in ALLOWED_COLLECTIONS:
        return jsonify({
            "success": False,
            "error": "Unknown collection",
            "allowed": sorted(ALLOWED_COLLECTIONS),
        }), 404

    try:
        records = list_records(collection)

        return jsonify({
            "success": True,
            "count": len(records),
            "data": records,
        })

    except FileNotFoundError as exc:
        app.logger.error("Data file not found: %s", exc)

        return jsonify({
            "success": False,
            "error": str(exc),
        }), 500

    except (ValueError, json.JSONDecodeError) as exc:
        app.logger.error("Invalid JSON data: %s", exc)

        return jsonify({
            "success": False,
            "error": str(exc),
        }), 500

    except Exception:
        app.logger.exception("API list failed")

        return jsonify({
            "success": False,
            "error": "Internal server error",
        }), 500


# --------------------------------------------------
# Flutter API: get one record
#
# GET /api/books/1
# GET /api/shops/1
# GET /api/media/1
# --------------------------------------------------

@app.route("/api/<collection>/<record_id>", methods=["GET"])
def api_detail(collection, record_id):
    if collection not in ALLOWED_COLLECTIONS:
        return jsonify({
            "success": False,
            "error": "Unknown collection",
            "allowed": sorted(ALLOWED_COLLECTIONS),
        }), 404

    try:
        record = get_record(collection, record_id)

        if record is None:
            return jsonify({
                "success": False,
                "error": "Record not found",
            }), 404

        return jsonify({
            "success": True,
            "data": record,
        })

    except (FileNotFoundError, ValueError) as exc:
        app.logger.error("Record lookup failed: %s", exc)

        return jsonify({
            "success": False,
            "error": str(exc),
        }), 500

    except Exception:
        app.logger.exception("API detail failed")

        return jsonify({
            "success": False,
            "error": "Internal server error",
        }), 500


# --------------------------------------------------
# Serve existing uploaded files
#
# GET /files/price/example.xlsx
# GET /files/book_cover/example.png
# GET /files/book_pdf/example.pdf
#
# Files are served from uploads/
# --------------------------------------------------

@app.route("/files/<path:filename>", methods=["GET"])
def uploaded_file(filename):
    if not UPLOAD_FOLDER.is_dir():
        abort(404)

    return send_from_directory(
        str(UPLOAD_FOLDER),
        filename,
        as_attachment=False,
    )


# --------------------------------------------------
# Download existing Excel price files
#
# GET /download-price/prices.xlsx
# --------------------------------------------------

@app.route("/download-price/<path:filename>", methods=["GET"])
def download_price(filename):
    if Path(filename).suffix.lower() not in EXCEL_EXTENSIONS:
        abort(404)

    if not PRICE_FOLDER.is_dir():
        abort(404)

    return send_from_directory(
        str(PRICE_FOLDER),
        filename,
        as_attachment=True,
    )


# --------------------------------------------------
# Diagnostics: inspect expected project paths
#
# GET /api/debug-paths
# --------------------------------------------------

@app.route("/api/debug-paths", methods=["GET"])
def debug_paths():
    paths = [
        BASE_DIR / "data",
        BASE_DIR / "kb",
        BASE_DIR / "uploads",
        BASE_DIR / "uploads" / "price",
        BASE_DIR / "uploads" / "book_cover",
        BASE_DIR / "uploads" / "book_pdf",
        BASE_DIR / "templates",
        BASE_DIR / "static",
    ]

    checked = []

    for path in paths:
        exists = path.is_dir()

        checked.append({
            "path": str(path),
            "exists": exists,
            "files": (
                sorted(
                    item.name
                    for item in path.iterdir()
                    if item.is_file()
                )
                if exists
                else []
            ),
        })

    return jsonify({
        "base_directory": str(BASE_DIR),
        "main_file": str(Path(__file__).resolve()),

        "expected_data_directory": str(DATA_DIR),
        "data_status": data_status(),

        "upload_directory": str(UPLOAD_FOLDER),
        "upload_directory_exists": UPLOAD_FOLDER.is_dir(),

        "price_directory": str(PRICE_FOLDER),
        "price_directory_exists": PRICE_FOLDER.is_dir(),
        "price_files": get_price_files(),

        "book_cover_directory": str(BOOK_COVER_FOLDER),
        "book_pdf_directory": str(BOOK_PDF_FOLDER),

        "checked_directories": checked,
        "read_only": True,
    })


# --------------------------------------------------
# Run locally
#
# python main.py
#
# Local URL: http://127.0.0.1:5000
# Vercel can import the app object above,
# provided the deployment entry point is configured.
# --------------------------------------------------

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=5000,
        debug=False,
    )
