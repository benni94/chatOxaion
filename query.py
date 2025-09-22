import pickle
import faiss
import numpy as np
from sentence_transformers import SentenceTransformer
import subprocess

from pathlib import Path

META_FILE = Path("data/meta.pkl")
FAISS_INDEX_FILE = Path("data/faiss.index")
EMBEDDING_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
OLLAMA_MODEL = "phi3:mini"  # pick a small model installed in Ollama


def load_data():
    with open(META_FILE, "rb") as f:
        chunks = pickle.load(f)
    index = faiss.read_index(str(FAISS_INDEX_FILE))
    return chunks, index


def retrieve(query: str, top_k=3):
    model = SentenceTransformer(EMBEDDING_MODEL_NAME)
    q_emb = model.encode([query]).astype("float32")
    chunks, index = load_data()

    D, I = index.search(q_emb, top_k)
    results = [chunks[idx] for idx in I[0]]
    return results


def build_prompt(query: str, contexts):
    ctx_text = "\n\n".join(
        [f"Source: {c['url']} | {c['title']}\n{c['content']}" for c in contexts]
    )
    prompt = f"""You are a helpful assistant.
Use the following documentation snippets to answer the question.

{ctx_text}

Question: {query}
Answer:"""
    return prompt


def ask_ollama(prompt: str, model: str = OLLAMA_MODEL):
    cmd = ["ollama", "run", model]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    out, _ = proc.communicate(prompt)
    return out


if __name__ == "__main__":
    query = input("❓ Ask something about Oxaion Docs: ")
    results = retrieve(query, top_k=3)
    prompt = build_prompt(query, results)
    answer = ask_ollama(prompt)
    print("\n🧠 Answer:\n", answer)
