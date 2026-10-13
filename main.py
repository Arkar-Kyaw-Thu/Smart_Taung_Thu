
import os
import re

from flask import (
    Flask,
    jsonify,
    render_template,
    send_from_directory,
)
from werkzeug.utils import secure_filename

from storage import list_records


# --------------------------------------------------
# APP CONFIGURATION
# --------------------------------------------------

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

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

app.secret_key = os.environ.get(
    "SECRET_KEY",
    "change-this-secret-key-before-deployment",
)

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.json.ensure_ascii = False


# Only these collections are exposed to Flutter.
ALLOWED_COLLECTIONS = {"books", "shops", "media"}


# --------------------------------------------------
# HELPERS
# --------------------------------------------------

def extract_month_day(filename):
    """Extract month/day display text from Excel filename."""
    name_without_ext = os.path.splitext(filename)[0]

    match = re.search(
        r"([\u1000-\u109F]+လ_[\u1040-\u1049\d]+)",
        name_without_ext,
    )

    if match:
        return match.group(1).replace("_", " ")

    return name_without_ext


def error_response(message, status=500):
    return jsonify({
        "success": False,
        "message": message,
    }), status


# --------------------------------------------------
# HOME / READ-ONLY DASHBOARD
# --------------------------------------------------

@app.route("/", methods=["GET"])
def index():
    try:
        books = list_records("books")
        shops = list_records("shops")
        media = list_records("media")

    except Exception:
        app.logger.exception(
            "Unable to load dashboard data"
        )
        return (
            "Dashboard data ကို ဖတ်မရပါ။ "
            "Vercel Logs ကို စစ်ဆေးပါ။",
            500,
        )

    price_files = []

    if os.path.isdir(PRICE_FOLDER):
        try:
            for filename in os.listdir(PRICE_FOLDER):
                if not filename.lower().endswith(
                    (".xlsx", ".xls")
                ):
                    continue

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
                "Unable to list price files"
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


# --------------------------------------------------
# HEALTH CHECK
# --------------------------------------------------

@app.route("/api/health", methods=["GET"])
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
        return error_response(
            "Data category not found",
            404,
        )

    try:
        records = list_records(collection)

        return jsonify({
            "success": True,
            "count": len(records),
            "data": records,
        }), 200

    except FileNotFoundError:
        app.logger.exception(
            "Missing JSON file for %s", collection
        )
        return error_response(
            f"{collection}.json not found",
            404,
        )

    except ValueError:
        app.logger.exception(
            "Invalid JSON data for %s", collection
        )
        return error_response(
            f"{collection}.json is invalid",
            500,
        )

    except OSError:
        app.logger.exception(
            "Unable to read %s", collection
        )
        return error_response(
            "Unable to read data",
            500,
        )

    except Exception:
        app.logger.exception(
            "Unexpected API error for %s", collection
        )
        return error_response(
            "Internal server error",
            500,
        )


# --------------------------------------------------
# READ-ONLY EXCEL DOWNLOAD
# --------------------------------------------------

@app.route(
    "/download-price/<path:filename>",
    methods=["GET"],
)
def download_price(filename):
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
# READ-ONLY UPLOADED FILE ACCESS
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
