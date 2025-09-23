import os
import sys
import subprocess
from pathlib import Path
from typing import List, Tuple

import gradio as gr

# Local imports
# Ensure local path is set (already true when running `python app.py`)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

# Import from query.py
import query as rag


def format_sources(items: List[dict]) -> str:
    lines = []
    for i, it in enumerate(items, 1):
        title = it.get("title", "# Abschnitt")
        path = it.get("path", "")
        lines.append(f"{i}. {title} — `{path}`")
    return "\n".join(lines)


def build_prompt(question: str, contexts: List[dict]) -> str:
    ctx_text = "\n\n".join(
        [f"{c.get('title','')}:\n{c.get('content','')}" for c in contexts]
    )
    prompt = (
        "You are a helpful assistant. Answer the user question using the provided context snippets.\n"
        "If the answer cannot be found in the context, say you are not sure.\n\n"
        f"Context:\n{ctx_text}\n\n"
        f"Question: {question}\nAnswer in the same language as the question."
    )
    return prompt


def ask_ollama(prompt: str, model: str = "phi3:mini") -> str:
    try:
        proc = subprocess.Popen(
            ["ollama", "run", model],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        out, err = proc.communicate(prompt, timeout=120)
        if proc.returncode != 0:
            return f"(Ollama error) {err.strip()}\n\nShowing retrieved context instead."
        return out
    except FileNotFoundError:
        return "(Ollama not installed) Showing retrieved context instead."
    except subprocess.TimeoutExpired:
        return "(Ollama timed out) Showing retrieved context instead."


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
        answer = ask_ollama(prompt, model=ollama_model.strip() or "phi3:mini")
    else:
        answer = extractive_answer(message, results)

    # Append sources at the end
    sources = format_sources(results)
    response = f"{answer}\n\n---\n**Sources**\n{sources if sources else 'No sources found.'}"

    return response


def build_ui():
    with gr.Blocks(title="Oxaion Docs RAG", theme=gr.themes.Soft()) as demo:
        gr.Markdown("""
        # Oxaion Docs Assistant
        Ask questions about the Oxaion documentation. The assistant retrieves the most relevant sections.
        - Toggle Ollama to generate answers with a local LLM, or leave it off for a fast extractive response.
        - Sources of the retrieved chunks are listed below each answer.
        """)

        with gr.Row():
            use_ollama = gr.Checkbox(value=False, label="Use Ollama for generation")
            ollama_model = gr.Textbox(value="phi3:mini", label="Ollama Model", scale=2)
            top_k = gr.Slider(1, 8, value=4, step=1, label="Top-K Chunks")

        chatbot = gr.Chatbot(height=500, show_copy_button=True, type="messages")
        msg = gr.Textbox(placeholder="Ask something about Oxaion…", autofocus=True)
        clear = gr.Button("Clear")

        def respond(message, history, use_llm, model_name, k_val):
            # Convert history in messages format to a simple list of tuples for our fn
            simple_hist = []
            if isinstance(history, list):
                for m in history:
                    role = m.get("role")
                    content = m.get("content", "")
                    if role == "user":
                        simple_hist.append((content, None))
                    elif role == "assistant":
                        if simple_hist:
                            last = simple_hist[-1]
                            simple_hist[-1] = (last[0], content)
                        else:
                            simple_hist.append(("", content))

            answer = chat_fn(message, simple_hist, bool(use_llm), str(model_name), int(k_val))
            new_history = (history or []) + [
                {"role": "user", "content": message},
                {"role": "assistant", "content": answer},
            ]
            return new_history, gr.update(value="")

        msg.submit(
            respond,
            inputs=[msg, chatbot, use_ollama, ollama_model, top_k],
            outputs=[chatbot, msg],
        )
        clear.click(lambda: ([], ""), inputs=None, outputs=[chatbot, msg])

        # Rebuild index button
        rebuild = gr.Button("Rebuild Index")
        out_info = gr.Markdown(visible=False)
        def _rebuild():
            rag.build_index()
            return gr.update(value="Index rebuilt.", visible=True)
        rebuild.click(fn=_rebuild, outputs=[out_info])

    return demo


if __name__ == "__main__":
    # Build index on first run if missing
    if not rag.META_FILE.exists() or not rag.INDEX_FILE.exists():
        rag.build_index()
    ui = build_ui()
    ui.launch(server_name="0.0.0.0", server_port=int(os.environ.get("PORT", 7860)))
