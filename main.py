
import logging
import re
from pathlib import Path

from flask import (
    Flask,
    jsonify,
    render_template,
    request,
    send_from_directory,
    abort,
    url_for,
)

from storage import (
    BASE_DIR,
    DATA_DIR,
    KB_DIR,
    UPLOAD_DIR,
    PRICE_DIR,
    BOOK_COVER_DIR,
    BOOK_PDF_DIR,
    JSON_FILES,
    list_records,
    get_record,
    data_status,
    create_record,
    update_record,
    delete_record,
    restore_record,
)

from service.media_service import MediaService 


# =========================================================
# Flask configuration
# =========================================================

app = Flask(
    __name__,
    template_folder=str(BASE_DIR / "templates"),
    static_folder=str(BASE_DIR / "static"),
)

app.config["JSON_AS_ASCII"] = False
app.json.ensure_ascii = False

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

ALLOWED_COLLECTIONS = {"books", "shops", "media"}
EXCEL_EXTENSIONS = {".xlsx", ".xls", ".xlsm"}

# Database မသုံးပါ။ Data အားလုံးကို JSON ဖိုင်များတွင် သိမ်းမည်။
# Market price များကို uploads/price/ ထဲ Excel ဖိုင်အဖြစ် သိမ်းမည်။


# =========================================================
# Helpers
# =========================================================

def error_response(message, status_code=400):
    return jsonify({
        "success": False,
        "message": message,
    }), status_code


def get_request_data():
    """Request body မှ JSON object ကို ရယူမည်။"""

    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return None

    return data


def get_price_files():
    """
    uploads/price/ ထဲရှိ Excel ဖိုင်များကို ရှာမည်။

    Display:
        ဇူလိုင်လ ၀၈ ရက်

    Download:
        မူရင်းဖိုင်အမည်အတိုင်း download လုပ်မည်။
    """

    if not PRICE_DIR.is_dir():
        return []

    month_pattern = (
        r"(ဇန်နဝါရီလ|ဖေဖော်ဝါရီလ|မတ်လ|ဧပြီလ|မေလ|"
        r"ဇွန်လ|ဇူလိုင်လ|ဩဂုတ်လ|သြဂုတ်လ|စက်တင်ဘာလ|"
        r"အောက်တိုဘာလ|နိုဝင်ဘာလ|ဒီဇင်ဘာလ)"
    )

    files = []

    for file_path in PRICE_DIR.iterdir():
        if not file_path.is_file():
            continue

        if file_path.suffix.lower() not in EXCEL_EXTENSIONS:
            continue

        raw_name = file_path.name
        stem = file_path.stem

        # ဥပမာ:
        # 001_Market_Price_၂၀၂၆_ခုနှစ်_ဇူလိုင်လ_၀၈
        match = re.search(
            rf"{month_pattern}[_\s]+([၀-၉0-9]{{1,2}})\*?$",
            stem,
        )

        if match:
            month = match.group(1)
            day = match.group(2).translate(
                str.maketrans("0123456789", "၀၁၂၃၄၅၆၇၈၉")
            )

            if len(day) == 1:
                day = "၀" + day

            display_name = f"{month} {day} ရက်"
        else:
            # ရက်စွဲမတွေ့လျှင် ဖိုင်အမည်အပြည့် မပြပါ။
            display_name = "ဈေးနှုန်းဖိုင်"

        files.append({
            "raw_name": raw_name,
            "display_name": display_name,
        })

    return sorted(
        files,
        key=lambda item: item["raw_name"],
        reverse=True,
    )


def validate_collection(collection):
    if collection not in ALLOWED_COLLECTIONS:
        return False

    return collection in JSON_FILES


# =========================================================
# Dashboard
# =========================================================

@app.route("/")
def index():
    """Main dashboard."""

    price_files = get_price_files()
    status = data_status()

    return render_template(
        "index.html",
        price_files=price_files,
        data_status=status,
        books_count=status.get("books", {}).get("active_count", 0),
        shops_count=status.get("shops", {}).get("active_count", 0),
        media_count=status.get("media", {}).get("active_count", 0),
    )


