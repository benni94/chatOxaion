import sys
import os
import pickle
import faiss
import numpy as np
from pathlib import Path
from sentence_transformers import SentenceTransformer
import re

# ─── Add crawl4ai/src to sys.path ───────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CRAWL4AI_SRC = os.path.join(BASE_DIR, "crawl4ai", "src")
if CRAWL4AI_SRC not in sys.path:
    sys.path.insert(0, CRAWL4AI_SRC)

# ─── Paths ─────────────────────────────────────────────────────
DOCS_DIR = Path("data/docs")
META_FILE = Path("data/meta.pkl")
INDEX_FILE = Path("data/faiss.index")

# ─── Embedding Model ───────────────────────────────────────────
# Multilingual model for better cross-lingual matching (EN queries ↔ DE docs)
model = SentenceTransformer("sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")

# ─── Helper Functions ─────────────────────────────────────────
def clean_text(text: str) -> str:
    """
    Remove Confluence navigation, search bars, login links, images,
    and any leftover bullet list headers.
    """
    # Keep from the first real heading onward
    m = re.search(r'^\s*#\s+.+', text, flags=re.MULTILINE)
    if m:
        text = text[m.start():]

    # Remove image links
    text = re.sub(r'!\[.*?\]\(.*?\)', '', text)
    # Remove login and utility links
    text = re.sub(r'\[(?:Anmelden|Login|Abmelden)\]\(.*?\)', '', text, flags=re.IGNORECASE)
    # Remove menu-like bullet links (allow leading spaces and different bullets)
    text = re.sub(r'^[ \t]*[\*\-•]\s*\[.*?\]\(.*?\).*$','', text, flags=re.MULTILINE)
    # Remove common Confluence boilerplate tokens
    text = re.sub(r'(Onlinehilfe|Tastenkombinationen|Feed\-Builder|Suche\s*\.{3})', '', text, flags=re.IGNORECASE)
    # Remove empty anchor lines: [](...)
    text = re.sub(r'^\s*\[\]\(.*?\)\s*$', '', text, flags=re.MULTILINE)
    # Collapse multiple newlines
    text = re.sub(r'\n{2,}', '\n\n', text)
    return text.strip()

def chunk_markdown(md_text: str):
    """Split markdown by headings (#, ##, ###...) into chunks with titles."""
    lines = md_text.splitlines()
    chunks = []
    current_title = None
    current_lines = []
    for line in lines:
        if re.match(r'^\s*#+\s+', line):
            # flush previous
            if current_lines and current_title:
                chunks.append((current_title, clean_text("\n".join(current_lines).strip())))
            current_title = line.strip()
            current_lines = []
        else:
            current_lines.append(line)
    if current_lines:
        title = current_title or "# Inhalt"
        chunks.append((title, clean_text("\n".join(current_lines).strip())))
    # Drop empty chunks
    return [(t, c) for t, c in chunks if c]

def build_index():
    """
    Build FAISS index from markdown chunks in data/docs using cosine similarity
    """
    print("🔍 Building FAISS index...")
    meta = []  # list of dicts: {path, title, content}
    texts = []
    for md_file in DOCS_DIR.glob("*.md"):
        if "_src_" in md_file.name:
            continue
        md_text = md_file.read_text(encoding="utf-8", errors="ignore")
        chunks = chunk_markdown(md_text)
        for title, content in chunks:
            meta.append({"path": str(md_file), "title": title, "content": content})
            texts.append(f"{title}\n\n{content}")

    if not texts:
        # Create an empty index to avoid crashing
        dim = 384  # default for MiniLM models
        index = faiss.IndexFlatIP(dim)
        with open(META_FILE, "wb") as f:
            pickle.dump(meta, f)
        faiss.write_index(index, str(INDEX_FILE))
        print("⚠️ No documents found to index.")
        return

    # Compute embeddings and normalize for cosine similarity
    embeddings = model.encode(texts, convert_to_numpy=True)
    embeddings = embeddings.astype("float32")
    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    embeddings = embeddings / norms

    # Build FAISS index with Inner Product (cosine on normalized vectors)
    dim = embeddings.shape[1]
    index = faiss.IndexFlatIP(dim)
    index.add(embeddings)

    # Save metadata and index
    with open(META_FILE, "wb") as f:
        pickle.dump(meta, f)
    faiss.write_index(index, str(INDEX_FILE))

    print(f"✅ Index built: {len(texts)} chunks indexed from {len(set([m['path'] for m in meta]))} files.")

def load_data():
    """
    Load FAISS index + metadata. Rebuild if missing or corrupted.
    """
    if not META_FILE.exists() or not INDEX_FILE.exists():
        build_index()

    try:
        with open(META_FILE, "rb") as f:
            meta = pickle.load(f)
    except EOFError:
        print("⚠️ meta.pkl is corrupted. Rebuilding index...")
        build_index()
        with open(META_FILE, "rb") as f:
            meta = pickle.load(f)

    index = faiss.read_index(str(INDEX_FILE))
    return meta, index

def retrieve(query: str, top_k: int = 3):
    """
    Retrieve top_k most relevant chunks for a query using cosine similarity
    """
    meta, index = load_data()
    query_vec = model.encode([query], convert_to_numpy=True).astype("float32")
    qn = np.linalg.norm(query_vec, axis=1, keepdims=True)
    qn[qn == 0] = 1.0
    query_vec = query_vec / qn
    D, I = index.search(query_vec, top_k)

    results = []
    for i in I[0]:
        if 0 <= i < len(meta):
            results.append(meta[i])
    return results

# ─── Main ──────────────────────────────────────────────────────
if __name__ == "__main__":
    # If old index exists but is unclean, delete to rebuild
    if not META_FILE.exists() or not INDEX_FILE.exists():
        build_index()

    query = input("❓ Ask something about Oxaion Docs: ").strip()
    results = retrieve(query, top_k=3)

    print("\n📄 Results:")
    for item in results:
        title = item.get("title", "# Abschnitt")
        path = item.get("path", "")
        content = item.get("content", "")
        snippet = content[:400].replace("\n", " ") + ("..." if len(content) > 400 else "")
        print(f"- {title} — {path}\n  {snippet}")
