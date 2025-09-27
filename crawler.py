import sys
import os
import asyncio
from collections import deque
from urllib.parse import urldefrag, urljoin
from pathlib import Path

# ─── Add local crawl4ai package to sys.path ─────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CRAWL4AI_PKG_ROOT = os.path.join(BASE_DIR, "crawl4ai")
if CRAWL4AI_PKG_ROOT not in sys.path:
    sys.path.insert(0, CRAWL4AI_PKG_ROOT)

# ─── Now safe to import Crawl4AI ────────────────────────────────
from crawl4ai.async_webcrawler import AsyncWebCrawler
from crawl4ai.async_configs import CrawlerRunConfig, BrowserConfig
from crawl4ai.cache_context import CacheMode
from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator


# ─── Setup ─────────────────────────────────────────────────────
START_URL = "https://docs.oxaion.de/spaces/open/overview"
ALLOWED_PREFIX = "https://docs.oxaion.de/spaces/open/"
DOCS_DIR = Path("data/docs")
DOCS_DIR.mkdir(parents=True, exist_ok=True)


async def crawl_all():
    """
    Crawl Oxaion Docs and save each page as Markdown
    """
    print(f"[CRAWL] Starting at {START_URL}")
    # Use text_mode to speed up rendering (disables images/remote fonts; may disable JS)
    async with AsyncWebCrawler(config=BrowserConfig(text_mode=True, headless=True, verbose=False)) as crawler:
        # Relax page load condition and increase timeout to avoid navigation timeouts
        config = CrawlerRunConfig(
            markdown_generator=DefaultMarkdownGenerator(),
            cache_mode=CacheMode.BYPASS,  # always fetch fresh
            wait_until="load",           # wait for full load; more stable than 'domcontentloaded' here
            page_timeout=180000,          # 180s navigation timeout
            check_robots_txt=False,       # skip robots.txt check for speed/reliability
            ignore_body_visibility=True,  # don't fail if body considered hidden
            verbose=False,
            # Set a realistic UA to reduce bot-block issues
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
        )

        # BFS crawl with queue/visited to go beyond one level
        queue = deque([START_URL])
        visited = set()

        # Crawl without a page limit (may take a long time)
        while queue:
            url = queue.popleft()
            # avoid re-processing
            if url in visited:
                continue
            visited.add(url)

            # Retry a few times on transient navigation issues/timeouts
            result = None
            for attempt in range(3):
                try:
                    result = await crawler.arun(url, config=config)
                    break
                except Exception as e:
                    print(f"[ERROR] Fetch failed for {url} (attempt {attempt+1}/3): {e}")
                    await asyncio.sleep(2 * (attempt + 1))
            if not result:
                continue

            if result and result.success and result.markdown:
                save_markdown(url, result.markdown.raw_markdown)

            # extract and enqueue next links (resolve relative URLs against the current page)
            next_links = extract_link_urls(getattr(result, "links", None)) if result else []
            base_url = getattr(result, "redirected_url", None) or url
            enqueued = 0
            for href in next_links:
                if not isinstance(href, str):
                    continue
                # resolve relative links and strip fragments
                full_url = urljoin(base_url, href)
                full_url, _ = urldefrag(full_url)
                if full_url.startswith(ALLOWED_PREFIX) and full_url not in visited and full_url not in queue:
                    queue.append(full_url)
                    enqueued += 1
            if enqueued:
                print(f"[QUEUE] {url} → added {enqueued} links (queue size: {len(queue)})")


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
    # Prepend a source URL comment if not already present
    header = f"<!-- source: {url} -->\n"
    if not content.lstrip().startswith("<!-- source:"):
        content_to_write = header + content
    else:
        content_to_write = content
    path.write_text(content_to_write, encoding="utf-8")
    print(f"[SAVED] {url} → {path}")


def extract_link_urls(links) -> list:
    """Best-effort extraction of URLs from Crawl4AI links structure.
    Supports both dict-based and object-based schemas and plain strings.
    """
    urls = []
    if links is None:
        return urls
    def add_item(item):
        if isinstance(item, str):
            urls.append(item)
        elif isinstance(item, dict):
            for key in ("href", "url", "link", "src"):
                val = item.get(key)
                if isinstance(val, str):
                    urls.append(val)
                    return
        else:
            for attr in ("href", "url"):
                val = getattr(item, attr, None)
                if isinstance(val, str):
                    urls.append(val)
                    return

    if isinstance(links, dict):
        for group in links.values():
            if isinstance(group, list):
                for it in group:
                    add_item(it)
    elif isinstance(links, list):
        for it in links:
            add_item(it)

    # dedupe while preserving order
    seen = set()
    uniq = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            uniq.append(u)
    return uniq


# ─── Run script ─────────────────────────────────────────────────
if __name__ == "__main__":
    asyncio.run(crawl_all())
