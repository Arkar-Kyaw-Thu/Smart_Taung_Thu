
import json
import logging
from pathlib import Path

from flask import Flask, jsonify

app = Flask(__name__)
app.json.ensure_ascii = False

logging.basicConfig(level=logging.INFO)

# --------------------------------------------------
# DATA DIRECTORY
# --------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent
PUBLIC_DATA_DIR = BASE_DIR / "public" / "data"

# Flutter can read only these JSON files.
ALLOWED_COLLECTIONS = {
    "books": "books.json",
    "shops": "shops.json",
    "media": "media.json",
}


# --------------------------------------------------
# HEALTH CHECK
# --------------------------------------------------

@app.get("/")
def home():
    return jsonify({
        "success": True,
        "message": "Flask API is running",
        "read_only": True,
        "endpoints": [
            "/api/books",
            "/api/shops",
            "/api/media",
        ],
    })


@app.get("/api/health")
def health_check():
    return jsonify({
        "success": True,
        "status": "healthy",
    })


# --------------------------------------------------
# FLUTTER READ-ONLY JSON API
# --------------------------------------------------

@app.get("/api/<collection>")
def flutter_read_data(collection):
    filename = ALLOWED_COLLECTIONS.get(collection)

    # Only the allowed collections can be accessed.
    if filename is None:
        return jsonify({
            "success": False,
            "message": "Data category not found",
        }), 404

    file_path = PUBLIC_DATA_DIR / filename

    try:
        with file_path.open("r", encoding="utf-8") as file:
            records = json.load(file)

        # This API expects each JSON file to contain a list.
        if not isinstance(records, list):
            app.logger.error(
                "Expected a JSON list in %s", filename
            )
            return jsonify({
                "success": False,
                "message": "JSON data must be a list",
            }), 500

        # Exclude soft-deleted records.
        visible_records = [
            record
            for record in records
            if isinstance(record, dict)
            and not record.get("delete_at")
        ]

        return jsonify({
            "success": True,
            "count": len(visible_records),
            "data": visible_records,
        }), 200

    except FileNotFoundError:
        app.logger.warning(
            "JSON file not found: %s", file_path
        )
        return jsonify({
            "success": False,
            "message": f"{filename} not found",
        }), 404

    except json.JSONDecodeError:
        app.logger.exception(
            "Invalid JSON in %s", filename
        )
        return jsonify({
            "success": False,
            "message": "JSON data is invalid",
        }), 500

    except OSError:
        app.logger.exception(
            "Unable to read %s", filename
        )
        return jsonify({
            "success": False,
            "message": "Unable to read data",
        }), 500


# --------------------------------------------------
# OPTIONAL: LOCAL DEVELOPMENT
# Vercel serves the app through its Python runtime.
# --------------------------------------------------

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=5000,
        debug=False,
    )
