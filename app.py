"""Flask backend: dashboard pages plus a JSON API for papers, the index, questions and chats."""

import socket
import threading
from pathlib import Path

from flask import Flask, jsonify, render_template, request
from werkzeug.exceptions import HTTPException, RequestEntityTooLarge
from werkzeug.utils import secure_filename

from src.chat_store import add_exchange, delete_chat, delete_chats_for_paper, get_chat, list_chats, rename_chat
from src.embedder import load_model
from src.ingest import run_ingestion
from src.rag_pipeline import answer_question
from src.retriever import check_model_matches
from src.suggestions import SUGGESTIONS_FILE, get_suggestions
from src.vector_store import CHUNKS_FILE, INDEX_FILE, INFO_FILE, load_store

BASE_DIR = Path(__file__).parent
ALLOWED_K = (1, 3, 5)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024  # 25 MB per upload request
# Folders (tests point these to temporary folders, so they never touch your real files)
app.config["DATA_DIR"] = BASE_DIR / "data"  # uploaded PDFs
app.config["INDEX_DIR"] = BASE_DIR / "index"  # FAISS index, chunk text, suggested questions
app.config["CHATS_DIR"] = BASE_DIR / "chats"  # one JSON file per chat
app.config["WARM_UP_MODEL"] = True  # load the embedding model in the background after the first request

# Only one request at a time may rebuild the index (Build index, or deleting a paper)
process_lock = threading.Lock()

# The loaded store as one tuple (index, chunks, info), or None if there is no index yet.
# It is replaced in one step, so /ask never sees a new index with old chunks.
store = None


def data_dir():
    return Path(app.config["DATA_DIR"])


def index_dir():
    return Path(app.config["INDEX_DIR"])


def chats_dir():
    return Path(app.config["CHATS_DIR"])


def load_index_into_memory():
    """Load the saved index from disk into memory. Leaves store as None if there is no index."""
    global store
    try:
        index, chunks, info = load_store(index_dir())
        check_model_matches(info)
        store = (index, chunks, info)
        print(f"Index loaded: {len(chunks)} chunks.")
    except (FileNotFoundError, ValueError) as e:
        store = None
        print(f"No index loaded: {e}")


def clear_index():
    """Remove the saved index (used when the last paper is deleted)."""
    global store
    for name in (INDEX_FILE, CHUNKS_FILE, INFO_FILE, SUGGESTIONS_FILE):
        (index_dir() / name).unlink(missing_ok=True)
    store = None


def error(message, status):
    """Every error is returned as JSON: {"error": "..."}."""
    return jsonify({"error": message}), status


_warm_up_started = False


def warm_up_model():
    """Load the embedding model (about 8 seconds), so the first question does not have to wait for it."""
    try:
        load_model()
        print("Embedding model ready.")
    except Exception as e:
        print(f"Embedding model not loaded yet (it loads on the first question): {e}")


@app.before_request
def start_warm_up():
    # The server and its pages start at once; the slow model loads in the background meanwhile
    global _warm_up_started
    if not _warm_up_started and app.config["WARM_UP_MODEL"]:
        _warm_up_started = True
        threading.Thread(target=warm_up_model, daemon=True).start()


def indexed_papers(current):
    """Filenames of the papers that are in the loaded index."""
    return sorted({chunk["source"] for chunk in current[1]}) if current else []


def pdfs_in_data():
    folder = data_dir()
    return sorted(p.name for p in folder.glob("*") if p.suffix.lower() == ".pdf") if folder.exists() else []


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


# ---------- Papers ----------

@app.post("/upload")
def upload():
    files = [f for f in request.files.getlist("files") if f.filename]
    if not files:
        return error("No files uploaded. Choose one or more PDF files.", 400)

    data_dir().mkdir(exist_ok=True)
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

        path = data_dir() / name
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
            summary = run_ingestion(data_dir(), index_dir())
        except ValueError as e:  # no PDFs, or no text in any PDF
            return error(str(e), 400)
        load_index_into_memory()

    return jsonify({
        "summary": summary,
        "message": f"Index built: {summary['pdfs']} PDFs, {summary['pages']} pages, {summary['chunks']} chunks.",
    })


