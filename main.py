
import logging
import re
import os
from pathlib import Path
from urllib.parse import unquote

from flask import (
    Flask,
    jsonify,
    render_template,
    request,
    send_from_directory,
    abort,
    url_for,
    redirect,
)
from werkzeug.utils import secure_filename

from service.price_service import MarketPriceService
from storage import (
    BASE_DIR,
    DATA_DIR,
    KB_DIR,
    UPLOAD_DIR,
    PRICE_DIR,
    BOOK_COVER_DIR,
    BOOK_FILE_DIR,
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

# NEW: Chat/RAG service
from service.rag_service import RAGService


# =========================================================
# Flask Configuration
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
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
BOOK_EXTENSIONS = {".pdf", ".epub"}


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


def validate_collection(collection):
    return (
        collection in ALLOWED_COLLECTIONS
        and collection in JSON_FILES
    )


def get_price_files():
    """Excel ဖိုင်နာမည်မှ မြန်မာလနှင့် ရက်ကို ထုတ်ယူမည်။"""

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

        match = re.search(
            rf"{month_pattern}[_\s-]*([၀-၉0-9]{{1,2}})_*$",
            stem,
        )

        if match:
            month = match.group(1)
            day = match.group(2)

            day = day.translate(
                str.maketrans("0123456789", "၀၁၂၃၄၅၆၇၈၉")
            )

            if len(day) == 1:
                day = "၀" + day

            display_name = f"{month} {day} ရက်"
        else:
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


def save_uploaded_file(upload, target_dir, allowed_extensions):
    """
    Upload ဖိုင်ကို သတ်မှတ်ထားသော folder ထဲ သိမ်းမည်။
    သိမ်းထားသော filename ကိုသာ ပြန်ပေးမည်။
    """

    if upload is None or not upload.filename:
        return None

    original_name = upload.filename
    extension = Path(original_name).suffix.lower()

    if extension not in allowed_extensions:
        raise ValueError(
            f"Unsupported file type: {extension or 'unknown'}"
        )

    filename = secure_filename(original_name)

    if not filename:
        raise ValueError("Invalid filename.")

    target_dir = Path(target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)

    destination = target_dir / filename

    if destination.exists():
        stem = Path(filename).stem
        suffix = Path(filename).suffix
        counter = 1

        while destination.exists():
            filename = f"{stem}_{counter}{suffix}"
            destination = target_dir / filename
            counter += 1

    upload.save(str(destination))

    return filename


def uploaded_relative_path(folder_name, filename):
    """ /files/<folder>/<filename> အတွက် relative path ပြန်ပေးမည်။"""
    if not filename:
        return None

    return f"{folder_name}/{filename}"


def render_add_page(page_type):
    """သက်ဆိုင်ရာ HTML template ကို ဖွင့်မည်။"""

    templates = {
        "book": "add_book.html",
        "shop": "add_shop.html",
        "media": "add_media.html",
    }

    template_name = templates.get(page_type)

    if template_name is None:
        abort(404)

    template_path = BASE_DIR / "templates" / template_name

    if not template_path.is_file():
        logger.error("Template not found: %s", template_path)
        abort(404)

    return render_template(template_name)


# =========================================================
# Dashboard
# GET /
# =========================================================

@app.route("/", methods=["GET"])
def index():
    status = data_status()

    books = list_records("books")
    shops = list_records("shops")
    media = list_records("media")

    return render_template(
        "index.html",
        price_files=get_price_files(),
        data_status=status,
        books=books,
        shops=shops,
        media=media,
        books_count=len(books),
        shops_count=len(shops),
        media_count=len(media),
    )


# =========================================================
# Add Book
# GET /add-book
# POST /add-book
# Also supports /add_book
# =========================================================

@app.route(
    "/add-book",
    methods=["GET", "POST"],
    endpoint="add_book",
)
@app.route("/add_book", methods=["GET", "POST"])
def add_book():
    if request.method == "GET":
        return render_add_page("book")

    name = request.form.get("name", "").strip()

    if not name:
        return "စာအုပ်အမည် ထည့်ပေးပါ။", 400

    image_name = None
    book_filename = None

    try:
        image_name = save_uploaded_file(
            request.files.get("image"),
            BOOK_COVER_DIR,
            IMAGE_EXTENSIONS,
        )

        book_filename = save_uploaded_file(
            request.files.get("file"),
            BOOK_FILE_DIR,
            BOOK_EXTENSIONS,
        )

        record = {
            "name": name,
            "image": uploaded_relative_path(
                "book_cover",
                image_name,
            ),
            "file": uploaded_relative_path(
                "book_file",
                book_filename,
            ),
        }

        create_record("books", record)

        logger.info("Book created: %s", name)

        return redirect(url_for("index"))

    except ValueError as exc:
        return str(exc), 400

    except (OSError, TypeError):
        logger.exception("Could not add book")
        return "စာအုပ်သိမ်းဆည်းရာတွင် အမှားဖြစ်နေပါသည်။", 500


# =========================================================
# Add Shop
# GET /add-shop
# POST /add-shop
# Also supports /add_shop
# =========================================================

@app.route(
    "/add-shop",
    methods=["GET", "POST"],
    endpoint="add_shop",
)
@app.route("/add_shop", methods=["GET", "POST"])
def add_shop():
    if request.method == "GET":
        return render_add_page("shop")

    data = {
        key: value.strip()
        for key, value in request.form.items()
    }

    if not any(data.values()):
        return "ဆိုင်အချက်အလက် ထည့်ပေးပါ။", 400

    try:
        create_record("shops", data)

        logger.info("Shop created")

        return redirect(url_for("index") + "#shops")

    except ValueError as exc:
        return str(exc), 400

    except (OSError, TypeError):
        logger.exception("Could not add shop")
        return "ဆိုင်အချက်အလက် သိမ်းဆည်းရာတွင် အမှားဖြစ်နေပါသည်။", 500


# =========================================================
# Add Media
# GET /add-media
# POST /add-media
# Also supports /add_media
# =========================================================

@app.route(
    "/add-media",
    methods=["GET", "POST"],
    endpoint="add_media",
)
@app.route("/add_media", methods=["GET", "POST"])
def add_media():
    if request.method == "GET":
        return render_add_page("media")

    data = {
        key: value.strip()
        for key, value in request.form.items()
    }

    if not any(data.values()):
        return "Media အချက်အလက် ထည့်ပေးပါ။", 400

    try:
        create_record("media", data)

        logger.info("Media record created")

        return redirect(url_for("index") + "#media")

    except ValueError as exc:
        return str(exc), 400

    except (OSError, TypeError):
        logger.exception("Could not add media")
        return "Media အချက်အလက် သိမ်းဆည်းရာတွင် အမှားဖြစ်နေပါသည်။", 500


# =========================================================
# Chat / RAG API
# POST /api/chat
# NEW: This route is added without changing existing routes.
# =========================================================

@app.route("/api/chat", methods=["POST"])
def api_chat():
    data = get_request_data()

    if data is None:
        return error_response(
            "Request body must be a valid JSON object.",
            400,
        )

    user_query = (
        data.get("user_query")
        or data.get("userQuery")
        or data.get("message")
        or ""
    )

    if not isinstance(user_query, str) or not user_query.strip():
        return error_response(
            "Please provide a non-empty user_query.",
            400,
        )

    try:
        answer = RAGService.answer_query(user_query.strip())

        if answer is None:
            answer = ""

        return jsonify({
            "success": True,
            "answer": str(answer),
        })

    except Exception:
        logger.exception("Chat/RAG request failed")
        return error_response(
            "Could not generate an answer.",
            500,
        )


# =========================================================
# Health Check
# GET /api/health
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
# READ: List Records
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

    except (ValueError, OSError):
        logger.exception("Could not read collection %s", collection)
        return error_response("Could not read records.", 500)


# =========================================================
# CREATE: Add Record through JSON API
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
# READ: Get One Record
# GET /api/books/<record_id>
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

    except (ValueError, OSError):
        logger.exception("Could not get record")
        return error_response("Could not retrieve record.", 500)


# =========================================================
# UPDATE: Edit Record
# PUT /api/books/<record_id>
# PATCH /api/books/<record_id>
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
        record = update_record(collection, record_id, data)

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
# DELETE: Soft Delete Record
# DELETE /api/books/<record_id>
# =========================================================

@app.route(
    "/api/<collection>/<record_id>",
    methods=["DELETE"],
)
def api_delete_record(collection, record_id):
    if not validate_collection(collection):
        return error_response("Collection not found.", 404)

    try:
        deleted = delete_record(collection, record_id)

        if not deleted:
            return error_response("Record not found.", 404)

        return jsonify({
            "success": True,
            "message": "Record soft-deleted successfully.",
            "id": record_id,
        })

    except (ValueError, OSError):
        logger.exception("Could not delete record")
        return error_response("Could not delete record.", 500)


# =========================================================
# RESTORE: Restore Deleted Record
# POST /api/books/<record_id>/restore
# =========================================================

@app.route(
    "/api/<collection>/<record_id>/restore",
    methods=["POST"],
)
def api_restore_record(collection, record_id):
    if not validate_collection(collection):
        return error_response("Collection not found.", 404)

    try:
        restored = restore_record(collection, record_id)

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

    except (ValueError, OSError):
        logger.exception("Could not restore record")
        return error_response("Could not restore record.", 500)


# =========================================================
# Market Price: Download Excel
# GET /download-price/<filename>
# =========================================================

@app.route(
    "/download-price/<path:filename>",
    methods=["GET"],
)
def download_price(filename):
    decoded_name = unquote(filename)

    safe_name = Path(decoded_name).name

    if safe_name != decoded_name:
        abort(404)

    if Path(safe_name).suffix.lower() not in EXCEL_EXTENSIONS:
        abort(404)

    file_path = PRICE_DIR / safe_name

    if not file_path.is_file():
        logger.warning(
            "Price file not found: %s",
            safe_name,
        )
        abort(404)

    return send_from_directory(
        str(PRICE_DIR),
        safe_name,
        as_attachment=True,
    )


# =========================================================
# Market Price: Refresh from Wisarra
# POST /api/refresh-price
# =========================================================

@app.route("/api/refresh-price", methods=["POST"])
def refresh_price():
    try:
        filepath, filename = MarketPriceService.fetch_and_save_excel()

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

    except Exception as e:
        logger.exception("Market price refresh failed")
        return jsonify({
            "success": False,
            "message": "Market price refresh failed.",
            "debug_error": str(e),
        }), 500


# =========================================================
# YouTube Media Preview API
# POST /fetch-youtube-preview
# POST /save-youtube-media
# POST /save-batch-youtube-media
# =========================================================

@app.route("/fetch-youtube-preview", methods=["POST"])
def fetch_youtube_preview():
    try:
        videos = MediaService.preview_youtube_videos(
            limit_per_channel=100
        )

        return jsonify({
            "success": True,
            "message": f"{len(videos)} videos found.",
            "videos": videos,
        })

    except Exception as exc:
        logger.exception("YouTube preview failed")

        return jsonify({
            "success": False,
            "message": "YouTube scraping failed.",
            "debug_error": str(exc),
            "videos": [],
        }), 500


@app.route("/save-youtube-media", methods=["POST"])
def save_youtube_media():
    data = get_request_data()

    if data is None:
        return error_response(
            "Request body must be a valid JSON object.",
            400,
        )

    description = data.get("description", "")
    link = data.get("link", "")
    media_type = data.get("type", "knowledge")

    if media_type not in {"news", "knowledge"}:
        return error_response("Invalid media type.", 400)

    try:
        result = MediaService.save_media_from_preview(
            description=description,
            link=link,
            media_type=media_type,
        )

        return jsonify({
            "success": True,
            "message": result.get(
                "message",
                "Media saved successfully."
            ),
            "already_exists": result.get(
                "already_exists", False
            ),
            "data": result.get("media"),
        })

    except ValueError as exc:
        return error_response(str(exc), 400)

    except Exception:
        logger.exception("Could not save YouTube media")

        return error_response(
            "Could not save YouTube media.",
            500,
        )


@app.route("/save-batch-youtube-media", methods=["POST"])
def save_batch_youtube_media():
    data = get_request_data()

    if data is None:
        return error_response(
            "Request body must be a valid JSON object.",
            400,
        )

    items = data.get("items")

    if not isinstance(items, list):
        return error_response(
            "'items' must be a list.",
            400,
        )

    if len(items) > 200:
        return error_response(
            "A maximum of 200 items can be saved at once.",
            400,
        )

    saved = 0
    skipped = 0
    failed = []

    for index, item in enumerate(items):
        if not isinstance(item, dict):
            failed.append({
                "index": index,
                "message": "Invalid item format.",
            })
            continue

        media_type = item.get("type", "knowledge")

        if media_type not in {"news", "knowledge"}:
            failed.append({
                "index": index,
                "message": "Invalid media type.",
            })
            continue

        try:
            result = MediaService.save_media_from_preview(
                description=item.get("description", ""),
                link=item.get("link", ""),
                media_type=media_type,
            )

            if result.get("already_exists"):
                skipped += 1
            else:
                saved += 1

        except (ValueError, OSError) as exc:
            failed.append({
                "index": index,
                "message": str(exc),
            })

        except Exception:
            logger.exception(
                "Batch YouTube save failed at index %s",
                index,
            )
            failed.append({
                "index": index,
                "message": "Could not save this item.",
            })

    success = len(failed) == 0

    return jsonify({
        "success": success,
        "message": (
            f"Saved: {saved}, already existed: {skipped}, "
            f"failed: {len(failed)}."
        ),
        "saved": saved,
        "skipped": skipped,
        "failed_count": len(failed),
        "errors": failed,
    }), (200 if success else 207)


# =========================================================
# Uploaded Files
# GET /files/book_cover/<filename>
# GET /files/book_file/<filename>
# =========================================================

@app.route("/files/<path:filename>", methods=["GET"])
def uploaded_file(filename):
    try:
        decoded_name = unquote(filename)

        root = UPLOAD_DIR.resolve()
        file_path = (root / decoded_name).resolve()

        if not file_path.is_relative_to(root):
            logger.warning("Invalid file path: %s", decoded_name)
            abort(404)

        if not file_path.is_file():
            logger.warning(
                "Uploaded file not found: requested=%r, resolved=%s",
                decoded_name,
                file_path,
            )
            abort(404)

        logger.info("Serving uploaded file: %s", file_path)

        return send_from_directory(
            str(file_path.parent),
            file_path.name,
            as_attachment=False,
        )

    except (OSError, ValueError):
        logger.exception("Error serving uploaded file: %s", filename)
        abort(404)


# =========================================================
# Debug Paths
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
        "book_file": BOOK_FILE_DIR,
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

        "book_cover_files": (
            sorted(
                file.name
                for file in BOOK_COVER_DIR.iterdir()
                if file.is_file()
            )
            if BOOK_COVER_DIR.is_dir()
            else []
        ),
        "book_file_files": (
            sorted(
                file.name
                for file in BOOK_FILE_DIR.iterdir()
                if file.is_file()
            )
            if BOOK_FILE_DIR.is_dir()
            else []
        ),
    })


# =========================================================
# Error Handlers
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
# Run Server
# =========================================================

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=5000,
        debug=True,
    )