# =========================================================
# Health check
# =========================================================

@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({
        "status": "ok",
        "storage": "json",
        "database": False,
        "base_directory": str(BASE_DIR),
        "data_directory": str(DATA_DIR),
        "kb_directory": str(KB_DIR),
        "upload_directory": str(UPLOAD_DIR),
        "price_directory": str(PRICE_DIR),
        "price_directory_exists": PRICE_DIR.is_dir(),
        "price_files": get_price_files(),
        "collections": data_status(),
    })


# =========================================================
# READ: List all records
# GET /api/books
# GET /api/shops
# GET /api/media
# =========================================================

@app.route("/api/<collection>", methods=["GET"])
def api_list_records(collection):
    if not validate_collection(collection):
        return error_response("Collection not found.", 404)

    include_deleted = (
        request.args.get("include_deleted", "false").lower()
        in {"true", "1", "yes"}
    )

    try:
        records = list_records(
            collection,
            include_deleted=include_deleted,
        )

        return jsonify({
            "success": True,
            "collection": collection,
            "count": len(records),
            "data": records,
        })

    except (ValueError, OSError) as exc:
        logger.exception("Could not read collection %s", collection)
        return error_response(str(exc), 500)


# =========================================================
# CREATE: Add a record
# POST /api/books
# POST /api/shops
# POST /api/media
# =========================================================

@app.route("/api/<collection>", methods=["POST"])
def api_create_record(collection):
    if not validate_collection(collection):
        return error_response("Collection not found.", 404)

    data = get_request_data()

    if data is None:
        return error_response(
            "Request body must be a valid JSON object.",
            400,
        )

    try:
        record = create_record(collection, data)

        return jsonify({
            "success": True,
            "message": "Record created successfully.",
            "data": record,
        }), 201

    except ValueError as exc:
        return error_response(str(exc), 400)

    except OSError:
        logger.exception("Could not create record in %s", collection)
        return error_response("Could not save the JSON file.", 500)


# =========================================================
# READ: Get one record
# GET /api/books/1
# GET /api/shops/1
# GET /api/media/1
# =========================================================

@app.route("/api/<collection>/<record_id>", methods=["GET"])
def api_get_record(collection, record_id):
    if not validate_collection(collection):
        return error_response("Collection not found.", 404)

    include_deleted = (
        request.args.get("include_deleted", "false").lower()
        in {"true", "1", "yes"}
    )

    try:
        record = get_record(
            collection,
            record_id,
            include_deleted=include_deleted,
        )

        if record is None:
            return error_response("Record not found.", 404)

        return jsonify({
            "success": True,
            "data": record,
        })

    except (ValueError, OSError) as exc:
        logger.exception("Could not get record")
        return error_response(str(exc), 500)


# =========================================================
# UPDATE: Edit a record
# PUT /api/books/1
# PUT /api/shops/1
# PUT /api/media/1
# =========================================================

@app.route(
    "/api/<collection>/<record_id>",
    methods=["PUT", "PATCH"],
)
def api_update_record(collection, record_id):
    if not validate_collection(collection):
        return error_response("Collection not found.", 404)

    data = get_request_data()

    if data is None:
        return error_response(
            "Request body must be a valid JSON object.",
            400,
        )

    try:
        record = update_record(
            collection,
            record_id,
            data,
        )

        if record is None:
            return error_response("Record not found.", 404)

        return jsonify({
            "success": True,
            "message": "Record updated successfully.",
            "data": record,
        })

    except ValueError as exc:
        return error_response(str(exc), 400)

    except OSError:
        logger.exception("Could not update record")
        return error_response("Could not save the JSON file.", 500)


# =========================================================
# DELETE: Soft delete a record
# DELETE /api/books/1
# DELETE /api/shops/1
# DELETE /api/media/1
# =========================================================

@app.route(
    "/api/<collection>/<record_id>",
    methods=["DELETE"],
)
def api_delete_record(collection, record_id):
    if not validate_collection(collection):
        return error_response("Collection not found.", 404)

    try:
        deleted = delete_record(
            collection,
            record_id,
        )

        if not deleted:
            return error_response("Record not found.", 404)

        return jsonify({
            "success": True,
            "message": "Record soft-deleted successfully.",
            "id": record_id,
        })

    except (ValueError, OSError) as exc:
        logger.exception("Could not delete record")
        return error_response(str(exc), 500)


