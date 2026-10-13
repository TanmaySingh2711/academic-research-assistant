"""Flask backend: upload PDFs, build the index, ask questions and check status (JSON API)."""

import threading
from pathlib import Path

import ollama
from flask import Flask, jsonify, render_template, request
from werkzeug.exceptions import HTTPException, RequestEntityTooLarge
from werkzeug.utils import secure_filename

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


@app.get("/")
def home():
    return render_template("index.html")


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
        message += " Click Process to rebuild the index."

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
        return error("No index yet. Upload PDFs and click Process first.", 409)
    index, chunks, _ = current

    try:
        result = answer_question(question.strip(), index, chunks, k=k)
    except (ConnectionError, RuntimeError) as e:  # Ollama not running / model not downloaded
        return error(str(e), 503)

    return jsonify(result)


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
