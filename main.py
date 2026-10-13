
import json
from pathlib import Path

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

PUBLIC_DIR = BASE_DIR / "public"
UPLOAD_FOLDER = PUBLIC_DIR / "uploads"
PRICE_FOLDER = UPLOAD_FOLDER / "price"

ALLOWED_COLLECTIONS = {"books", "shops", "media"}
EXCEL_EXTENSIONS = {".xlsx", ".xls", ".xlsm"}


# --------------------------------------------------
# Read existing Excel files only
# Do not create folders or write files
# --------------------------------------------------

def get_price_files():
    if not PRICE_FOLDER.is_dir():
        return []

    return sorted(
        file.name
        for file in PRICE_FOLDER.iterdir()
        if file.is_file()
        and file.suffix.lower() in EXCEL_EXTENSIONS
    )


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
# --------------------------------------------------

@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({
        "status": "ok",
        "read_only": True,
        "data_directory": str(DATA_DIR),
        "data": data_status(),
        "upload_directory": str(UPLOAD_FOLDER),
        "price_directory": str(PRICE_FOLDER),
        "price_directory_exists": PRICE_FOLDER.is_dir(),
        "price_files": get_price_files(),
    })


# --------------------------------------------------
# Flutter API: list records
# GET /api/books
# GET /api/shops
# GET /api/media
# --------------------------------------------------

@app.route("/api/<collection>", methods=["GET"])
def api_list(collection):
    if collection not in ALLOWED_COLLECTIONS:
        return jsonify({
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
        return jsonify({
            "success": False,
            "error": str(exc),
        }), 500

    except (ValueError, json.JSONDecodeError) as exc:
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
# GET /api/books/1
# GET /api/shops/1
# GET /api/media/1
# --------------------------------------------------

@app.route("/api/<collection>/<record_id>", methods=["GET"])
def api_detail(collection, record_id):
    if collection not in ALLOWED_COLLECTIONS:
        return jsonify({
            "error": "Unknown collection",
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
# Existing upload files
# Example: /files/book_cover/example.png
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
# Example: /download-price/prices.xlsx
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
# Diagnostics: inspect expected paths
# --------------------------------------------------

@app.route("/api/debug-paths", methods=["GET"])
def debug_paths():
    paths = [
        BASE_DIR / "data",
        BASE_DIR / "public" / "data",
        BASE_DIR.parent / "data",
        BASE_DIR.parent / "public" / "data",
    ]

    checked = []

    for path in paths:
        checked.append({
            "path": str(path),
            "exists": path.is_dir(),
            "files": (
                sorted(item.name for item in path.iterdir()
                       if item.is_file())
                if path.is_dir()
                else []
            ),
        })

    return jsonify({
        "base_directory": str(BASE_DIR),
        "expected_data_directory": str(DATA_DIR),
        "main_file": str(Path(__file__).resolve()),
        "checked_directories": checked,
        "data_status": data_status(),
        "upload_directory": str(UPLOAD_FOLDER),
        "upload_directory_exists": UPLOAD_FOLDER.is_dir(),
        "price_directory": str(PRICE_FOLDER),
        "price_directory_exists": PRICE_FOLDER.is_dir(),
        "price_files": get_price_files(),
    })


# --------------------------------------------------
# Run locally
# Vercel imports the app object above
# --------------------------------------------------

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