# =========================================================
# RESTORE: Restore a soft-deleted record
# POST /api/books/1/restore
# POST /api/shops/1/restore
# POST /api/media/1/restore
# =========================================================

@app.route(
    "/api/<collection>/<record_id>/restore",
    methods=["POST"],
)
def api_restore_record(collection, record_id):
    if not validate_collection(collection):
        return error_response("Collection not found.", 404)

    try:
        restored = restore_record(
            collection,
            record_id,
        )

        if not restored:
            return error_response(
                "Deleted record not found.",
                404,
            )

        return jsonify({
            "success": True,
            "message": "Record restored successfully.",
            "id": record_id,
        })

    except (ValueError, OSError) as exc:
        logger.exception("Could not restore record")
        return error_response(str(exc), 500)


# =========================================================
# Market Price: Download Excel
# GET /download-price/<filename>
# =========================================================

@app.route("/download-price/<path:filename>", methods=["GET"])
def download_price(filename):
    if Path(filename).suffix.lower() not in EXCEL_EXTENSIONS:
        abort(404)

    if not (PRICE_DIR / filename).is_file():
        abort(404)

    return send_from_directory(
        str(PRICE_DIR),
        filename,
        as_attachment=True,
    )


# =========================================================
# Market Price: Refresh from Wisarra
# POST /api/refresh-price
# =========================================================

@app.route("/api/refresh-price", methods=["POST"])
def refresh_price():
    try:
        filepath, filename = (
            MediaService.fetch_and_save_excel()
        )

        if not filepath or not filename:
            return error_response(
                "Market price data could not be retrieved or saved.",
                502,
            )

        return jsonify({
            "success": True,
            "message": "Market price Excel file is ready.",
            "filename": filename,
            "download_url": url_for(
                "download_price",
                filename=filename,
            ),
        })

    except Exception:
        logger.exception("Market price refresh failed")
        return error_response(
            "Market price refresh failed.",
            500,
        )


# =========================================================
# Uploaded files
# GET /files/book_cover/book1.jpg
# GET /files/book_pdf/book1.pdf
# =========================================================

@app.route("/files/<path:filename>", methods=["GET"])
def uploaded_file(filename):
    file_path = UPLOAD_DIR / filename

    if not file_path.is_file():
        abort(404)

    return send_from_directory(
        str(UPLOAD_DIR),
        filename,
        as_attachment=False,
    )


# =========================================================
# Debug paths
# GET /api/debug-paths
# =========================================================

@app.route("/api/debug-paths", methods=["GET"])
def debug_paths():
    directories = {
        "project": BASE_DIR,
        "data": DATA_DIR,
        "kb": KB_DIR,
        "uploads": UPLOAD_DIR,
        "price": PRICE_DIR,
        "book_cover": BOOK_COVER_DIR,
        "book_pdf": BOOK_PDF_DIR,
        "templates": BASE_DIR / "templates",
        "static": BASE_DIR / "static",
    }

    return jsonify({
        "status": "ok",
        "paths": {
            name: {
                "path": str(path),
                "exists": path.exists(),
                "is_directory": path.is_dir(),
            }
            for name, path in directories.items()
        },
        "json_files": {
            name: {
                "path": str(path),
                "exists": path.exists(),
            }
            for name, path in JSON_FILES.items()
        },
        "price_files": get_price_files(),
    })


# =========================================================
# Error handlers
# =========================================================

@app.errorhandler(404)
def not_found(_error):
    if request.path.startswith("/api/"):
        return error_response("Resource not found.", 404)

    return "404 - Not Found", 404


@app.errorhandler(405)
def method_not_allowed(_error):
    if request.path.startswith("/api/"):
        return error_response("Method not allowed.", 405)

    return "405 - Method Not Allowed", 405


# =========================================================
# Run server
# =========================================================

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=5000,
        debug=True,
    )
