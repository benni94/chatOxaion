### Directory Layout:

oxaion_rag/
├── crawler.py          # crawl + chunk + embed + save
├── query.py            # retrieve + ask Ollama
├── data/
│   ├── docs/           # raw markdown per page
│   ├── faiss.index     # FAISS vector DB
│   └── meta.pkl        # mapping chunks -> URLs, etc.

### Required repo:
Works with the [Crawl4Ai](https://github.com/unclecode/crawl4ai) github repo.
