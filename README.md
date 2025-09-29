### Directory Layout:

```
oxaion_rag/
├── crawler.py          # crawl + chunk + embed + save
├── query.py            # retrieve + ask Ollama
├── app.py              # Gradio GUI with chat history and sources
├── start.sh            # macOS/Linux starter
├── Start Chat.command  # macOS double‑click launcher
├── start.cmd           # Windows starter (double‑click)
├── Makefile            # helper commands
├── data/
│   ├── docs/           # raw markdown per page (with <!-- source: URL --> header)
│   ├── faiss.index     # FAISS vector DB
│   └── meta.pkl        # mapping chunks -> URLs, titles, content (chunk-level)
```

### Requirements
Works with the [Crawl4Ai](https://github.com/unclecode/crawl4ai) GitHub repo (auto-cloned by the installer).

---

## Quick Start (GUI)

### macOS/Linux
1. Make the starter executable once:
   ```bash
   chmod +x start.sh "Start Chat.command"
   ```
2. Launch (terminal):
   ```bash
   ./start.sh
   ```
   or double‑click `Start Chat.command` in Finder.

### Windows
1. Double‑click `start.cmd` in Explorer (or run from cmd).

The app starts at:
- http://127.0.0.1:7860

---

## CLI Usage

- Build/install dependencies:
  ```bash
  python3 install_dependencies.py
  ```
- Crawl docs (saves markdown with source URLs):
  ```bash
  ./venv/bin/python crawler.py
  ```
- Rebuild index and query from terminal:
  ```bash
  rm data/meta.pkl data/faiss.index
  ./venv/bin/python query.py
  ```

---

## Notes
- Sources in the GUI and CLI show the original documentation URLs, extracted from a header comment inserted into each markdown: `<!-- source: https://... -->`.
- Retrieval uses multilingual embeddings, chunking by headings, cosine similarity, and cleaned markdown for higher quality matches.
- To change the Ollama model, edit `app.py` or toggle in the UI.

---
## Direct Download (latest release)

You can download the latest version of the chatbot from the GitHub releases page:

https://github.com/benni94/chatOxaion/releases/latest

After downloading the latest version, follow these steps:

1. Place the `data.zip` file in the extracted folder.
2. Double-click the `Install.command` file to install the chatbot.
3. Once the installation is complete, double-click the `Start Chat.command` file to start the chatbot.
