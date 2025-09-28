import sys
import os
import pickle
import numpy as np
from pathlib import Path
from sentence_transformers import SentenceTransformer
import re
import json
import time
import hashlib
import chromadb
from chromadb.config import Settings
import requests

# ─── Add crawl4ai/src to sys.path ───────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CRAWL4AI_SRC = os.path.join(BASE_DIR, "crawl4ai", "src")
if CRAWL4AI_SRC not in sys.path:
    sys.path.insert(0, CRAWL4AI_SRC)

# ─── Paths ─────────────────────────────────────────────────────
DOCS_DIR = Path("data/docs")
META_FILE = Path("data/meta.pkl")
# Maintain an INDEX_FILE path for compatibility with app.py checks,
# but use a marker file inside the Chroma directory instead of a FAISS index
CHROMA_DIR = Path("data/chroma")
INDEX_FILE = CHROMA_DIR / "INDEX_EXISTS"
MANIFEST_FILE = CHROMA_DIR / "manifest.json"

# ─── Embedding Model ───────────────────────────────────────────
# Multilingual model for better cross-lingual matching (EN queries ↔ DE docs)
model = SentenceTransformer("sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
DEFAULT_EMBED_MODEL = os.environ.get("EMBED_MODEL", "nomic-embed-text")

# Chroma settings
COLLECTION_NAME = "oxaion-docs"

def _chroma_client():
    CHROMA_DIR.mkdir(parents=True, exist_ok=True)
    # Disable anonymized telemetry to avoid PostHog network calls
    settings = Settings(anonymized_telemetry=False)
    return chromadb.PersistentClient(path=str(CHROMA_DIR), settings=settings)

def _ollama_server_up(timeout: float = 2.0) -> bool:
    try:
        r = requests.get("http://localhost:11434/api/tags", timeout=timeout)
        return r.status_code == 200
    except Exception:
        return False

def _ollama_embed(texts: list[str], model_name: str) -> np.ndarray:
    url = "http://localhost:11434/api/embeddings"
    vecs = []
    for t in texts:
        payload = {"model": model_name, "prompt": t}
        try:
            resp = requests.post(url, json=payload, timeout=120)
            if resp.status_code != 200:
                raise RuntimeError(f"Ollama HTTP {resp.status_code}: {resp.text[:180]}")
            data = resp.json() or {}
            emb = data.get("embedding")
            if not emb:
                raise RuntimeError("No embedding returned")
            vecs.append(emb)
        except Exception as e:
            raise e
    arr = np.array(vecs, dtype="float32")
    return arr

def _embed_texts(texts: list[str]) -> np.ndarray:
    """Try Ollama embeddings first; fallback to SentenceTransformers. Returns normalized vectors."""
    if _ollama_server_up():
        try:
            arr = _ollama_embed(texts, DEFAULT_EMBED_MODEL)
            # normalize
            norms = np.linalg.norm(arr, axis=1, keepdims=True)
            norms[norms == 0] = 1.0
            arr = arr / norms
            return arr
        except Exception:
            # Fallback below
            pass
    # SentenceTransformers fallback
    arr = model.encode(texts, convert_to_numpy=True).astype("float32")
    norms = np.linalg.norm(arr, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    arr = arr / norms
    return arr

def _embed_query(text: str) -> list:
    arr = _embed_texts([text])
    return arr.tolist()

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

def _chunk_id(path: str, title: str, content: str) -> str:
    h = hashlib.md5((path + "\n" + (title or "") + "\n" + (content or "")).encode("utf-8")).hexdigest()
    return f"{Path(path).name}:{h}"

def _load_manifest() -> dict:
    if not MANIFEST_FILE.exists():
        return {"files": {}}
    try:
        return json.loads(MANIFEST_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"files": {}}

def _save_manifest(manifest: dict):
    MANIFEST_FILE.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_FILE.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

def _collect_all_metadatas(collection) -> list:
    try:
        got = collection.get(include=["metadatas"])
        mds = got.get("metadatas") or []
        # Flatten single-level list
        return mds
    except Exception:
        return []

def _sanitize_meta(d: dict) -> dict:
    """Ensure metadata values are of allowed types (str/bool/int/float) and not None."""
    out = {}
    for key in ("path", "url", "title", "content"):
        val = d.get(key)
        if val is None:
            out[key] = ""
        else:
            # Coerce to string for consistency
            out[key] = str(val)
    return out

def build_index():
    """
    Incremental build of ChromaDB collection from Markdown files.
    - Adds/updates chunks for modified files
    - Removes chunks for deleted files
    - Persists a manifest for fast detection
    """
    print("🔍 Incremental indexing with ChromaDB…")

    client = _chroma_client()
    collection = client.get_or_create_collection(COLLECTION_NAME)

    manifest = _load_manifest()
    known_files = set(manifest.get("files", {}).keys())
    current_files = sorted([str(p) for p in DOCS_DIR.glob("*.md") if "_src_" not in p.name])
    current_set = set(current_files)

    # Handle modifications and additions
    for path in current_files:
        p = Path(path)
        try:
            md_text = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        m = re.search(r"<!--\s*source:\s*(.*?)\s*-->", md_text, flags=re.IGNORECASE)
        source_url = m.group(1).strip() if m else None
        chunks = chunk_markdown(md_text)

        # Build desired state for this file (IDs are content-hash + stable index to avoid duplicates)
        new_ids = []
        new_docs = []
        new_metas = []
        for idx, (title, content) in enumerate(chunks):
            base = _chunk_id(path, title, content)
            cid = f"{base}:{idx}"
            new_ids.append(cid)
            new_docs.append(f"{title}\n\n{content}")
            new_metas.append(_sanitize_meta({"path": path, "url": source_url, "title": title, "content": content}))

        # Fetch existing chunk ids for this file
        try:
            existing = collection.get(where={"path": path}, include=["metadatas", "documents"])
            existing_ids = set(existing.get("ids") or [])
        except Exception:
            existing_ids = set()

        new_id_set = set(new_ids)
        to_delete = list(existing_ids - new_id_set)
        to_add_mask = [cid not in existing_ids for cid in new_ids]

        # Delete removed chunks
        if to_delete:
            try:
                collection.delete(ids=to_delete)
            except Exception:
                pass

        # Add new/changed chunks
        if any(to_add_mask):
            add_ids = [cid for cid, m in zip(new_ids, to_add_mask) if m]
            add_docs = [doc for doc, m in zip(new_docs, to_add_mask) if m]
            add_metas = [mt for mt, m in zip(new_metas, to_add_mask) if m]
            # Deduplicate within batch to avoid any accidental duplicates
            unique = {}
            for cid, doc, meta in zip(add_ids, add_docs, add_metas):
                unique[cid] = (doc, meta)
            add_ids = list(unique.keys())
            add_docs = [unique[cid][0] for cid in add_ids]
            add_metas = [unique[cid][1] for cid in add_ids]
            # Defensive: delete any of these IDs if they already exist to avoid DuplicateIDError
            try:
                if add_ids:
                    collection.delete(ids=add_ids)
            except Exception:
                pass
            # Embed only the new docs (via Ollama or ST)
            embeddings = _embed_texts(add_docs)
            collection.add(ids=add_ids, documents=add_docs, metadatas=add_metas, embeddings=embeddings.tolist())

        # Update manifest for this file
        manifest.setdefault("files", {})[path] = {
            "mtime": p.stat().st_mtime,
            "ids": new_ids,
        }

    # Handle deletions for files removed from docs directory
    removed_files = known_files - current_set
    for path in removed_files:
        try:
            collection.delete(where={"path": path})
        except Exception:
            pass
        manifest["files"].pop(path, None)

    # Save META_FILE from collection snapshot
    all_meta = _collect_all_metadatas(collection)
    with open(META_FILE, "wb") as f:
        pickle.dump(all_meta, f)

    # Write manifest and index marker
    _save_manifest(manifest)
    INDEX_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not INDEX_FILE.exists():
        INDEX_FILE.write_text("ok", encoding="utf-8")

    total_chunks = sum(len(entry.get("ids", [])) for entry in manifest.get("files", {}).values())
    print(f"✅ Incremental index complete: {total_chunks} chunks across {len(manifest.get('files', {}))} files.")

def load_data():
    """
    Ensure Chroma collection and metadata are available. Rebuild if missing/corrupted.
    Returns the Chroma collection and metadata list.
    """
    if not META_FILE.exists() or not INDEX_FILE.exists():
        build_index()

    try:
        with open(META_FILE, "rb") as f:
            meta = pickle.load(f)
    except Exception:
        print("⚠️ meta.pkl missing or corrupted. Rebuilding index...")
        build_index()
        with open(META_FILE, "rb") as f:
            meta = pickle.load(f)

    client = _chroma_client()
    collection = client.get_or_create_collection(COLLECTION_NAME)
    return meta, collection

def retrieve(query: str, top_k: int = 3):
    """
    Retrieve top_k most relevant chunks via Chroma collection.
    Returns a list of dicts with keys: path, url, title, content.
    """
    meta, collection = load_data()
    # Encode query consistent with index embeddings
    query_vec = _embed_query(query)

    res = collection.query(query_embeddings=query_vec, n_results=top_k)
    metadatas = res.get("metadatas") or []
    if not metadatas:
        return []
    items = metadatas[0]
    # Ensure structure compatibility
    results = []
    for it in items:
        results.append({
            "path": it.get("path"),
            "url": it.get("url"),
            "title": it.get("title"),
            "content": it.get("content"),
        })
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
        url = item.get("url") or item.get("path", "")
        content = item.get("content", "")
        snippet = content[:400].replace("\n", " ") + ("..." if len(content) > 400 else "")
        print(f"- {title} — {url}\n  {snippet}")
