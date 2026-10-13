
import os
import re
from flask import (
    Flask,
    request,
    render_template,
    send_from_directory,
    redirect,
    url_for,
    flash,
    jsonify,
)
from werkzeug.utils import secure_filename

from storage import (
    list_records,
    create_record,
    update_record,
    soft_delete_record,
)

from services.price_service import MarketPriceService
from services.media_service import MediaService



BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Vercel မှာ temporary writable directory ကို အသုံးပြုပါ
if os.environ.get("VERCEL") == "1":
    UPLOAD_FOLDER = "/tmp/uploads"
else:
    UPLOAD_FOLDER = os.path.join(BASE_DIR, "public", "uploads")

PRICE_FOLDER = os.path.join(UPLOAD_FOLDER, "price")

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(PRICE_FOLDER, exist_ok=True)


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
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024


# --------------------------------------------------
# HELPERS
# --------------------------------------------------

def extract_month_day(filename):
    """ဈေးနှုန်း Excel ဖိုင်အမည်မှ လနှင့်ရက်ကို ထုတ်ယူသည်။"""
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

def save_uploaded_file(file_key, target_folder):
    """Local development အတွက် upload ဖိုင်သိမ်းသည်။
    မြန်မာစာပါသော ဖိုင်အမည်များကို ထိန်းသိမ်းသည်။
    """
    uploaded_file = request.files.get(file_key)

    if not uploaded_file or not uploaded_file.filename:
        return ""

    original_name = uploaded_file.filename.replace("\\", "/")
    original_name = original_name.rsplit("/", 1)[-1].strip()

    if not original_name or original_name in (".", ".."):
        return ""

    # Filename ထဲက မသင့်လျော်သော control characters များကို စစ်ဆေးသည်။
    if any(ord(char) < 32 for char in original_name):
        return ""

    os.makedirs(target_folder, exist_ok=True)

    save_path = os.path.join(target_folder, original_name)
    uploaded_file.save(save_path)

    return original_name

# --------------------------------------------------
# ADMIN DASHBOARD
# --------------------------------------------------

@app.route("/")
def index():
    try:
        books = list_records("books")
        shops = list_records("shops")
        media = list_records("media")
    except Exception as exc:
        app.logger.exception("Unable to load dashboard data")
        return f"Dashboard data ကို ဖတ်မရပါ: {exc}", 500

    price_files = []

    if os.path.isdir(PRICE_FOLDER):
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
    )


# --------------------------------------------------
# MARKET PRICE
# --------------------------------------------------

@app.route("/fetch-market-price", methods=["POST"])
def fetch_market_price():
    try:
        result = MarketPriceService.fetch_and_save_excel()

        if isinstance(result, tuple):
            file_path = result[0]
            file_name = result[1]
            already_exists = result[2] if len(result) > 2 else False

        elif isinstance(result, dict):
            file_path = result.get("file_path")
            file_name = result.get("file_name")
            already_exists = result.get("already_exists", False)

        else:
            file_path = None
            file_name = None
            already_exists = False

        if already_exists:
            return jsonify({
                "success": True,
                "status": "exists",
                "message": "ယနေ့အတွက် ဒေတာများ ရှိပြီးသား ဖြစ်ပါသည်။",
            })

        if file_path:
            return jsonify({
                "success": True,
                "status": "created",
                "message": f"Excel ဖိုင်အသစ် ({file_name}) ကို ရယူပြီးပါပြီ။",
            })

        return json_error(
            "ဈေးနှုန်း ဒေတာများ ဆွဲယူ၍ မရရှိပါ။",
            502,
        )

    except Exception as exc:
        app.logger.exception("Market price fetch failed")
        return json_error(exc, 500)


@app.route("/download-price/<path:filename>")
def download_price(filename):
    # Path traversal ကို ကာကွယ်ရန် filename ကို စစ်ဆေးသည်။
    safe_filename = secure_filename(filename)

    if not safe_filename or safe_filename != filename:
        return "Invalid filename", 400

    file_path = os.path.join(PRICE_FOLDER, safe_filename)

    if not os.path.isfile(file_path):
        return "File not found", 404

    return send_from_directory(
        PRICE_FOLDER,
        safe_filename,
        as_attachment=True,
    )


# --------------------------------------------------
# YOUTUBE PREVIEW AND SAVE
# --------------------------------------------------

@app.route("/fetch-youtube-preview", methods=["POST"])
def fetch_youtube_preview():
    try:
        videos = MediaService.preview_youtube_videos(
            limit_per_channel=100
        )

        return jsonify({
            "success": True,
            "videos": videos,
        })

    except Exception as exc:
        app.logger.exception("YouTube preview failed")
        return json_error(exc, 500)


