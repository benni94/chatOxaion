import asyncio
import pickle
from pathlib import Path
from typing import List, Dict, Set
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode
from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator
from crawl4ai.content_filter_strategy import PruningContentFilter

from sentence_transformers import SentenceTransformer
import faiss
import numpy as np
import re

def safe_filename(url: str) -> str:
    # Strip domain
    fname = url.replace("https://docs.oxaion.de/", "")
    # Replace unsafe chars with "_"
    fname = re.sub(r'[^a-zA-Z0-9_-]', "_", fname)
    return fname


BASE_URL = "https://docs.oxaion.de/spaces/open/overview"
DOMAIN_PREFIX = "https://docs.oxaion.de/spaces/open/"

DATA_DIR = Path("data")
DOCS_DIR = DATA_DIR / "docs"
META_FILE = DATA_DIR / "meta.pkl"
FAISS_INDEX_FILE = DATA_DIR / "faiss.index"

EMBEDDING_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"


def is_internal_link(url: str) -> bool:
    return url.startswith(DOMAIN_PREFIX)


def extract_links(html: str, base_url: str) -> Set[str]:
    """Extract all internal links from a page."""
    soup = BeautifulSoup(html, "html.parser")
    links = set()
    for a in soup.find_all("a", href=True):
        href = urljoin(base_url, a["href"])
        if is_internal_link(href):
            links.add(href.split("#")[0])  # strip fragments
    return links


def chunk_by_headings(markdown: str, url: str) -> List[Dict]:
    """Split markdown by headings (#, ##, ###...) into semantically meaningful chunks."""
    chunks = []
    lines = markdown.splitlines()
    current_chunk = []
    current_title = "Introduction"

    for line in lines:
        if line.startswith("#"):
            if current_chunk:
                chunks.append({
                    "title": current_title,
                    "content": "\n".join(current_chunk).strip(),
                    "url": url
                })
                current_chunk = []
            current_title = line.strip()
        else:
            current_chunk.append(line)

    if current_chunk:
        chunks.append({
            "title": current_title,
            "content": "\n".join(current_chunk).strip(),
            "url": url
        })

    return chunks


async def crawl_all():
    DATA_DIR.mkdir(exist_ok=True)
    DOCS_DIR.mkdir(exist_ok=True)

    visited: Set[str] = set()
    to_visit: Set[str] = {BASE_URL}
    all_chunks = []

    model = SentenceTransformer(EMBEDDING_MODEL_NAME)
    embeddings_list = []

    browser_cfg = BrowserConfig(headless=True, verbose=False)
    filter_cfg = PruningContentFilter(threshold=0.5, threshold_type="fixed", min_word_threshold=10)
    md_generator = DefaultMarkdownGenerator(content_filter=filter_cfg)
    run_cfg = CrawlerRunConfig(cache_mode=CacheMode.ENABLED, markdown_generator=md_generator)

    async with AsyncWebCrawler(config=browser_cfg) as crawler:
        while to_visit:
            url = to_visit.pop()
            if url in visited:
                continue
            visited.add(url)

            print(f"[CRAWL] {url}")
            result = await crawler.arun(url=url, config=run_cfg)

            if not result or not result.markdown:
                print(f"⚠️ Skipping {url} (no markdown)")
                continue

            raw_markdown = result.markdown.raw_markdown
            raw_html = result.html

            # save markdown
            # inside crawl_all
            fname = safe_filename(url)
            (DOCS_DIR / f"{fname}.md").write_text(raw_markdown, encoding="utf-8")

            # chunk
            chunks = chunk_by_headings(raw_markdown, url)
            all_chunks.extend(chunks)

            # embed
            emb = model.encode([c["content"] for c in chunks])
            embeddings_list.append(np.array(emb, dtype="float32"))

            # discover more links
            for link in extract_links(raw_html, url):
                if link not in visited:
                    to_visit.add(link)

    # combine embeddings
    if embeddings_list:
        embeddings = np.vstack(embeddings_list)
        dim = embeddings.shape[1]
        index = faiss.IndexFlatL2(dim)
        index.add(embeddings)

        # save
        faiss.write_index(index, str(FAISS_INDEX_FILE))
        with open(META_FILE, "wb") as f:
            pickle.dump(all_chunks, f)

        print(f"✅ Crawled {len(visited)} pages, {len(all_chunks)} chunks saved.")
    else:
        print("⚠️ No embeddings created.")


if __name__ == "__main__":
    asyncio.run(crawl_all())
