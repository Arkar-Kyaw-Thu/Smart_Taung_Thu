import os
import pickle
import re
from dotenv import load_dotenv
from langchain_community.retrievers import BM25Retriever
from langchain_text_splitters import MarkdownHeaderTextSplitter

load_dotenv()

DATA_PATH = os.path.join(os.path.dirname(__file__), "data")
RETRIEVER_PATH = os.path.join(os.path.dirname(__file__), "bm25_retriever.pkl")

# Regex Tokenizer Function
def tokenize_mm(text: str) -> str:
    tokens = re.findall(r'[\u1000-\u104f]+|[a-zA-Z0-9]+', text)
    return " ".join(tokens)

def create_bm25_db():
    if not os.path.exists(DATA_PATH):
        os.makedirs(DATA_PATH)
        print(f"📁 {DATA_PATH} ဖိုင်တွဲ ဖန်တီးလိုက်ပါပြီ။ .txt ဖိုင်များ ထည့်ပါ။")
        return

    # ခေါင်းစဉ် (Header) အလိုက် ပိုင်းဖြတ်ခြင်း
    headers_to_split_on = [
        ("#", "Header 1"),
        ("##", "Header 2"),
        ("###", "Header 3"),
    ]
    
    markdown_splitter = MarkdownHeaderTextSplitter(
        headers_to_split_on=headers_to_split_on, 
        strip_headers=False
    )

    all_docs = []

    for root, _, files in os.walk(DATA_PATH):
        for file in files:
            if file.endswith(".txt"):
                file_path = os.path.join(root, file)
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()

                docs = markdown_splitter.split_text(content)
                for doc in docs:
                    # ခေါင်းစဉ် Metadata များကို page_content ထဲသို့ ပေါင်းထည့်ခြင်း (BM25 ဖြင့် အလွယ်တကူ ရှာတွေ့စေရန်)
                    header_prefix = ""
                    for key in ["Header 1", "Header 2", "Header 3"]:
                        if key in doc.metadata:
                            header_prefix += f"{doc.metadata[key]} "
                    
                    doc.page_content = header_prefix + "\n" + doc.page_content
                    doc.metadata["source"] = file
                    all_docs.append(doc)

    print(f"📦 Header အလိုက် စုစည်းထားသော Chunk အရေအတွက်: {len(all_docs)}")

    # pickle ဖြင့် retriever_path သို့ သိမ်းဆည်းခြင်း
    with open(RETRIEVER_PATH, "wb") as f:
        pickle.dump(all_docs, f)

    print("✅ Header-based Ingestion အောင်မြင်စွာ ပြီးစီးပါပြီ။")

if __name__ == "__main__":
    create_bm25_db()