import os
import sys
import subprocess
from pathlib import Path
from typing import List, Tuple

import gradio as gr
from urllib.parse import urlparse
import re
import requests
import threading
import json
import shutil
import time

# ─── Translations ───────────────────────────────────────────────
TRANSLATIONS = {
    "en": {
        "app_title": "# Oxaion Docs Assistant",
        "app_desc": (
            "Ask questions about the Oxaion documentation. The assistant retrieves the most relevant sections.\n"
            "- Toggle Ollama to generate answers with a local LLM, or leave it off for a fast extractive response.\n"
            "- Sources of the retrieved chunks are listed below each answer."
        ),
        "language_label": "Language",
        "use_ollama": "Use Ollama for generation",
        "model_label": "Ollama Model",
        "top_k": "Top-K Chunks",
        "placeholder": "Ask something about Oxaion…",
        "clear": "Clear",
        "rebuild": "Rebuild Index",
        "index_rebuilt": "Index rebuilt.",
        "sources_label": "Sources:",
        "ollama_section": "Ollama Setup",
        "start_server": "Start Ollama Server",
        "pull_model": "Pull Selected Model",
        "refresh_status": "Refresh Status",
        "status_installed": "Ollama installed: {val}",
        "status_server": "Ollama server running: {val}",
        "status_models": "Installed models: {models}",
        "status_model_available": "Selected model available: {val}",
        "install_hint": "If not installed, see https://ollama.com/download or run: brew install ollama",
        "popular_models": "Popular models",
        "use_popular": "Use Popular Model",
        "pull_instr": "To install the selected model, run: \n`ollama pull {model}`",
    },
    "de": {
        "app_title": "# Oxaion Doku-Assistent",
        "app_desc": (
            "Stellen Sie Fragen zur Oxaion-Dokumentation. Der Assistent ruft die relevantesten Abschnitte ab.\n"
            "- Aktivieren Sie Ollama, um Antworten mit einem lokalen LLM zu generieren, oder lassen Sie es für eine schnelle, extraktive Antwort deaktiviert.\n"
            "- Quellen der gefundenen Textstellen werden unter jeder Antwort aufgeführt."
        ),
        "language_label": "Sprache",
        "use_ollama": "Ollama für Generierung verwenden",
        "model_label": "Ollama-Modell",
        "top_k": "Top-K Abschnitte",
        "placeholder": "Fragen Sie etwas zu Oxaion…",
        "clear": "Leeren",
        "rebuild": "Index neu aufbauen",
        "index_rebuilt": "Index neu aufgebaut.",
        "sources_label": "Quellen:",
        "ollama_section": "Ollama Einrichtung",
        "start_server": "Ollama-Server starten",
        "pull_model": "Ausgewähltes Modell laden",
        "refresh_status": "Status aktualisieren",
        "status_installed": "Ollama installiert: {val}",
        "status_server": "Ollama-Server läuft: {val}",
        "status_models": "Installierte Modelle: {models}",
        "status_model_available": "Ausgewähltes Modell verfügbar: {val}",
        "install_hint": "Falls nicht installiert: https://ollama.com/download oder per brew install ollama",
        "popular_models": "Beliebte Modelle",
        "use_popular": "Beliebtes Modell übernehmen",
        "pull_instr": "Um das ausgewählte Modell zu installieren, führen Sie aus: \n`ollama pull {model}`",
    },
}

# Defaults
DEFAULT_MODEL = "phi4-mini"

# Common/popular Ollama models to offer as defaults/fallbacks
OLLAMA_COMMON_MODELS = [
    "phi3:mini",
    "phi4-mini",
    "tinyllama:latest",
]

# Local imports
# Ensure local path is set (already true when running `python app.py`)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

# Import from query.py
import query as rag


