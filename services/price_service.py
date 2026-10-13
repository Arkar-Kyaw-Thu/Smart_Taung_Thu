import os
import re
import logging
import tempfile
from datetime import datetime

import requests
import pandas as pd
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# Local development အတွက်သာ အသုံးပြုမည့် folder
UPLOAD_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "uploads",
    "price",
)

BASE_URL = "https://wisarra.com/mm/market-price"

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}

COLUMNS = [
    "သီးနှံအမည်",
    "ဒေသ",
    "ဈေးကွက်",
    "အနိမ့်ဆုံးဈေး",
    "အမြင့်ဆုံးဈေး",
    "ငွေကြေး",
    "အရေအတွက်",
    "ယူနစ်",
]


class MarketPriceService:

    @staticmethod
    def _pad_single_digit(match):
        value = match.group(0)

        myanmar_digits = {
            "၁": "၀၁",
            "၂": "၀၂",
            "၃": "၀၃",
            "၄": "၀၄",
            "၅": "၀၅",
            "၆": "၀၆",
            "၇": "၀၇",
            "၈": "၀၈",
            "၉": "၀၉",
        }

        if value in myanmar_digits:
            return myanmar_digits[value]

        if value.isdigit() and len(value) == 1:
            return f"0{value}"

        return value

    @staticmethod
    def _get_next_prefix_number():
        os.makedirs(UPLOAD_DIR, exist_ok=True)

        excel_files = [
            name
            for name in os.listdir(UPLOAD_DIR)
            if name.lower().endswith((".xlsx", ".xls"))
        ]

        max_num = 0

        for filename in excel_files:
            match = re.match(r"^(\d+)_", filename)

            if match:
                max_num = max(max_num, int(match.group(1)))

        next_num = max(max_num + 1, len(excel_files) + 1)

        return f"{next_num:03d}"

    @staticmethod
    def _clean_market_date(raw_date):
        clean_date = (
            raw_date.replace("ရက်", "")
            .replace("၊", "")
            .replace("(", "")
            .replace(")", "")
            .strip()
        )

        clean_date = re.sub(
            r"(?<!\S)[၁-၉1-9](?=\s|$)",
            MarketPriceService._pad_single_digit,
            clean_date,
        )

        clean_date = re.sub(r"\s+", "_", clean_date)

        if not clean_date:
            clean_date = datetime.now().strftime("%Y-%m-%d")

        # Filename ထဲတွင် အသုံးမပြုသင့်သော character များကို ဖယ်ရှားခြင်း
        clean_date = re.sub(r'[<>:"/\\|?*]', "", clean_date)

        return clean_date

    @staticmethod
    def _scrape_market_prices():
        records = []
        market_date = ""
        page = 1

        with requests.Session() as session:
            session.headers.update(HEADERS)

            while True:
                url = f"{BASE_URL}?page={page}"

                try:
                    response = session.get(url, timeout=15)
                    response.raise_for_status()
                except requests.RequestException as exc:
                    logger.warning(
                        "Wisarra page %s ကို ရယူမရပါ: %s",
                        page,
                        exc,
                    )
                    break

                soup = BeautifulSoup(response.text, "html.parser")

                if not market_date:
                    page_content = soup.select_one(".pageContent")

                    if page_content:
                        p_tag = page_content.find("p")

                        if p_tag:
                            market_date = re.sub(
                                r"\s+",
                                " ",
                                p_tag.get_text(" ", strip=True),
                            ).strip()

                rows = soup.select("table tr")

                if len(rows) <= 1:
                    break

                page_records = []

                for row in rows:
                    cols = row.select("td")

                    if len(cols) >= 8:
                        page_records.append({
                            COLUMNS[index]: cols[index].get_text(strip=True)
                            for index in range(8)
                        })

                if not page_records:
                    break

                records.extend(page_records)
                page += 1

        return records, market_date

    @staticmethod
    def fetch_and_save_excel():
        """
        Wisarra မှ market price များကို scrape လုပ်ပြီး Excel ဖိုင်ထုတ်ပေးသည်။

        Return:
            (file_path, file_name) အောင်မြင်လျှင်
            (None, None) မအောင်မြင်လျှင်
        """

        try:
            records, raw_date = (
                MarketPriceService._scrape_market_prices()
            )

            logger.info(
                "Wisarra မှ ရရှိသော records: %s",
                len(records),
            )

            if not records:
                logger.warning("သိမ်းဆည်းရန် ဈေးနှုန်းဒေတာ မရှိပါ။")
                return None, None

            clean_date = MarketPriceService._clean_market_date(
                raw_date
            )

            os.makedirs(UPLOAD_DIR, exist_ok=True)

            # Local development အတွက် ရက်စွဲတူဖိုင် ရှိပြီးသားလား စစ်ဆေးခြင်း
            existing_files = [
                name
                for name in os.listdir(UPLOAD_DIR)
                if f"Market_Price_{clean_date}.xlsx" in name
            ]

            if existing_files:
                filename = sorted(existing_files)[0]
                filepath = os.path.join(UPLOAD_DIR, filename)

                logger.info("ဖိုင်ရှိပြီးသား: %s", filename)
                return filepath, filename

            prefix = MarketPriceService._get_next_prefix_number()

            filename = (
                f"{prefix}_Market_Price_{clean_date}.xlsx"
            )
            filepath = os.path.join(UPLOAD_DIR, filename)

            dataframe = pd.DataFrame(records, columns=COLUMNS)

            dataframe.to_excel(
                filepath,
                index=False,
                engine="openpyxl",
            )

            logger.info("Excel ဖိုင်ထုတ်ပြီးပါပြီ: %s", filename)

            return filepath, filename

        except Exception:
            logger.exception("MarketPriceService error")
            return None, None