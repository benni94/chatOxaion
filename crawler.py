import sys
import os
import asyncio
from pathlib import Path

# ─── Add crawl4ai/src to sys.path ───────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CRAWL4AI_SRC = os.path.join(BASE_DIR, "crawl4ai", "src")
if CRAWL4AI_SRC not in sys.path:
    sys.path.insert(0, CRAWL4AI_SRC)

# ─── Now safe to import Crawl4AI ────────────────────────────────
from crawl4ai.async_webcrawler import AsyncWebCrawler
from crawl4ai.models import CrawlerRunConfig, CacheMode
from crawl4ai.parsers import DefaultMarkdownParser


# ─── Setup ─────────────────────────────────────────────────────
START_URL = "https://docs.oxaion.de/spaces/open/overview"
DOCS_DIR = Path("data/docs")
DOCS_DIR.mkdir(parents=True, exist_ok=True)


async def crawl_all():
    """
    Crawl Oxaion Docs and save each page as Markdown
    """
    print(f"[CRAWL] Starting at {START_URL}")
    async with AsyncWebCrawler() as crawler:
        config = CrawlerRunConfig(
            parser=DefaultMarkdownParser(),
            cache_mode=CacheMode.BYPASS,  # always fetch fresh
        )

        # crawl the start page
        result = await crawler.arun(START_URL, config=config)
        if result.success:
            save_markdown(START_URL, result.markdown.raw_markdown)

        # recursively crawl links
        for link in result.links:
            if link.url.startswith("https://docs.oxaion.de/spaces/open/"):
                sub = await crawler.arun(link.url, config=config)
                if sub.success:
                    save_markdown(link.url, sub.markdown.raw_markdown)


def safe_filename(url: str) -> str:
    """
    Convert a URL into a safe filename
    """
    return url.replace("https://", "").replace("/", "_").replace("?", "_").replace(":", "_")


def save_markdown(url: str, content: str):
    """
    Save Markdown content to the docs directory
    """
    fname = safe_filename(url) + ".md"
    path = DOCS_DIR / fname
    path.write_text(content, encoding="utf-8")
    print(f"[SAVED] {url} → {path}")


# ─── Run script ─────────────────────────────────────────────────
if __name__ == "__main__":
    asyncio.run(crawl_all())