def format_sources(items: List[dict], lang: str = "en") -> str:
    """
    Render sources as a compact Markdown list so the Chatbot displays them
    as standard text with clickable Markdown links.
    Example:
    1. [Title](https://example.com) — example.com
    2. [Another](https://example.org) — example.org
    """
    lines = []
    def _shorten(text: str, max_len: int = 80) -> str:
        text = text.strip()
        if len(text) <= max_len:
            return text
        short = text[: max_len - 1]
        # Avoid cutting mid-word
        short = short.rsplit(" ", 1)[0].rstrip(",.;:—-_")
        return short + "…"

    def _clean_title(raw: str) -> str:
        # Remove leading markdown heading markers and extra spaces
        t = re.sub(r"^\s*#+\s*", "", raw or "").strip()
        return t

    for i, it in enumerate(items, 1):
        raw_title = (it.get("title") or "# Abschnitt").strip()
        title = _clean_title(raw_title)
        if not title:
            title = "Abschnitt"
        title = _shorten(title)
        url = (it.get("url") or "").strip()
        path = (it.get("path") or "").strip()
        content = (it.get("content") or "").strip()

        # If title is still uninformative, fallback to a snippet of the content
        if title in {"#", "##", "###", "####", "#####", "######"} or len(title) <= 1:
            if content:
                title = _shorten(content.replace("\n", " "), 80)

        if url:
            # Add domain next to link for clarity
            domain = urlparse(url).netloc or ""
            suffix = f" — {domain}" if domain else ""
            lines.append(f"1. [{title}]({url}){suffix}")
        elif path:
            # Local file path fallback: do not show the filename, only the title
            lines.append(f"1. {title}")
        else:
            lines.append(f"1. {title}")

    # Convert temporary "1." items to a proper ordered list
    numbered = []
    for idx, line in enumerate(lines, 1):
        numbered.append(line.replace("1.", f"{idx}.", 1))

    t = TRANSLATIONS.get(lang, TRANSLATIONS["en"])
    return f"{t['sources_label']}\n" + "\n".join(numbered)


def build_prompt(question: str, contexts: List[dict]) -> str:
    # Trim each chunk to keep prompt compact for faster LLM inference
    trimmed_chunks = []
    total_chars = 0
    MAX_TOTAL = 2800  # total context cap
    for c in contexts:
        title = str(c.get('title', '')).strip()
        content = str(c.get('content', '')).strip()
        # sanitize title and cap lengths
        title = re.sub(r"^\s*#+\s*", "", title)[:80]
        if len(content) > 900:
            content = content[:900].rsplit(" ", 1)[0] + "…"
        block = f"{title}:\n{content}" if title else content
        if total_chars + len(block) > MAX_TOTAL:
            # if adding whole block exceeds cap, add partially if useful
            remaining = max(0, MAX_TOTAL - total_chars)
            if remaining > 200:
                block = block[:remaining].rsplit(" ", 1)[0] + "…"
                trimmed_chunks.append(block)
            break
        trimmed_chunks.append(block)
        total_chars += len(block)

    ctx_text = "\n\n".join(trimmed_chunks)
    prompt = (
        "You are a helpful assistant. Answer the user question using the provided context snippets.\n"
        "If the answer cannot be found in the context, say you are not sure.\n\n"
        f"Context:\n{ctx_text}\n\n"
        f"Question: {question}\nAnswer in the same language as the question."
    )
    return prompt


def ask_ollama(prompt: str, model: str = DEFAULT_MODEL) -> str:
    """Call Ollama via HTTP API with keep-alive and conservative generation options."""
    url = "http://localhost:11434/api/generate"
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "keep_alive": "10m",
            "num_predict": 256,
            "num_ctx": 2048,
            "temperature": 0.2,
        },
    }
    try:
        resp = requests.post(url, json=payload, timeout=120)
        if resp.status_code != 200:
            return f"(Ollama HTTP {resp.status_code}) {resp.text[:200]}\n\nShowing retrieved context instead."
        data = resp.json()
        return data.get("response", "")
    except requests.exceptions.ConnectionError:
        return "(Ollama server not running) Showing retrieved context instead."
    except requests.exceptions.Timeout:
        return "(Ollama timed out) Showing retrieved context instead."
    except Exception as e:
        return f"(Ollama error) {e}\n\nShowing retrieved context instead."

