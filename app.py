"""Flask backend: dashboard pages plus a JSON API to upload PDFs, build the index, ask and see chat history."""

import threading
from pathlib import Path

import ollama
from flask import Flask, jsonify, render_template, request
from werkzeug.exceptions import HTTPException, RequestEntityTooLarge
from werkzeug.utils import secure_filename

from src.chat_store import add_exchange, get_chat, list_chats
from src.ingest import run_ingestion
from src.rag_pipeline import answer_question
from src.retriever import check_model_matches
from src.vector_store import load_store

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
INDEX_DIR = BASE_DIR / "index"
ALLOWED_K = (1, 3, 5)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024  # 25 MB per upload request
app.config["CHATS_DIR"] = BASE_DIR / "chats"  # one JSON file per chat (tests point this to a temp folder)

# Only one /process request may rebuild the index at a time
process_lock = threading.Lock()

# The loaded store as one tuple (index, chunks, info), or None if there is no index yet.
# It is replaced in one step, so /ask never sees a new index with old chunks.
store = None


def load_index_into_memory():
    """Load the saved index from disk into memory. Leaves store as None if there is no index."""
    global store
    try:
        index, chunks, info = load_store(INDEX_DIR)
        check_model_matches(info)
        store = (index, chunks, info)
        print(f"Index loaded: {len(chunks)} chunks.")
    except (FileNotFoundError, ValueError) as e:
        store = None
        print(f"No index loaded: {e}")


def error(message, status):
    """Every error is returned as JSON: {"error": "..."}."""
    return jsonify({"error": message}), status


def indexed_papers(current):
    """Filenames of the papers that are in the loaded index."""
    return sorted({chunk["source"] for chunk in current[1]}) if current else []


# ---------- Pages ----------

@app.get("/")
def overview():
    return render_template("overview.html")


@app.get("/chat")
def chat_page():
    return render_template("chat.html")


@app.get("/how-it-works")
def how_it_works():
    return render_template("how_it_works.html")


@app.get("/history")
def history_page():
    return render_template("history.html")


# ---------- JSON API ----------


@app.post("/upload")
def upload():
    files = [f for f in request.files.getlist("files") if f.filename]
    if not files:
        return error("No files uploaded. Choose one or more PDF files.", 400)

    DATA_DIR.mkdir(exist_ok=True)
    saved, skipped, overwritten = [], [], []

    for f in files:
        if not f.filename.lower().endswith(".pdf"):
            skipped.append({"name": f.filename, "reason": "Not a .pdf file"})
            continue

        # A real PDF always starts with the bytes "%PDF"
        header = f.stream.read(4)
        f.stream.seek(0)
        if header != b"%PDF":
            skipped.append({"name": f.filename, "reason": "Not a real PDF (content does not start with %PDF)"})
            continue

        # Remove unsafe characters and paths, e.g. "../x.pdf" or spaces
        name = secure_filename(f.filename)
        if not name.lower().endswith(".pdf"):
            skipped.append({"name": f.filename, "reason": "Invalid filename"})
            continue

        path = DATA_DIR / name
        if path.exists():
            overwritten.append(name)
        f.save(path)
        saved.append(name)

    message = f"Saved {len(saved)} file(s), skipped {len(skipped)}."
    if overwritten:
        message += f" Overwrote existing: {', '.join(overwritten)}."
    if saved:
        message += " Click Build index to make them searchable."

    return jsonify({"saved": saved, "skipped": skipped, "message": message})


@app.post("/process")
def process():
    with process_lock:
        try:
            summary = run_ingestion(DATA_DIR, INDEX_DIR)
        except ValueError as e:  # no PDFs, or no text in any PDF
            return error(str(e), 400)
        load_index_into_memory()

    return jsonify({
        "summary": summary,
        "message": f"Index built: {summary['pdfs']} PDFs, {summary['pages']} pages, {summary['chunks']} chunks.",
    })


@app.post("/ask")
def ask():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return error("Send JSON like {\"question\": \"...\", \"k\": 3}.", 400)

    question = data.get("question", "")
    if not isinstance(question, str) or not question.strip():
        return error("Question is empty. Please type a question.", 400)

    k = data.get("k", 3)
    if isinstance(k, bool) or k not in ALLOWED_K:  # bool check: True == 1 in Python
        return error("k must be 1, 3 or 5.", 400)

    current = store  # take one consistent snapshot
    if current is None:
        return error("No index yet. Upload PDFs and click Build index first.", 409)
    index, chunks, _ = current

    # An existing chat keeps its own paper; a new chat uses the paper sent by the page (None = all papers)
    chats_dir = app.config["CHATS_DIR"]
    chat_id = data.get("chat_id")
    if chat_id is not None:
        try:
            paper = get_chat(chats_dir, chat_id)["paper"]
        except KeyError:
            return error("This chat was not found. Start a new chat.", 404)
    else:
        paper = data.get("paper") or None
        if paper is not None and paper not in indexed_papers(current):
            return error("This paper is not in the index yet. Click Build index first.", 400)

    try:
        result = answer_question(question.strip(), index, chunks, k=k, source=paper)
    except (ConnectionError, RuntimeError) as e:  # Ollama not running / model not downloaded
        return error(str(e), 503)

    chat = add_exchange(chats_dir, chat_id, paper, result)
    return jsonify({**result, "chat_id": chat["id"], "paper": paper})


@app.get("/api/chats")
def chats():
    return jsonify(list_chats(app.config["CHATS_DIR"]))


@app.get("/api/chats/<chat_id>")
def chat_detail(chat_id):
    try:
        return jsonify(get_chat(app.config["CHATS_DIR"], chat_id))
    except KeyError:
        return error("Chat not found.", 404)


@app.get("/status")
def status():
    current = store
    try:
        ollama.list()  # needs the Ollama server
        ollama_running = True
    except Exception:
        ollama_running = False

    pdfs = sorted(p.name for p in DATA_DIR.glob("*") if p.suffix.lower() == ".pdf") if DATA_DIR.exists() else []

    return jsonify({
        "index_ready": current is not None,
        "chunks": len(current[1]) if current else 0,
        "built_at": current[2].get("built_at") if current else None,
        "pdfs_in_data": pdfs,
        "indexed_papers": indexed_papers(current),
        "ollama_running": ollama_running,
    })


@app.errorhandler(RequestEntityTooLarge)
def too_large(e):
    return error("File too large. The maximum upload size is 25 MB.", 413)


@app.errorhandler(HTTPException)
def http_error(e):
    # e.g. 404 page not found, 405 wrong method
    return error(e.description, e.code)


@app.errorhandler(Exception)
def unexpected_error(e):
    # Log the full traceback in the terminal, but never send it to the user
    app.logger.exception("Unexpected error")
    return error("Something went wrong on the server. Check the terminal for details.", 500)


# Load the index once at startup (starts fine without one)
load_index_into_memory()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
