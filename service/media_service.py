
import logging
import yt_dlp

from storage import list_records, create_record


logger = logging.getLogger(__name__)


class MediaService:
    CHANNELS = [
        {
            "name": "Green Way App",
            "url": "https://www.youtube.com/@GreenWayapp/videos",
        },
        {
            "name": "Knowledge Zone",
            "url": "https://www.youtube.com/@knowledgezonemm/videos",
        },
        {
            "name": "Win Production",
            "url": "https://www.youtube.com/@winproduction8682/videos",
        },
        {
            "name": "Farmers Power",
            "url": "https://www.youtube.com/@farmerspower2064/videos",
        },
        {
            "name": "The Farmer Times",
            "url": "https://www.youtube.com/@TheFarmerTimes/videos",
        },
        {
            "name": "Khonethar14",
            "url": "https://www.youtube.com/@khonethar14/videos",
        },
        {
            "name": "Agri Future Myanmar",
            "url": "https://www.youtube.com/@agrifuturemyanmar4261/videos",
        },
    ]

    AGRI_KEYWORDS = [
        "စိုက်",
        "စိုက်ပျိုး",
        "မြေဩဇာ",
        "သီးနှံ",
        "မျိုးစေ့",
        "ရေသွင်း",
        "ဟင်းသီးဟင်းရွက်",
        "သစ်သီး",
        "ရိတ်သိမ်း",
        "ခြံ",
        "စိုက်နည်း",
        "မြေဆီ",
        "ပိုးသတ်ဆေး",
        "ပျိုး",
        "ခရမ်းချဉ်",
        "ငရုတ်",
        "ကန်စွန်း",
        "ဂေါ်ဖီ",
        "ကြက်သွန်",
        "စပါး",
        "သဘာဝမြေဩဇာ",
    ]

    @staticmethod
    def is_agriculture_video(title: str) -> bool:
        title = title or ""
        return any(
            keyword in title
            for keyword in MediaService.AGRI_KEYWORDS
        )

    @staticmethod
    def _get_existing_links():
        """media.json ထဲရှိပြီးသား link များကို ဖတ်ယူသည်."""
        records = list_records("media")

        return {
            str(record.get("link", "")).strip()
            for record in records
            if record.get("link")
        }

    @staticmethod
    def preview_youtube_videos(limit_per_channel=100):
        """သတ်မှတ်ထားသော channel ၇ ခုမှ စိုက်ပျိုးရေး video များ ရှာသည်."""
        preview_list = []
        existing_links = MediaService._get_existing_links()

        ydl_opts = {
            "extract_flat": "in_playlist",
            "skip_download": True,
            "quiet": True,
            "no_warnings": True,
            "ignoreerrors": True,
            "playlistend": limit_per_channel,
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            for channel in MediaService.CHANNELS:
                channel_name = channel["name"]
                channel_url = channel["url"]

                try:
                    info = ydl.extract_info(
                        channel_url,
                        download=False,
                    )

                    if not info:
                        continue

                    entries = info.get("entries") or []

                    for entry in entries:
                        if not entry:
                            continue

                        title = entry.get("title", "")

                        if not MediaService.is_agriculture_video(title):
                            continue

                        video_id = entry.get("id")

                        if not video_id:
                            continue

                        video_link = (
                            f"https://www.youtube.com/watch?v={video_id}"
                        )

                        if video_link in existing_links:
                            continue

                        preview_list.append({
                            "channel_name": channel_name,
                            "video_id": video_id,
                            "title": title,
                            "description": title,
                            "link": video_link,
                            "type": "knowledge",
                            "suggested_type": "knowledge",
                            "thumbnail": (
                                f"https://img.youtube.com/vi/"
                                f"{video_id}/mqdefault.jpg"
                            ),
                        })

                except Exception:
                    logger.exception(
                        "YouTube scraping failed: %s",
                        channel_name,
                    )

        return preview_list

    @staticmethod
    def save_media_from_preview(description, link, media_type="knowledge"):
        """Preview မှ ရွေးထားသော video ကို media.json ထဲ သိမ်းသည်."""
        description = (
            description.strip()
            if isinstance(description, str)
            else ""
        )
        link = link.strip() if isinstance(link, str) else ""

        if not description or not link:
            raise ValueError("Video title နှင့် link လိုအပ်ပါသည်။")

        # Preview မှလာသော link သာ လက်ခံရန် video ID စစ်ဆေးသည်။
        import re
        from urllib.parse import urlparse, parse_qs

        parsed = urlparse(link)
        host = (parsed.hostname or "").lower()

        if host in ("youtube.com", "www.youtube.com", "m.youtube.com"):
            video_id = (
                parse_qs(parsed.query).get("v", [None])[0]
                if parsed.path == "/watch"
                else None
            )
        elif host == "youtu.be":
            video_id = parsed.path.strip("/").split("/")[0]
        else:
            video_id = None

        if not video_id or not re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id):
            raise ValueError("မှန်ကန်သော YouTube video link ထည့်ပါ။")

        normalized_link = (
            f"https://www.youtube.com/watch?v={video_id}"
        )

        existing_links = MediaService._get_existing_links()

        if normalized_link in existing_links:
            return {
                "success": True,
                "already_exists": True,
                "message": "ဒီ Video ကို သိမ်းဆည်းပြီးသား ဖြစ်ပါသည်။",
            }

        record = create_record("media", {
            "description": description,
            "link": normalized_link,
            "type": media_type or "knowledge",
        })

        return {
            "success": True,
            "already_exists": False,
            "media": record,
        }