@app.route("/save-youtube-media", methods=["POST"])
def save_youtube_media():
    data = request.get_json(silent=True) or {}

    description = data.get("description")
    link = data.get("link")
    media_type = data.get("type", "news")

    if not link or not description:
        return json_error("အချက်အလက် မပြည့်စုံပါ။")

    try:
        # Service ကိုလည်း နောက်တစ်ဆင့်တွင် JSON storage
        # အသုံးပြုအောင် ပြောင်းရန် လိုအပ်သည်။
        MediaService.save_media_from_preview(
            description,
            link,
            media_type,
        )

        return jsonify({
            "success": True,
            "message": "Media ကို သိမ်းဆည်းပြီးပါပြီ!",
        })

    except Exception as exc:
        app.logger.exception("Saving YouTube media failed")
        return json_error(exc, 500)


@app.route("/save-batch-youtube-media", methods=["POST"])
def save_all_youtube_media():
    data = request.get_json(silent=True) or {}
    items = data.get("items", [])

    if not isinstance(items, list) or not items:
        return json_error("သိမ်းဆည်းရန် ဒေတာ မရှိပါ။")

    try:
        saved_count = 0

        for item in items:
            if not isinstance(item, dict):
                continue

            description = item.get("description")
            link = item.get("link")
            media_type = item.get("type", "news")

            if not description or not link:
                continue

            create_record("media", {
                "description": description,
                "link": link,
                "type": media_type,
            })

            saved_count += 1

        return jsonify({
            "success": True,
            "message": (
                f"ဗီဒီယို စုစုပေါင်း ({saved_count}) ခု "
                "ကို သိမ်းဆည်းပြီးပါပြီ!"
            ),
        })

    except Exception as exc:
        app.logger.exception("Batch media save failed")
        return json_error(exc, 500)


# --------------------------------------------------
# ADD BOOK
# --------------------------------------------------

@app.route("/add-book", methods=["GET", "POST"])
def add_book():
    if request.method == "POST":
        cover_folder = os.path.join(
            app.config["UPLOAD_FOLDER"],
            "book_cover",
        )

        file_folder = os.path.join(
            app.config["UPLOAD_FOLDER"],
            "book_file",
        )

        image_name = save_uploaded_file("image", cover_folder)
        file_name = save_uploaded_file("file", file_folder)

        name = (request.form.get("name") or "").strip()

        if not name and file_name:
            name = os.path.splitext(file_name)[0]

        if not name:
            flash("စာအုပ်အမည် ထည့်သွင်းရန် လိုအပ်ပါသည်။", "error")
            return redirect(url_for("add_book"))

        create_record("books", {
            "name": name,
            "image_path": f"book_cover/{image_name}" if image_name else "",
            "file_path": f"book_file/{file_name}" if file_name else "",
        })

        flash("စာအုပ်အသစ် ထည့်သွင်းပြီးပါပြီ!", "success")
        return redirect(url_for("index") + "#library-tab")

    return render_template("add_book.html")


# --------------------------------------------------
# ADD SHOP
# --------------------------------------------------

@app.route("/add-shop", methods=["GET", "POST"])
def add_shop():
    if request.method == "POST":
        name = (request.form.get("name") or "").strip()

        if not name:
            flash("ဆိုင်အမည် ထည့်သွင်းရန် လိုအပ်ပါသည်။", "error")
            return redirect(url_for("add_shop"))

        create_record("shops", {
            "name": name,
            "address": request.form.get("address", ""),
            "phone": request.form.get("phone", ""),
            "type": request.form.get("type", ""),
            "latitude": request.form.get("latitude") or 0.0,
            "longitude": request.form.get("longitude") or 0.0,
        })

        flash("ဆိုင်အသစ် ထည့်သွင်းပြီးပါပြီ!", "success")
        return redirect(url_for("index") + "#shop-tab")

    return render_template("add_shop.html")


# --------------------------------------------------
# ADD MEDIA
# --------------------------------------------------

@app.route("/add-media", methods=["GET", "POST"])
def add_media():
    if request.method == "POST":
        description = request.form.get("description", "")
        link = (request.form.get("link") or "").strip()
        media_type = request.form.get("type") or "news"

        if not link:
            flash("Link ထည့်သွင်းရန် လိုအပ်ပါသည်။", "error")
            return redirect(url_for("add_media"))

        create_record("media", {
            "description": description,
            "link": link,
            "type": media_type,
        })

        flash("Media အသစ် ထည့်သွင်းပြီးပါပြီ!", "success")
        return redirect(url_for("index") + "#media-tab")

    return render_template("add_media.html")