def _warm_up_model_async(model: str):
    """Fire-and-forget small generate call to preload model into memory."""
    def _run():
        try:
            _ = ask_ollama("Warm up.", model=model)
        except Exception:
            pass
    threading.Thread(target=_run, daemon=True).start()


def ask_ollama_stream(prompt: str, model: str = DEFAULT_MODEL):
    """Stream tokens from Ollama HTTP API as they arrive."""
    url = "http://localhost:11434/api/generate"
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": True,
        "options": {
            "keep_alive": "10m",
            "num_predict": 256,
            "num_ctx": 2048,
            "temperature": 0.2,
        },
    }
    try:
        with requests.post(url, json=payload, stream=True, timeout=120) as resp:
            if resp.status_code != 200:
                yield f"(Ollama HTTP {resp.status_code}) "
                return
            for line in resp.iter_lines(decode_unicode=True):
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except Exception:
                    continue
                # Each chunk may have a 'response' token and a 'done' flag
                token = data.get("response")
                if token:
                    yield token
                if data.get("done"):
                    break
    except requests.exceptions.ConnectionError:
        yield "(Ollama server not running)"
    except requests.exceptions.Timeout:
        yield "(Ollama timed out)"
    except Exception as e:
        yield f"(Ollama error) {e}"


# ─── Ollama Status Helpers ─────────────────────────────────────
def _ollama_installed() -> bool:
    return shutil.which("ollama") is not None


def _ollama_server_up(timeout: float = 2.0) -> bool:
    try:
        r = requests.get("http://localhost:11434/api/tags", timeout=timeout)
        return r.status_code == 200
    except Exception:
        return False


def _ollama_list_models() -> list:
    try:
        r = requests.get("http://localhost:11434/api/tags", timeout=5)
        if r.status_code != 200:
            return []
        data = r.json() or {}
        return [m.get("name") for m in data.get("models", []) if m.get("name")]
    except Exception:
        return []


def _ollama_pull_model(model: str):
    """Yield progress strings while pulling a model via HTTP API (requires running server)."""
    url = "http://localhost:11434/api/pull"
    payload = {"name": model, "stream": True}
    try:
        with requests.post(url, json=payload, stream=True, timeout=300) as resp:
            if resp.status_code != 200:
                # Provide a clearer message when model tag is invalid/non-existent
                text = resp.text or ""
                if resp.status_code == 404 or "not found" in text.lower() or "no such model" in text.lower():
                    yield f"Model tag not found in Ollama registry: '{model}'. Please check the name or choose another model."
                else:
                    yield f"HTTP {resp.status_code}: {text[:200]}"
                return
            for line in resp.iter_lines(decode_unicode=True):
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except Exception:
                    continue
                status = data.get("status") or data.get("detail") or data.get("error") or ""
                if status:
                    yield status
                if data.get("completed") or data.get("status") == "success":
                    yield "Pull completed."
                    break
    except Exception as e:
        yield f"Error: {e}"


def extractive_answer(question: str, contexts: List[dict], max_chars: int = 900) -> str:
    # Simple heuristic: concatenate the most relevant chunks and trim
    text = "\n\n".join([c.get("content", "") for c in contexts])
    text = text.strip()
    if len(text) > max_chars:
        text = text[:max_chars].rsplit(" ", 1)[0] + "…"
    return text


