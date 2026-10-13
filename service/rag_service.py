import os
import pickle
import itertools
from dotenv import load_dotenv
from google import genai
from google.genai import types
from langchain_community.retrievers import BM25Retriever

load_dotenv()

RETRIEVER_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "bm25_retriever.pkl"
)

class RAGService:
    _retriever = None
    _all_docs_cache = None
    _key_iter = None

    CROPS = [
        "စပါး", "ကစော့ခါး", "ကညွတ်", "ကနခို", "ကနဖေါ့", "ကျွဲကော", "ကြံ", "ကြက်သွန်နီ", "ကြက်သွန်ဖြူ", "ကြက်ဟင်းခါး",
        "ကလော", "ကုလားပဲ", "ကော်ဖီ", "ဂျုံ", "ငရုတ်", "ငှက်ပျော", "ဆီထွက်မုန်ညင်း", "စပျစ်", "ဆီအုန်း", "နဂါးမောက်", "ထောပတ်",
        "နှံစားပြောင်း", "နှမ်း", "နာနတ်", "နေကြာ", "ပန်းဂေါ်ဖီ", "ပန်းနှမ်း", "ပဲစင်းငုံ", "ပဲတီစိမ်း", "ပဲပုပ်", "မတ်ပဲ", "မြေပဲ", "မာလကာ",
        "မှို", "ရော်ဘာ", "လိမ္မော်", "အစေ့ထုတ်ပြောင်း", "အာလူး", "အုန်း", "ဝါ"
    ] 
    INTENTS = {
        "စိုက်ပျိုးချိန်": ["ချိန်", "စိုက်ပျိုးချိန်", "စိုက်ချိန်", "ဘယ်ချိန်", "စိုက်ပျိုးချိန်များ", "စိုက်ချိန်များ"],
        "စိုက်ပျိုးနည်း": ["စိုက်", "စိုက်ပျိုး", "စိုက်ပျိုးနည်း", "စိုက်နည်း", "စိုက်ပျိုးနည်းစနစ်", "ဘယ်လို့စိုက်ရမလဲ", "စိုက်ပျိုးနည်းများ", "စိုက်နည်းများ"],
        "ပိုးမွှား": ["ပိုး", "ပိုးမွှား", "ဖျက်ပိုး", "ပိုးမွှားများ", "ပိုးမွှားအမျိုးအစား"],
        "ရောဂါ": ["ရောဂါ", "ရောဂါများ", "ဖျက်ရောဂါ", "ရောဂါအမျိုးအစား", "ရောဂါအမျိုးအစားများ"],
        "ဒေသ": ["ဒေသ", "ဒေသအလိုက်"],
        "မြေအမျိုးအစား": ["မြေအမျိုး", "မြေအမျိုးအစား", "မြေမျိုး", "ဘယ်မြေ", "မြေအမျိုးအစားများ"],
        "အကြောင်း": ["အကြောင်း", "အကြောင်းအရာ", "အကြောင်းအရာများ", "ဘာလဲ"],
        "အသုံးပြုသည့်အစိတ်အပိုင်း": ["အစိတ်အပိုင်း", "အစိတ်အပိုင်းများ", "ဘယ်အစိတ်အပိုင်း", "ဘယ်အစိတ်အပိုင်းများ"],
        "ဆေးဖက်ဝင်အာနိသင်": ["ဆေးဖက်ဝင်အာနိသင်", "ဆေးဖက်ဝင်အာနိသင်များ", "ဘယ်ဆေးဖက်ဝင်အာနိသင်", "ဘယ်ဆေးဖက်ဝင်အာနိသင်များ"],
        "အသုံးပြုပုံ": ["အသုံးပြုပုံ", "အသုံးပြုပုံများ", "ဘယ်လိုအသုံးပြုရမလဲ", "ဘယ်လိုအသုံးပြုပုံ", "ဘယ်လိုအသုံးပြုပုံများ"],
        "ဓာတ်မြေဩဇာသုံးစွဲခြင်း": ["ဓာတ်မြေဩဇာ", "ဓာတ်မြေဩဇာသုံးစွဲခြင်း", "ဘယ်လိုဓာတ်မြေဩဇာသုံးစွဲရမလဲ"],
        "ရေသွင်းခြင်း": ["ရေသွင်းခြင်း", "ရေသွင်းနည်း", "ဘယ်လိုရေသွင်းရမလဲ"],
        "ရာသီဥတု": ["ရာသီဥတု", "ရာသီဥတုအခြေအနေ", "ဘယ်လိုရာသီဥတု"],
        "ရိတ်သိမ်းခြင်း": ["ရိတ်သိမ်းခြင်း", "ရိတ်သိမ်းနည်း", "ဘယ်လိုရိတ်သိမ်းရမလဲ"],
    }

    @classmethod
    def _initialize_keys(cls):
        if cls._key_iter is None:
            keys = []
            for i in itertools.count(1):
                key = os.getenv(f"API_KEY_{i}")
                if not key:
                    break
                keys.append(key)
            if not keys and os.getenv("API_KEY"):
                keys.append(os.getenv("API_KEY"))
            if not keys:
                raise ValueError("API Key တစ်ခုမှ ရှာမတွေ့ပါ။")
            cls._key_iter = itertools.cycle(keys)

    @classmethod
    def get_retriever(cls):
        if cls._retriever is None:
            if not os.path.exists(RETRIEVER_PATH):
                return None
            with open(RETRIEVER_PATH, "rb") as f:
                all_docs = pickle.load(f)
            
            cls._all_docs_cache = all_docs
            # Custom tokenize ကို ဖြုတ်ပြီး LangChain ရဲ့ Default BM25 ကိုသာ သုံးမည်
            cls._retriever = BM25Retriever.from_documents(all_docs)
            cls._retriever.k = 60
        return cls._retriever

    @classmethod
    def get_genai_client(cls):
        cls._initialize_keys()
        key = next(cls._key_iter)
        return genai.Client(api_key=key)

    @classmethod
    def smart_query_processing(cls, user_query: str) -> tuple[str, str, str]:
        detected_crop = None
        detected_intent = ""

        for crop in cls.CROPS:
            if crop in user_query:
                detected_crop = crop
                break
        
        for intent_name, keywords in cls.INTENTS.items():
            for kw in keywords:
                if kw in user_query:
                    detected_intent = intent_name
                    break
            if detected_intent:
                break

        return user_query, detected_crop, detected_intent

    @classmethod
    def answer_query(cls, user_query: str) -> str:
        retriever = cls.get_retriever()
        if not retriever:
            return "Knowledge Base မရှိသေးပါ။ ingest.py ကို အရင် Run ပါ။"

        clean_query = user_query.strip()
        if not clean_query:
            return "ကျေးဇူးပြု၍ မေးခွန်း ရေးသားပေးပါ။"

        _, detected_crop, detected_intent = cls.smart_query_processing(clean_query)

        docs = []
        # ၁။ သီးနှံနှင့် Intent ကိုက်ညီပါက သက်ဆိုင်ရာ Chunk များကို Cache ထဲမှ တိုက်ရိုက်ဆွဲထုတ်မည်
        if detected_crop and detected_intent:
            print(f"-> Direct Matching for Crop: {detected_crop} & Intent: {detected_intent}")
            matching_docs = []
            for doc in cls._all_docs_cache:
                source = doc.metadata.get("source", "")
                content = doc.page_content
                if detected_crop in source:
                    if detected_intent in content or detected_intent in source:
                        matching_docs.append(doc)
            if matching_docs:
                docs = matching_docs

        # ၂။ Direct Match မရှိပါက ပုံမှန် BM25 ဖြင့် ရှာမည်
        if not docs:
            search_query = f"{detected_crop} {detected_intent}" if detected_crop and detected_intent else clean_query
            retriever.k = 60
            docs = retriever.invoke(search_query)

            if detected_crop:
                filtered_docs = [doc for doc in docs if detected_crop in doc.metadata.get("source", "")]
                if filtered_docs:
                    docs = filtered_docs

        print(f"=== DEBUG: Final Selected Docs Count: {len(docs)} ===")
        for i, doc in enumerate(docs[:3]):
            print(f"  [Final {i+1}] Source: {doc.metadata.get('source')} | Content: {doc.page_content[:120]}...")

        if not docs:
            return "ဒီအကြောင်းအရာနှင့် ပတ်သက်သည့် အချက်အလက် ဒေတာဘေ့စ်ထဲတွင် မရှိသေးပါ။"

        context_list = [doc.page_content for doc in docs]
        context_text = "\n\n---\n\n".join(context_list)

        system_instruction = (
            "You are an expert Myanmar Agricultural AI Assistant.\n\n"
            "INSTRUCTIONS:\n"
            "1. Answer the user query using ONLY the provided Context.\n"
            "2. List all relevant sections, sub-methods, or items (##, ###) found in the Context clearly in detail.\n"
            "3. Answer in full, natural, polite Myanmar language.\n"
            "4. Only if the Context lacks any relevant info, reply: 'ဒီအကြောင်းအရာနှင့် ပတ်သက်သည့် အချက်အလက် ဒေတာဘေ့စ်ထဲတွင် မရှိသေးပါ။'\n\n"
            f"Context:\n{context_text}"
        )

        max_retries = 6
        for attempt in range(max_retries):
            try:
                client = cls.get_genai_client()
                response = client.models.generate_content(
                    model="models/gemini-3.6-flash",
                    contents=clean_query,
                    config=types.GenerateContentConfig(
                        system_instruction=system_instruction,
                        temperature=0.2,
                        max_output_tokens=4096,
                    ),
                )
                return response.text
            except Exception as e:
                error_msg = str(e)
                if "429" in error_msg or "RESOURCE_EXHAUSTED" in error_msg:
                    continue
                else:
                    # return f"LLM Error: {error_msg}"
                    return f"LLM Error: {error_msg}"
        
        return "တောင်းပန်ပါတယ်၊ LLM connectionကို ခဏစောင့်ပြီးမှ ထပ်ကြိုးစားပေးပါ။"