# --------------------------------------------------
# EDIT BOOK
# --------------------------------------------------

@app.route("/edit-book", methods=["POST"])
def edit_book():
    book_id = request.form.get("id")
    name = (request.form.get("name") or "").strip()

    if not book_id or not name:
        flash("စာအုပ်အချက်အလက် မပြည့်စုံပါ။", "error")
        return redirect(url_for("index") + "#library-tab")

    updated = update_record(
        "books",
        book_id,
        {"name": name},
    )

    flash(
        "စာအုပ်အချက်အလက် ပြင်ဆင်ပြီးပါပြီ!"
        if updated else "စာအုပ်ကို ရှာမတွေ့ပါ။",
        "success" if updated else "error",
    )

    return redirect(url_for("index") + "#library-tab")


# --------------------------------------------------
# EDIT SHOP
# --------------------------------------------------

@app.route("/edit-shop", methods=["POST"])
def edit_shop():
    shop_id = request.form.get("id")

    if not shop_id:
        flash("ဆိုင် ID မရှိပါ။", "error")
        return redirect(url_for("index") + "#shop-tab")

    updated = update_record(
        "shops",
        shop_id,
        {
            "name": request.form.get("name", ""),
            "type": request.form.get("type", ""),
            "phone": request.form.get("phone", ""),
            "address": request.form.get("address", ""),
            "latitude": request.form.get("latitude") or 0.0,
            "longitude": request.form.get("longitude") or 0.0,
        },
    )

    flash(
        "ဆိုင်အချက်အလက် ပြင်ဆင်ပြီးပါပြီ!"
        if updated else "ဆိုင်ကို ရှာမတွေ့ပါ။",
        "success" if updated else "error",
    )

    return redirect(url_for("index") + "#shop-tab")


# --------------------------------------------------
# EDIT MEDIA
# --------------------------------------------------

@app.route("/edit-media", methods=["POST"])
def edit_media():
    media_id = request.form.get("id")

    if not media_id:
        flash("Media ID မရှိပါ။", "error")
        return redirect(url_for("index") + "#media-tab")

    updated = update_record(
        "media",
        media_id,
        {
            "description": request.form.get("description", ""),
            "link": request.form.get("link", ""),
            "type": request.form.get("type", "news"),
        },
    )

    flash(
        "Media ပြင်ဆင်ပြီးပါပြီ!"
        if updated else "Media ကို ရှာမတွေ့ပါ။",
        "success" if updated else "error",
    )

    return redirect(url_for("index") + "#media-tab")


# --------------------------------------------------
# SOFT DELETE
# --------------------------------------------------

@app.route("/delete-book/<int:book_id>", methods=["GET", "POST"])
def delete_book(book_id):
    deleted = soft_delete_record("books", book_id)

    flash(
        "စာအုပ်ကို ဖျက်လိုက်ပါပြီ!"
        if deleted else "စာအုပ်ကို ရှာမတွေ့ပါ။",
        "info" if deleted else "error",
    )

    return redirect(url_for("index") + "#library-tab")


@app.route("/delete-shop/<int:shop_id>", methods=["GET", "POST"])
def delete_shop(shop_id):
    deleted = soft_delete_record("shops", shop_id)

    flash(
        "ဆိုင်ကို ဖျက်လိုက်ပါပြီ!"
        if deleted else "ဆိုင်ကို ရှာမတွေ့ပါ။",
        "info" if deleted else "error",
    )

    return redirect(url_for("index") + "#shop-tab")


@app.route("/delete-media/<int:media_id>", methods=["GET", "POST"])
def delete_media(media_id):
    deleted = soft_delete_record("media", media_id)

    flash(
        "Media ကို ဖျက်လိုက်ပါပြီ!"
        if deleted else "Media ကို ရှာမတွေ့ပါ။",
        "info" if deleted else "error",
    )

    return redirect(url_for("index") + "#media-tab")


# --------------------------------------------------
# UPLOADED FILES
# --------------------------------------------------

@app.route("/files/<path:filename>")
def custom_static(filename):
    return send_from_directory(
        app.config["UPLOAD_FOLDER"],
        filename,
    )


# Vercel Python deployment အတွက် Flask app ကို export လုပ်ထားသည်။
# Local development:
# flask --app main run --host 0.0.0.0 --port 8000

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "8000")),
        debug=False,
    )
