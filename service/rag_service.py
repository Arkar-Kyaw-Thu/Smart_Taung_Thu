import os
import pickle
import itertools
import time
import random
import logging

from pathlib import Path
from threading import Lock

from dotenv import load_dotenv
from google import genai
from google.genai import types
from langchain_community.retrievers import BM25Retriever


# ---------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
RETRIEVER_PATH = BASE_DIR / "kb" / "bm25_retriever.pkl"

logger = logging.getLogger(__name__)


class AIServiceUnavailable(Exception):
    """Raised when all configured Gemini models fail."""


class RAGService:
    _retriever = None
    _all_docs_cache = None
    _api_keys = []
    _key_iter = None
    _key_lock = Lock()

    # Primary model first, followed by fallback models.
    # Confirm availability for your Google AI Studio API key.
    MODEL_NAMES = [
        os.getenv("GEMINI_MODEL", "gemini-3.8-flash"),
        "gemini-3.7-flash",
        "gemini-3.6-flash",
        "gemini-3.5-flash-lite",
    ]

    MAX_RETRIES_PER_MODEL = 2
    INITIAL_RETRY_DELAY = 1.0
    MAX_RETRY_DELAY = 8.0
    MAX_CONTEXT_CHARS = 24000
    MAX_OUTPUT_TOKENS = 4096

    CROPS = [
        "စပါး", "ကစော့ခါး", "ကညွတ်", "ကနခို", "ကနဖေါ့", "ကျွဲကော",
        "ကြံ", "ကြက်သွန်နီ", "ကြက်သွန်ဖြူ", "ကြက်ဟင်းခါး", "ကလော",
        "ကုလားပဲ", "ကော်ဖီ", "ဂျုံ", "ငရုတ်", "ငှက်ပျော",
        "ဆီထွက်မုန်ညင်း", "စပျစ်", "ဆီအုန်း", "နဂါးမောက်", "ထောပတ်",
        "နှံစားပြောင်း", "နှမ်း", "နာနတ်", "နေကြာ", "ပန်းဂေါ်ဖီ",
        "ပန်းနှမ်း", "ပဲစင်းငုံ", "ပဲတီစိမ်း", "ပဲပုပ်", "မတ်ပဲ",
        "မြေပဲ", "မာလကာ", "မှို", "ရော်ဘာ", "လိမ္မော်",
        "အစေ့ထုတ်ပြောင်း", "အာလူး", "အုန်း", "ဝါ"
    ]

    INTENTS = {
        "စိုက်ပျိုးချိန်": [
            "ချိန်", "စိုက်ပျိုးချိန်", "စိုက်ချိန်", "ဘယ်ချိန်",
            "စိုက်ပျိုးချိန်များ", "စိုက်ချိန်များ"
        ],
        "စိုက်ပျိုးနည်း": [
            "စိုက်", "စိုက်ပျိုး", "စိုက်ပျိုးနည်း", "စိုက်နည်း",
            "စိုက်ပျိုးနည်းစနစ်", "ဘယ်လို့စိုက်ရမလဲ",
            "စိုက်ပျိုးနည်းများ", "စိုက်နည်းများ"
        ],
        "ပိုးမွှား": [
            "ပိုး", "ပိုးမွှား", "ဖျက်ပိုး",
            "ပိုးမွှားများ", "ပိုးမွှားအမျိုးအစား"
        ],
        "ရောဂါ": [
            "ရောဂါ", "ရောဂါများ", "ဖျက်ရောဂါ",
            "ရောဂါအမျိုးအစား", "ရောဂါအမျိုးအစားများ"
        ],
        "ဒေသ": ["ဒေသ", "ဒေသအလိုက်"],
        "မြေအမျိုးအစား": [
            "မြေအမျိုး", "မြေအမျိုးအစား", "မြေမျိုး",
            "ဘယ်မြေ", "မြေအမျိုးအစားများ"
        ],
        "အကြောင်း": [
            "အကြောင်း", "အကြောင်းအရာ",
            "အကြောင်းအရာများ", "ဘာလဲ"
        ],
        "အသုံးပြုသည့်အစိတ်အပိုင်း": [
            "အစိတ်အပိုင်း", "အစိတ်အပိုင်းများ",
            "ဘယ်အစိတ်အပိုင်း", "ဘယ်အစိတ်အပိုင်းများ"
        ],
        "ဆေးဖက်ဝင်အာနိသင်": [
            "ဆေးဖက်ဝင်အာနိသင်", "ဆေးဖက်ဝင်အာနိသင်များ",
            "ဘယ်ဆေးဖက်ဝင်အာနိသင်",
            "ဘယ်ဆေးဖက်ဝင်အာနိသင်များ"
        ],
        "အသုံးပြုပုံ": [
            "အသုံးပြုပုံ", "အသုံးပြုပုံများ",
            "ဘယ်လိုအသုံးပြုရမလဲ",
            "ဘယ်လိုအသုံးပြုပုံ", "ဘယ်လိုအသုံးပြုပုံများ"
        ],
        "ဓာတ်မြေဩဇာသုံးစွဲခြင်း": [
            "ဓာတ်မြေဩဇာ", "ဓာတ်မြေဩဇာသုံးစွဲခြင်း",
            "ဘယ်လိုဓာတ်မြေဩဇာသုံးစွဲရမလဲ"
        ],
        "ရေသွင်းခြင်း": [
            "ရေသွင်းခြင်း", "ရေသွင်းနည်း",
            "ဘယ်လိုရေသွင်းရမလဲ"
        ],
        "ရာသီဥတု": [
            "ရာသီဥတု", "ရာသီဥတုအခြေအနေ",
            "ဘယ်လိုရာသီဥတု"
        ],
        "ရိတ်သိမ်းခြင်း": [
            "ရိတ်သိမ်းခြင်း", "ရိတ်သိမ်းနည်း",
            "ဘယ်လိုရိတ်သိမ်းရမလဲ"
        ],
    }

    # -----------------------------------------------------
    # API KEYS
    # -----------------------------------------------------

    @classmethod
    def _initialize_keys(cls):
        """Load all configured API keys once."""

        if cls._key_iter is not None:
            return

        keys = []

        # Do not stop at a missing key number.
        for i in range(1, 51):
            key = os.getenv(f"API_KEY_{i}", "").strip()

            if key and key not in keys:
                keys.append(key)

        single_key = os.getenv("API_KEY", "").strip()

        if single_key and single_key not in keys:
            keys.append(single_key)

        if not keys:
            raise RuntimeError(
                "Gemini API key မတွေ့ပါ။ "
                "Vercel Environment Variables ထဲတွင် "
                "API_KEY_1 သို့မဟုတ် API_KEY ထည့်ပါ။"
            )

        with cls._key_lock:
            if cls._key_iter is None:
                cls._api_keys = keys
                cls._key_iter = itertools.cycle(keys)

        logger.info("Gemini API keys loaded: %s", len(keys))

    @classmethod
    def get_genai_client(cls):
        """Create a Gemini client using the next configured key."""

        cls._initialize_keys()

        with cls._key_lock:
            key = next(cls._key_iter)

        return genai.Client(api_key=key)

    # -----------------------------------------------------
    # LOAD BM25 RETRIEVER
    # -----------------------------------------------------

    @classmethod
    def get_retriever(cls):
        """Load the existing pickle and cache its documents."""

        if cls._retriever is not None:
            return cls._retriever

        if not RETRIEVER_PATH.exists():
            logger.error("Retriever file not found: %s", RETRIEVER_PATH)
            return None

        try:
            with open(RETRIEVER_PATH, "rb") as file:
                all_docs = pickle.load(file)

            if not all_docs:
                logger.error("Retriever file contains no documents.")
                return None

            cls._all_docs_cache = all_docs

            cls._retriever = BM25Retriever.from_documents(all_docs)
            cls._retriever.k = 60

            logger.info(
                "BM25 retriever loaded: %s documents",
                len(all_docs),
            )

            return cls._retriever

        except Exception:
            logger.exception("Retriever loading failed")
            return None

    # -----------------------------------------------------
    # QUERY PROCESSING
    # -----------------------------------------------------

    @classmethod
    def smart_query_processing(cls, user_query: str):
        """Detect crop and intent from a Myanmar-language question."""

        detected_crop = None
        detected_intent = ""

        for crop in cls.CROPS:
            if crop in user_query:
                detected_crop = crop
                break

        for intent_name, keywords in cls.INTENTS.items():
            if any(keyword in user_query for keyword in keywords):
                detected_intent = intent_name
                break

        return user_query, detected_crop, detected_intent

    # -----------------------------------------------------
    # ERROR CLASSIFICATION
    # -----------------------------------------------------

    @classmethod
    def _is_retryable_error(cls, error):
        """Retry temporary service errors, not invalid requests."""

        message = str(error).upper()

        permanent_errors = [
            "API_KEY_INVALID",
            "API KEY NOT VALID",
            "PERMISSION_DENIED",
            "UNAUTHENTICATED",
            "INVALID_ARGUMENT",
            "404 NOT_FOUND",
            "NOT_FOUND",
        ]

        if any(marker in message for marker in permanent_errors):
            return False

        retryable_errors = [
            "429",
            "500",
            "502",
            "503",
            "504",
            "RESOURCE_EXHAUSTED",
            "UNAVAILABLE",
            "INTERNAL",
            "DEADLINE_EXCEEDED",
            "408",
            "TIMEOUT",
            "TIMED OUT",
            "CONNECTION RESET",
            "CONNECTION ERROR",
        ]

        return any(marker in message for marker in retryable_errors)

    # -----------------------------------------------------
    # GEMINI GENERATION WITH MODEL FALLBACK
    # -----------------------------------------------------

    @classmethod
    def _generate_answer(cls, clean_query, system_instruction):
        """
        Try configured models in order.
        Retry transient errors with exponential backoff.
        Raise AIServiceUnavailable if all models fail.
        """

        cls._initialize_keys()
        last_error = None

        # Remove duplicate model names while preserving order.
        models = list(dict.fromkeys(
            model.strip()
            for model in cls.MODEL_NAMES
            if model and model.strip()
        ))

        for model_name in models:
            logger.info("Trying Gemini model: %s", model_name)

            for attempt in range(cls.MAX_RETRIES_PER_MODEL):
                try:
                    client = cls.get_genai_client()

                    logger.info(
                        "Gemini request: model=%s attempt=%s/%s",
                        model_name,
                        attempt + 1,
                        cls.MAX_RETRIES_PER_MODEL,
                    )

                    response = client.models.generate_content(
                        model=model_name,
                        contents=clean_query,
                        config=types.GenerateContentConfig(
                            system_instruction=system_instruction,
                            temperature=0.2,
                            max_output_tokens=cls.MAX_OUTPUT_TOKENS,
                        ),
                    )

                    answer = getattr(response, "text", None)

                    if answer and answer.strip():
                        logger.info(
                            "Gemini generation succeeded with %s",
                            model_name,
                        )
                        return answer.strip()

                    raise RuntimeError(
                        f"{model_name} returned an empty response."
                    )

                except Exception as error:
                    last_error = error

                    logger.warning(
                        "Gemini failed: model=%s attempt=%s error=%s",
                        model_name,
                        attempt + 1,
                        error,
                    )

                    # Invalid model/key/request: try the next model
                    # only when it makes sense; don't retry permanently.
                    if not cls._is_retryable_error(error):
                        break

                    if attempt < cls.MAX_RETRIES_PER_MODEL - 1:
                        delay = min(
                            cls.INITIAL_RETRY_DELAY * (2 ** attempt),
                            cls.MAX_RETRY_DELAY,
                        )
                        delay += random.uniform(0, 0.5)

                        logger.info("Retrying in %.1f seconds", delay)
                        time.sleep(delay)

            logger.warning(
                "Moving to next fallback model after failure: %s",
                model_name,
            )

        logger.error("All Gemini models failed: %s", last_error)

        raise AIServiceUnavailable(
            "Gemini service is temporarily unavailable."
        ) from last_error

    # -----------------------------------------------------
    # MAIN RAG ENTRY POINT
    # -----------------------------------------------------

    @classmethod
    def answer_query(cls, user_query: str) -> str:
        """Retrieve agricultural documents and generate an answer."""

        clean_query = (user_query or "").strip()

        if not clean_query:
            return "ကျေးဇူးပြု၍ မေးခွန်း ရေးသားပေးပါ။"

        retriever = cls.get_retriever()

        if retriever is None:
            raise RuntimeError(
                "Knowledge Base ကို ဖတ်၍မရပါ။ "
                "kb/bm25_retriever.pkl ကို စစ်ဆေးပါ။"
            )

        _, detected_crop, detected_intent = (
            cls.smart_query_processing(clean_query)
        )

        docs = []

        # 1. Direct matching by crop and intent
        if detected_crop and detected_intent:
            logger.info(
                "Direct matching: Crop=%s Intent=%s",
                detected_crop,
                detected_intent,
            )

            matching_docs = []

            for doc in cls._all_docs_cache or []:
                source = str(doc.metadata.get("source", ""))
                content = doc.page_content or ""

                if detected_crop not in source:
                    continue

                if (
                    detected_intent in content
                    or detected_intent in source
                ):
                    matching_docs.append(doc)

            if matching_docs:
                docs = matching_docs

        # 2. BM25 fallback retrieval
        if not docs:
            if detected_crop and detected_intent:
                search_query = (
                    f"{detected_crop} {detected_intent} {clean_query}"
                )
            elif detected_crop:
                search_query = f"{detected_crop} {clean_query}"
            else:
                search_query = clean_query

            retriever.k = 60
            docs = retriever.invoke(search_query)

            # Prefer documents from the requested crop when available.
            if detected_crop:
                filtered_docs = [
                    doc
                    for doc in docs
                    if detected_crop in str(
                        doc.metadata.get("source", "")
                    )
                ]

                if filtered_docs:
                    docs = filtered_docs

        # 3. Remove duplicate documents and limit context size.
        selected_docs = []
        seen = set()
        context_size = 0

        for doc in docs:
            content = (doc.page_content or "").strip()

            if not content or content in seen:
                continue

            seen.add(content)

            source = str(doc.metadata.get("source", "Unknown"))
            block = f"Source: {source}\n{content}"

            remaining = cls.MAX_CONTEXT_CHARS - context_size

            if remaining <= 0:
                break

            if len(block) > remaining:
                block = block[:remaining]

            selected_docs.append(block)
            context_size += len(block)

        logger.info(
            "Final selected documents: %s",
            len(selected_docs),
        )

        if not selected_docs:
            return (
                "ဒီအကြောင်းအရာနှင့် ပတ်သက်သည့် "
                "အချက်အလက် ဒေတာဘေ့စ်ထဲတွင် မရှိသေးပါ။"
            )

        # 4. Build the context for Gemini.
        context_text = "\n\n---\n\n".join(selected_docs)

        system_instruction = (
            "You are an expert Myanmar Agricultural AI Assistant.\n\n"
            "INSTRUCTIONS:\n"
            "1. Answer using ONLY the provided Context.\n"
            "2. Include relevant sections, methods, and steps from Context.\n"
            "3. Answer in full, natural, polite Myanmar language.\n"
            "4. Use headings and bullet points when useful.\n"
            "5. Do not invent agricultural facts absent from Context.\n"
            "6. If Context has no relevant information, reply exactly:\n"
            "'ဒီအကြောင်းအရာနှင့် ပတ်သက်သည့် "
            "အချက်အလက် ဒေတာဘေ့စ်ထဲတွင် မရှိသေးပါ။'\n\n"
            f"Context:\n{context_text}"
        )

        # 5. Generate answer.
        # AIServiceUnavailable is intentionally allowed to propagate
        # so the Flask route can return success=False and HTTP 503.
        return cls._generate_answer(
            clean_query,
            system_instruction,
        )