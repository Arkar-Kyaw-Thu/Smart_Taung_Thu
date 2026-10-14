
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

    # Retry configuration
    MAX_RETRIES = 5
    INITIAL_RETRY_DELAY = 2
    MAX_RETRY_DELAY = 16

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

        # Support a single API_KEY as well
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
            cls._retriever.k = 60

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

        # Do not retry invalid keys or permission errors
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

        return any(marker in message for marker in retryable_markers)

    @classmethod
    def _generate_answer(cls, clean_query, system_instruction):
        """Call Gemini with retry and API key rotation."""

        cls._initialize_keys()

        last_error = None

        for attempt in range(cls.MAX_RETRIES):
            try:
                # Rotate through configured API keys.
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
                        max_output_tokens=4096,
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

                    delay += random.uniform(0, 1)

                    print(
                        f"Retrying in {delay:.1f} seconds..."
                    )

                    time.sleep(delay)

        print(f"Gemini request failed: {last_error}")

        return (
            "တောင်းပန်ပါတယ်၊ AI ဝန်ဆောင်မှုကို "
            "ယာယီအသုံးပြု၍မရသေးပါ။ "
            "ခဏစောင့်ပြီး ထပ်မံကြိုးစားပေးပါ။"
        )

    @classmethod
    def answer_query(cls, user_query: str) -> str:
        """Retrieve agricultural context and generate an answer."""

        clean_query = user_query.strip()

        if not clean_query:
            return "ကျေးဇူးပြု၍ မေးခွန်း ရေးသားပေးပါ။"

        retriever = cls.get_retriever()

        if retriever is None:
            return (
                "Knowledge Base မရှိသေးပါ။ "
                "ingest.py ကို အရင် Run ပါ။"
            )

        _, detected_crop, detected_intent = (
            cls.smart_query_processing(clean_query)
        )

        docs = []

        # --------------------------------------------------
        # 1. Direct matching by crop and intent
        # --------------------------------------------------
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

                if detected_crop not in source:
                    continue

                if (
                    detected_intent in content
                    or detected_intent in source
                ):
                    matching_docs.append(doc)

            if matching_docs:
                docs = matching_docs

        # --------------------------------------------------
        # 2. BM25 retrieval if direct matching fails
        # --------------------------------------------------
        if not docs:
            if detected_crop and detected_intent:
                search_query = (
                    f"{detected_crop} {detected_intent} "
                    f"{clean_query}"
                )
            else:
                search_query = clean_query

            retriever.k = 60
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

        # --------------------------------------------------
        # 3. Debug retrieved documents
        # --------------------------------------------------
        print(
            f"Final selected documents: {len(docs)}"
        )

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

        # --------------------------------------------------
        # 4. Build context
        # --------------------------------------------------
        context_list = [
            doc.page_content
            for doc in docs
        ]

        context_text = "\n\n---\n\n".join(context_list)

        system_instruction = (
            "You are an expert Myanmar Agricultural AI Assistant.\n\n"

            "INSTRUCTIONS:\n"
            "1. Answer the user query using ONLY the provided Context.\n"
            "2. Include all relevant sections, sub-methods, and items "
            "found in the Context.\n"
            "3. Answer in full, natural, polite Myanmar language.\n"
            "4. Organize the answer using headings or bullet points "
            "when appropriate.\n"
            "5. Do not invent agricultural facts that are absent "
            "from the Context.\n"
            "6. If the Context contains no relevant information, "
            "reply exactly: "
            "'ဒီအကြောင်းအရာနှင့် ပတ်သက်သည့် "
            "အချက်အလက် ဒေတာဘေ့စ်ထဲတွင် မရှိသေးပါ။'\n\n"

            f"Context:\n{context_text}"
        )

        # --------------------------------------------------
        # 5. Generate answer with retry
        # --------------------------------------------------
        try:
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