def chat_fn(message: str, history: List[Tuple[str, str]], use_ollama: bool, ollama_model: str, k: int):
    # Ensure index is ready
    if not rag.META_FILE.exists() or not rag.INDEX_FILE.exists():
        rag.build_index()

    # Retrieve
    results = rag.retrieve(message, top_k=max(1, int(k)))

    # Build an answer
    if use_ollama:
        prompt = build_prompt(message, results)
        answer = ask_ollama(prompt, model=ollama_model.strip() or DEFAULT_MODEL)
    else:
        answer = extractive_answer(message, results)

    # Append Sources section only (no numeric inline citations)
    sources_md = format_sources(results) if results else ""
    response = f"{answer}\n\n{sources_md if sources_md else ''}"

    return response


def build_ui():
    with gr.Blocks(title="Oxaion Docs RAG", theme=gr.themes.Soft()) as demo:
        # Language selector
        # Use (label, value) tuples to comply with Gradio's expected format
        _lang_choices = [("English", "en"), ("Deutsch", "de")]
        lang_sel = gr.Dropdown(choices=_lang_choices, value="de", label=TRANSLATIONS["de"]["language_label"], scale=1)

        # Header based on language
        def _header_text(lang: str):
            t = TRANSLATIONS.get(lang, TRANSLATIONS["en"])
            return f"{t['app_title']}\n{t['app_desc']}"

        header_md = gr.Markdown(_header_text(lang_sel.value if hasattr(lang_sel, 'value') else "de"))

        with gr.Row():
            t0 = TRANSLATIONS.get(lang_sel.value if hasattr(lang_sel, 'value') else 'de', TRANSLATIONS['en'])
            use_ollama = gr.Checkbox(value=False, label=t0["use_ollama"])
            # Initialize model list dynamically if server running
            _init_models = _ollama_list_models() if _ollama_server_up() else []
            _init_choices = _init_models if _init_models else OLLAMA_COMMON_MODELS
            # Convert to (label, value) tuples for Dropdown
            _model_choice_pairs = [(m, m) for m in _init_choices]
            _init_value = _init_choices[0]
            ollama_model = gr.Dropdown(
                choices=_model_choice_pairs,
                value=_init_value,
                label=t0["model_label"],
                scale=2,
            )
            top_k = gr.Slider(1, 8, value=4, step=1, label=t0["top_k"])

        # Ollama setup/status panel (moved above chat)
        with gr.Accordion(t0["ollama_section"], open=False):
            status_md = gr.Markdown(visible=True)
            hint_md = gr.Markdown(visible=True)
            with gr.Row():
                refresh_btn = gr.Button(t0["refresh_status"]) 
                start_btn = gr.Button(t0["start_server"]) 
            # Instruction how to pull a model manually
            instruction_md = gr.Markdown(visible=True)


            def _format_status(lang, model_name):
                t = TRANSLATIONS.get(lang, TRANSLATIONS['en'])
                installed = _ollama_installed()
                server = _ollama_server_up()
                models = _ollama_list_models() if server else []
                model_avail = str(model_name) in models if model_name else False
                lines = [
                    t["status_installed"].format(val="✅" if installed else "❌"),
                    t["status_server"].format(val="✅" if server else "❌"),
                    t["status_models"].format(models=", ".join(models) if models else "—"),
                    t["status_model_available"].format(val="✅" if model_avail else "❌"),
                ]
                return "\n".join(lines), models

            def _refresh_status(lang, model_name):
                md, models = _format_status(lang, model_name)
                t = TRANSLATIONS.get(lang, TRANSLATIONS['en'])
                # Update dropdown choices to installed models if any
                if models:
                    dd = gr.update(choices=[(m, m) for m in models], value=(model_name if model_name in models else (models[0] if models else None)))
                else:
                    dd = gr.update()
                instr = gr.update(value=t["pull_instr"].format(model=(model_name or "")))
                return gr.update(value=md), gr.update(value=t["install_hint"]), dd, instr

            def _start_server(lang, model_name):
                # Try to start server if installed but not running
                if _ollama_installed() and not _ollama_server_up():
                    try:
                        subprocess.Popen(["ollama", "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                        time.sleep(2.0)
                    except Exception:
                        pass
                # Warm up selected (or default) model after server starts
                try:
                    _warm_up_model_async(str(model_name or DEFAULT_MODEL))
                except Exception:
                    pass
                return _refresh_status(lang, model_name)

            # (Removed pull button and log; provide manual instruction instead)

            # Initialize status on load
            init = _refresh_status(lang_sel.value if hasattr(lang_sel, 'value') else 'de', ollama_model.value if hasattr(ollama_model, 'value') else DEFAULT_MODEL)
            init_status, init_hint, init_dd, init_instr = init
            status_md.value = init_status["value"] if isinstance(init_status, dict) else init_status
            hint_md.value = init_hint["value"] if isinstance(init_hint, dict) else init_hint
            if isinstance(init_dd, dict):
                ollama_model.choices = init_dd.get("choices", ollama_model.choices)
                if "value" in init_dd:
                    ollama_model.value = init_dd["value"]
            instruction_md.value = init_instr["value"] if isinstance(init_instr, dict) else init_instr

            # Wire buttons
            refresh_btn.click(_refresh_status, inputs=[lang_sel, ollama_model], outputs=[status_md, hint_md, ollama_model, instruction_md])
            start_btn.click(_start_server, inputs=[lang_sel, ollama_model], outputs=[status_md, hint_md, ollama_model, instruction_md])
            # Update instruction when main model changes
            def _on_model_change(lang, model_name):
                t = TRANSLATIONS.get(lang, TRANSLATIONS['en'])
                return gr.update(value=t["pull_instr"].format(model=(model_name or "")))
            ollama_model.change(_on_model_change, inputs=[lang_sel, ollama_model], outputs=[instruction_md])

        chatbot = gr.Chatbot(height=500, show_copy_button=True, type="messages", autoscroll=False, elem_id="chatbot")
        msg = gr.Textbox(placeholder=t0["placeholder"], autofocus=True)
        clear = gr.Button(t0["clear"])

        def respond(message, history, use_llm, model_name, k_val, lang):
            """Generator function to support streaming when using Ollama."""
            history = history or []
            k_val = int(k_val)
            model_name = str(model_name)
            lang = str(lang or 'en')

            # Retrieval first
            results = rag.retrieve(message, top_k=max(1, k_val))

            # If not using LLM, return extractive answer immediately
            if not use_llm:
                answer = extractive_answer(message, results)
                sources_md = format_sources(results, lang=lang) if results else ""
                new_history = history + [
                    {"role": "user", "content": message},
                    {"role": "assistant", "content": f"{answer}\n\n{sources_md}"},
                ]
                return new_history, gr.update(value="")

            # Using LLM: stream tokens
            prompt = build_prompt(message, results)

            # Initialize displayed assistant message
            assistant_text = ""
            working_history = history + [
                {"role": "user", "content": message},
                {"role": "assistant", "content": assistant_text},
            ]

            # Yield once to show the assistant bubble immediately
            yield working_history, gr.update(value="")

            for chunk in ask_ollama_stream(prompt, model=model_name):
                if not chunk:
                    continue
                assistant_text += chunk
                working_history[-1]["content"] = assistant_text
                # Stream incremental updates
                yield working_history, gr.update(value="")

            # Append sources at the end
            sources_md = format_sources(results, lang=lang) if results else ""
            assistant_text = f"{assistant_text}\n\n{sources_md}" if sources_md else assistant_text
            working_history[-1]["content"] = assistant_text
            yield working_history, gr.update(value="")

        # Client-side helper to scroll the Chatbot so the last user message is at the top
        gr.HTML(
            """
            <script>
            window.scrollToUserTop = function () {
              try {
                // Access inside gradio-app shadow DOM if present
                const getRootDoc = () => {
                  const ga = document.querySelector('gradio-app');
                  return (ga && ga.shadowRoot) ? ga.shadowRoot : document;
                };
                const tryScroll = () => {
                  const doc = getRootDoc();
                  const root = doc.getElementById('chatbot');
                  if (!root) return false;

                  // Prefer Gradio v5 message structure
                  let userMsgs = root.querySelectorAll('[data-testid="message"][data-source="user"], [data-testid="user"], .message.user');
                  if (!userMsgs || userMsgs.length === 0) {
                    userMsgs = root.querySelectorAll('[data-testid^="block-"], [data-testid^="message"], .message');
                  }
                  const last = userMsgs[userMsgs.length - 1];
                  if (!last) return false;

                  // Find the nearest scrollable container (Chatbot body)
                  let container = root;
                  const isScrollable = (el) => {
                    if (!el) return false;
                    const style = getComputedStyle(el);
                    const overflowY = style.overflowY;
                    return (overflowY === 'auto' || overflowY === 'scroll') && el.scrollHeight > el.clientHeight;
                  };
                  let parent = last.parentElement;
                  while (parent && parent !== root) {
                    if (isScrollable(parent)) { container = parent; break; }
                    parent = parent.parentElement;
                  }

                  const cRect = container.getBoundingClientRect();
                  const lRect = last.getBoundingClientRect();
                  const delta = (lRect.top - cRect.top) + container.scrollTop;
                  container.scrollTo({ top: delta, behavior: 'auto' });
                  return true;
                };

                // Try a few times to handle async rendering
                let attempts = 0;
                const tick = () => {
                  if (tryScroll()) return;
                  if (++attempts < 10) requestAnimationFrame(tick);
                };
                setTimeout(tick, 50);
              } catch (e) {
                // Fail silently
              }
            };
            </script>
            """,
            visible=False,
        )

        _evt = msg.submit(
            respond,
            inputs=[msg, chatbot, use_ollama, ollama_model, top_k, lang_sel],
            outputs=[chatbot, msg],
        )
        _evt.then(fn=None, inputs=None, outputs=None, js="scrollToUserTop")
        clear.click(lambda: ([], ""), inputs=None, outputs=[chatbot, msg])


        # Rebuild index button
        rebuild = gr.Button(t0["rebuild"])
        out_info = gr.Markdown(visible=False)
        def _rebuild():
            rag.build_index()
            t = TRANSLATIONS.get(lang_sel.value if hasattr(lang_sel, 'value') else 'de', TRANSLATIONS['en'])
            return gr.update(value=t["index_rebuilt"], visible=True)
        rebuild.click(fn=_rebuild, outputs=[out_info])

        # Warm up the default Ollama model in the background to reduce first-token latency
        try:
            _warm_up_model_async(str(ollama_model.value) if hasattr(ollama_model, 'value') else DEFAULT_MODEL)
        except Exception:
            pass

        # Language change handler updates labels/placeholders/header
        def _apply_lang(lang, model_name):
            t = TRANSLATIONS.get(lang, TRANSLATIONS['en'])
            return (
                gr.update(value=_header_text(lang)),
                gr.update(label=t["use_ollama"]),
                gr.update(label=t["model_label"]),
                gr.update(label=t["top_k"]),
                gr.update(placeholder=t["placeholder"]),
                gr.update(value=t["clear"]),
                gr.update(value=t["rebuild"]),
                gr.update(value=t["refresh_status"]),
                gr.update(value=t["start_server"]),
                gr.update(value=t["install_hint"]),
                gr.update(value=t["pull_instr"].format(model=(model_name or ""))),
            )

        lang_sel.change(
            _apply_lang,
            inputs=[lang_sel, ollama_model],
            outputs=[header_md, use_ollama, ollama_model, top_k, msg, clear, rebuild, refresh_btn, start_btn, hint_md, instruction_md],
        )

    return demo


if __name__ == "__main__":
    # Build index on first run if missing
    if not rag.META_FILE.exists() or not rag.INDEX_FILE.exists():
        rag.build_index()
    ui = build_ui()
    ui.launch(server_name="0.0.0.0", server_port=int(os.environ.get("PORT", 7860)), inbrowser=True)
