import os
import pickle
import itertools
import time
import random

from pathlib import Path
from dotenv import load_dotenv
from google import genai
from google.genai import types
from langchain_community.retrievers import BM25Retriever

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
RETRIEVER_PATH = BASE_DIR / "kb" / "bm25_retriever.pkl"


class RAGService:
    _retriever = None
    _all_docs_cache = None
    _key_iter = None
    _api_keys = []

    # Gemini model
    MODEL_NAME = "gemini-3.6-flash"

    # Reduced retry settings to limit long-running requests
    MAX_RETRIES = 2
    INITIAL_RETRY_DELAY = 1
    MAX_RETRY_DELAY = 2

    # Retrieval and context limits
    RETRIEVER_TOP_K = 8
    MAX_CONTEXT_CHARS = 24000
    MAX_DOCUMENTS_DIRECT_MATCH = 8

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
            "စိုက်ပျိုးနည်း", "စိုက်နည်း",
            "စိုက်ပျိုးနည်းစနစ်", "ဘယ်လို့စိုက်ရမလဲ",
            "စိုက်ပျိုးနည်းများ", "စိုက်နည်းများ", "စိုက်ပျိုး"
        ],
        "ပိုးမွှား": [
            "ပိုးမွှား", "ဖျက်ပိုး",
            "ပိုးမွှားများ", "ပိုးမွှားအမျိုးအစား"
        ],
        "ရောဂါ": [
            "ရောဂါ", "ရောဂါများ", "ဖျက်ရောဂါ",
            "ရောဂါအမျိုးအစား", "ရောဂါအမျိုးအစားများ"
        ],
        "ဒေသ": ["ဒေသအလိုက်", "ဒေသ"],
        "မြေအမျိုးအစား": [
            "မြေအမျိုးအစား", "မြေမျိုး", "ဘယ်မြေ",
            "မြေအမျိုးအစားများ"
        ],
        "အကြောင်း": [
            "အကြောင်းအရာ", "အကြောင်းအရာများ", "ဘာလဲ"
        ],
        "အသုံးပြုသည့်အစိတ်အပိုင်း": [
            "ဘယ်အစိတ်အပိုင်း", "အစိတ်အပိုင်းများ",
            "အစိတ်အပိုင်း"
        ],
        "ဆေးဖက်ဝင်အာနိသင်": [
            "ဆေးဖက်ဝင်အာနိသင်",
            "ဆေးဖက်ဝင်အာနိသင်များ",
            "ဘယ်ဆေးဖက်ဝင်အာနိသင်"
        ],
        "အသုံးပြုပုံ": [
            "အသုံးပြုပုံ", "အသုံးပြုပုံများ",
            "ဘယ်လိုအသုံးပြုရမလဲ", "ဘယ်လိုအသုံးပြုပုံ"
        ],
        "ဓာတ်မြေဩဇာသုံးစွဲခြင်း": [
            "ဓာတ်မြေဩဇာ",
            "ဓာတ်မြေဩဇာသုံးစွဲခြင်း",
            "ဘယ်လိုဓာတ်မြေဩဇာသုံးစွဲရမလဲ"
        ],
        "ရေသွင်းခြင်း": [
            "ရေသွင်းခြင်း", "ရေသွင်းနည်း",
            "ဘယ်လိုရေသွင်းရမလဲ"
        ],
        "ရာသီဥတု": [
            "ရာသီဥတုအခြေအနေ", "ဘယ်လိုရာသီဥတု",
            "ရာသီဥတု"
        ],
        "ရိတ်သိမ်းခြင်း": [
            "ရိတ်သိမ်းခြင်း", "ရိတ်သိမ်းနည်း",
            "ဘယ်လိုရိတ်သိမ်းရမလဲ"
        ],
    }

    @classmethod
    def _initialize_keys(cls):
        """Load API keys from .env once."""

        if cls._key_iter is not None:
            return

        keys = []

        # Read API_KEY_1, API_KEY_2, API_KEY_3, ...
        i = 1
        while True:
            key = os.getenv(f"API_KEY_{i}")

            if not key:
                break

            key = key.strip()

            if key and key not in keys:
                keys.append(key)

            i += 1

        # Also support a single API_KEY
        single_key = os.getenv("API_KEY")

        if single_key:
            single_key = single_key.strip()

            if single_key and single_key not in keys:
                keys.append(single_key)

        if not keys:
            raise ValueError(
                "API Key တစ်ခုမှ မတွေ့ပါ။ "
                ".env ဖိုင်ထဲတွင် API_KEY သို့မဟုတ် "
                "API_KEY_1 ကို ထည့်ပေးပါ။"
            )

        cls._api_keys = keys
        cls._key_iter = itertools.cycle(keys)

        print(f"Gemini API keys loaded: {len(keys)}")

    @classmethod
    def get_genai_client(cls):
        """Create a client using the next API key."""

        cls._initialize_keys()

        key = next(cls._key_iter)

        return genai.Client(api_key=key)

    @classmethod
    def get_retriever(cls):
        """Load the BM25 retriever and document cache."""

        if cls._retriever is not None:
            return cls._retriever

        if not RETRIEVER_PATH.exists():
            print(f"Retriever file not found: {RETRIEVER_PATH}")
            return None

        try:
            with open(RETRIEVER_PATH, "rb") as f:
                all_docs = pickle.load(f)

            cls._all_docs_cache = all_docs

            cls._retriever = BM25Retriever.from_documents(all_docs)
            cls._retriever.k = cls.RETRIEVER_TOP_K

            print(f"BM25 retriever loaded: {len(all_docs)} documents")

            return cls._retriever

        except Exception as e:
            print(f"Retriever loading error: {e}")
            return None

    @classmethod
    def smart_query_processing(cls, user_query: str):
        """Detect crop and intent from the user's question."""

        detected_crop = None
        detected_intent = ""

        # Detect crop
        for crop in cls.CROPS:
            if crop in user_query:
                detected_crop = crop
                break

        # Detect intent
        for intent_name, keywords in cls.INTENTS.items():
            if any(keyword in user_query for keyword in keywords):
                detected_intent = intent_name
                break

        return user_query, detected_crop, detected_intent

    @classmethod
    def _is_retryable_error(cls, error):
        """Identify temporary API and network errors."""

        message = str(error).upper()

        non_retryable_markers = [
            "API_KEY_INVALID",
            "API KEY NOT VALID",
            "PERMISSION_DENIED",
            "UNAUTHENTICATED",
            "INVALID_ARGUMENT",
            "404 NOT_FOUND",
        ]

        if any(marker in message for marker in non_retryable_markers):
            return False

        retryable_markers = [
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

        return any(marker in message for marker in retryable_markers)

    @classmethod
    def _generate_answer(cls, clean_query, system_instruction):
        """Call Gemini with limited retries and API key rotation."""

        cls._initialize_keys()

        last_error = None

        for attempt in range(cls.MAX_RETRIES):
            try:
                client = cls.get_genai_client()

                print(
                    f"Gemini request: attempt "
                    f"{attempt + 1}/{cls.MAX_RETRIES}"
                )

                response = client.models.generate_content(
                    model=cls.MODEL_NAME,
                    contents=clean_query,
                    config=types.GenerateContentConfig(
                        system_instruction=system_instruction,
                        temperature=0.2,
                        max_output_tokens=2048,
                    ),
                )

                if response.text:
                    return response.text

                raise RuntimeError(
                    "Gemini returned an empty response."
                )

            except Exception as e:
                last_error = e

                print(
                    f"Gemini API error "
                    f"(attempt {attempt + 1}): {e}"
                )

                if not cls._is_retryable_error(e):
                    break

                if attempt < cls.MAX_RETRIES - 1:
                    delay = min(
                        cls.INITIAL_RETRY_DELAY * (2 ** attempt),
                        cls.MAX_RETRY_DELAY,
                    )

                    delay += random.uniform(0, 0.3)

                    print(f"Retrying in {delay:.1f} seconds...")
                    time.sleep(delay)

        print(f"Gemini request failed: {last_error}")

        return (
            "တောင်းပန်ပါတယ်၊ AI ဝန်ဆောင်မှုကို "
            "ယာယီအသုံးပြု၍မရသေးပါ။ "
            "ခဏစောင့်ပြီး ထပ်မံကြိုးစားပေးပါ။"
        )

    @classmethod
    def _select_documents(
        cls,
        retriever,
        clean_query,
        detected_crop,
        detected_intent,
    ):
        """Select relevant documents using direct matching and BM25."""

        docs = []

        # 1. Direct matching by crop and intent
        if detected_crop and detected_intent:
            print(
                f"Direct matching: "
                f"Crop={detected_crop}, "
                f"Intent={detected_intent}"
            )

            matching_docs = []

            for doc in cls._all_docs_cache or []:
                source = str(doc.metadata.get("source", ""))
                content = doc.page_content

                # Preserve the existing source-based crop matching
                if detected_crop not in source:
                    continue

                if (
                    detected_intent in content
                    or detected_intent in source
                ):
                    matching_docs.append(doc)

            if matching_docs:
                docs = matching_docs[
                    :cls.MAX_DOCUMENTS_DIRECT_MATCH
                ]

        # 2. BM25 retrieval if direct matching fails
        if not docs:
            if detected_crop and detected_intent:
                search_query = (
                    f"{detected_crop} {detected_intent} "
                    f"{clean_query}"
                )
            elif detected_crop:
                search_query = f"{detected_crop} {clean_query}"
            else:
                search_query = clean_query

            retriever.k = cls.RETRIEVER_TOP_K
            docs = retriever.invoke(search_query)

            # Prefer documents belonging to the detected crop
            if detected_crop:
                filtered_docs = [
                    doc
                    for doc in docs
                    if detected_crop
                    in str(doc.metadata.get("source", ""))
                ]

                if filtered_docs:
                    docs = filtered_docs

        return docs

    @classmethod
    def _build_context(cls, docs):
        """Build a context string with a maximum character limit."""

        context_parts = []
        remaining_chars = cls.MAX_CONTEXT_CHARS

        for doc in docs:
            content = (doc.page_content or "").strip()

            if not content:
                continue

            if remaining_chars <= 0:
                break

            # Include a source label when available
            source = str(doc.metadata.get("source", "Unknown"))

            section = (
                f"Source: {source}\n"
                f"{content}"
            )

            if len(section) > remaining_chars:
                section = section[:remaining_chars]

            context_parts.append(section)
            remaining_chars -= len(section) + 9

        return "\n\n---\n\n".join(context_parts)

    @classmethod
    def answer_query(cls, user_query: str) -> str:
        """Retrieve agricultural context and generate an answer."""

        clean_query = (user_query or "").strip()

        if not clean_query:
            return "ကျေးဇူးပြု၍ မေးခွန်း ရေးသားပေးပါ။"

        try:
            retriever = cls.get_retriever()

            if retriever is None:
                return (
                    "Knowledge Base မရှိသေးပါ။ "
                    "ingest.py ကို အရင် Run ပါ။"
                )

            _, detected_crop, detected_intent = (
                cls.smart_query_processing(clean_query)
            )

            docs = cls._select_documents(
                retriever= retriever,
                clean_query=clean_query,
                detected_crop=detected_crop,
                detected_intent=detected_intent,
            )

            print(f"Final selected documents: {len(docs)}")

            for i, doc in enumerate(docs[:3]):
                print(
                    f"[Document {i + 1}] "
                    f"Source: {doc.metadata.get('source', 'Unknown')} "
                    f"| Content: {doc.page_content[:120]}..."
                )

            if not docs:
                return (
                    "ဒီအကြောင်းအရာနှင့် ပတ်သက်သည့် "
                    "အချက်အလက် ဒေတာဘေ့စ်ထဲတွင် မရှိသေးပါ။"
                )

            # Build bounded context
            context_text = cls._build_context(docs)

            if not context_text.strip():
                return (
                    "ဒီအကြောင်းအရာနှင့် ပတ်သက်သည့် "
                    "အချက်အလက် ဒေတာဘေ့စ်ထဲတွင် မရှိသေးပါ။"
                )

            system_instruction = (
                "You are an expert Myanmar Agricultural AI Assistant.\n\n"
                "INSTRUCTIONS:\n"
                "1. Answer the user's question using only the provided Context.\n"
                "2. Include the relevant sections, methods, and items "
                "available in the Context.\n"
                "3. Answer in natural, polite Myanmar language.\n"
                "4. Use headings or bullet points when appropriate.\n"
                "5. Do not invent agricultural facts absent from the Context.\n"
                "6. If the Context does not contain relevant information, "
                "reply exactly: "
                "'ဒီအကြောင်းအရာနှင့် ပတ်သက်သည့် "
                "အချက်အလက် ဒေတာဘေ့စ်ထဲတွင် မရှိသေးပါ။'\n\n"
                f"Context:\n{context_text}"
            )

            return cls._generate_answer(
                clean_query,
                system_instruction,
            )

        except Exception as e:
            print(f"RAG service error: {e}")

            return (
                "တောင်းပန်ပါတယ်၊ စနစ်တွင် အမှားတစ်ခု "
                "ဖြစ်ပေါ်နေပါတယ်။ ခဏအကြာတွင် "
                "ထပ်မံကြိုးစားပေးပါ။"
            )