@app.delete("/api/papers/<name>")
def delete_paper(name):
    """Delete a paper: its PDF, all its chats, and rebuild the index without it."""
    path = data_dir() / name
    # Only plain file names of PDFs in data/ (no paths like "../app.py")
    if name != secure_filename(name) or not name.lower().endswith(".pdf") or not path.is_file():
        return error("Paper not found.", 404)

    with process_lock:
        path.unlink()
        chats_deleted = delete_chats_for_paper(chats_dir(), name)
        summary = None
        if pdfs_in_data():
            try:
                summary = run_ingestion(data_dir(), index_dir())
                load_index_into_memory()
            except ValueError:  # the other PDFs have no text (for example scanned)
                clear_index()
        else:
            clear_index()  # that was the last paper

    return jsonify({
        "deleted": name,
        "chats_deleted": chats_deleted,
        "summary": summary,
        "message": f"Deleted the paper and {chats_deleted} chat{'' if chats_deleted == 1 else 's'}.",
    })


# ---------- Asking ----------

@app.post("/ask")
def ask():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return error("Send JSON like {\"question\": \"...\", \"paper\": \"paper.pdf\", \"k\": 3}.", 400)

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

    # Every chat is about one paper. An existing chat keeps its paper; a new chat uses the paper sent by the page.
    chat_id = data.get("chat_id")
    if chat_id is not None:
        try:
            paper = get_chat(chats_dir(), chat_id)["paper"]
        except KeyError:
            return error("This chat was not found. Start a new chat.", 404)
    else:
        paper = data.get("paper")
    if paper not in indexed_papers(current):
        return error("Pick a paper that is in the index. If it is new, click Build index first.", 400)

    try:
        result = answer_question(question.strip(), index, chunks, k=k, source=paper)
    except (ConnectionError, RuntimeError) as e:  # Ollama not running / model not downloaded
        return error(str(e), 503)

    chat = add_exchange(chats_dir(), chat_id, paper, result)
    return jsonify({**result, "chat_id": chat["id"], "paper": paper, "title": chat["title"]})


@app.get("/api/suggestions")
def suggestions():
    """A few questions about one paper, written by the local model from the start of the paper."""
    paper = request.args.get("paper", "")
    current = store
    if current is None:
        return error("No index yet. Upload PDFs and click Build index first.", 409)
    if paper not in indexed_papers(current):
        return error("This paper is not in the index yet. Click Build index first.", 400)
    try:
        questions = get_suggestions(paper, current[1], current[2], index_dir())
    except (ConnectionError, RuntimeError) as e:  # Ollama not running / model not downloaded
        return error(str(e), 503)
    return jsonify({"paper": paper, "questions": questions})


# ---------- Chats ----------

@app.get("/api/chats")
def chats():
    return jsonify(list_chats(chats_dir()))


@app.get("/api/chats/<chat_id>")
def chat_detail(chat_id):
    try:
        return jsonify(get_chat(chats_dir(), chat_id))
    except KeyError:
        return error("Chat not found.", 404)


@app.patch("/api/chats/<chat_id>")
def chat_rename(chat_id):
    data = request.get_json(silent=True)
    title = data.get("title") if isinstance(data, dict) else None
    if not isinstance(title, str):
        return error("Send JSON like {\"title\": \"New name\"}.", 400)
    try:
        chat = rename_chat(chats_dir(), chat_id, title)
    except KeyError:
        return error("Chat not found.", 404)
    except ValueError as e:
        return error(str(e), 400)
    return jsonify({"id": chat["id"], "title": chat["title"]})


@app.delete("/api/chats/<chat_id>")
def chat_delete(chat_id):
    try:
        delete_chat(chats_dir(), chat_id)
    except KeyError:
        return error("Chat not found.", 404)
    return jsonify({"deleted": chat_id})


# ---------- Status ----------

def is_ollama_running():
    """True if the Ollama server answers on its default address (127.0.0.1:11434)."""
    # Quick port check first: on Windows, connecting to a closed port takes about 2 seconds
    # (Windows retries), which would make every status check slow while Ollama is off.
    try:
        socket.create_connection(("127.0.0.1", 11434), timeout=0.3).close()
    except OSError:
        return False
    try:
        import ollama  # imported here so the app starts faster

        ollama.list()  # something answers on the port: check that it really is Ollama
        return True
    except Exception:
        return False


@app.get("/status")
def status():
    current = store
    ollama_running = is_ollama_running()

    return jsonify({
        "index_ready": current is not None,
        "chunks": len(current[1]) if current else 0,
        "built_at": current[2].get("built_at") if current else None,
        "pdfs_in_data": pdfs_in_data(),
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
