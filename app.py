"""Flask backend: dashboard pages plus a JSON API for papers, the index, questions and chats."""

import itertools
import json
import socket
import threading
import time
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from flask import Flask, Response, jsonify, render_template, request
from werkzeug.exceptions import HTTPException, RequestEntityTooLarge
from werkzeug.utils import secure_filename

from src.chat_store import (
    add_exchange,
    delete_chat,
    delete_chats_for_paper,
    get_chat,
    get_history,
    list_chats,
    new_chat_id,
    rename_chat,
)
from src.embedder import load_model
from src.ingest import is_compatible, papers_needing_index, run_ingestion
from src.rag_pipeline import answer_question_stream, make_result
from src.reranker import load_reranker
from src.retriever import check_model_matches
from src.schema import Chunk
from src.suggestions import SUGGESTIONS_FILE, forget, get_suggestions
from src.vector_store import CHUNKS_FILE, INDEX_FILE, INFO_FILE, load_store, remove_paper, save_store

BASE_DIR = Path(__file__).parent
STORAGE_DIR = BASE_DIR / "storage"  # everything the app saves; created when needed, ignored by git
ALLOWED_K = (1, 3, 5)
# The dashboard runs only on this computer, so these are the only host names it answers to
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}

app = Flask(__name__, template_folder="web/templates", static_folder="web/static")
app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024  # 25 MB per upload request
# Folders (tests point these to temporary folders, so they never touch your real files)
app.config["PAPERS_DIR"] = STORAGE_DIR / "papers"  # uploaded PDFs
app.config["INDEX_DIR"] = STORAGE_DIR / "index"  # FAISS index, chunk text, suggested questions
app.config["CHATS_DIR"] = STORAGE_DIR / "chats"  # one JSON file per chat
app.config["WARM_UP_MODEL"] = True  # load the models in the background after the first request

# Only one request at a time may change the index (Build index, or deleting a paper)
process_lock = threading.Lock()

# New every time the server starts. The page compares it with the one it saw before:
# a different id means the dashboard was opened fresh, so it starts on the default page
# instead of reopening the last chat.
BOOT_ID = uuid.uuid4().hex

# The loaded store as one tuple (index, chunks, info), or None if there is no index yet.
# It is replaced in one step, so /ask never sees a new index with old chunks.
Store = tuple[Any, list[Chunk], dict[str, Any]]
store: Store | None = None


def papers_dir() -> Path:
    return Path(app.config["PAPERS_DIR"])


def index_dir() -> Path:
    return Path(app.config["INDEX_DIR"])


def chats_dir() -> Path:
    return Path(app.config["CHATS_DIR"])


def load_index_into_memory() -> None:
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


def clear_index() -> None:
    """Remove the saved index (used when the last paper is deleted)."""
    global store
    for name in (INDEX_FILE, CHUNKS_FILE, INFO_FILE, SUGGESTIONS_FILE):
        (index_dir() / name).unlink(missing_ok=True)
    store = None


CHAT_DELETED = "This chat was deleted while the answer was being written."


def error(message: str, status: int) -> tuple[Response, int]:
    """Every error is returned as JSON: {"error": "..."}."""
    return jsonify({"error": message}), status


_warm_up_started = False


def warm_up_models() -> None:
    """Load the embedding model and the re-ranker (about 8 seconds), so the first question is fast."""
    try:
        load_model()
        load_reranker()
        print("Search models ready.")
    except Exception as e:
        print(f"Search models not loaded yet (they load on the first question): {e}")


@app.before_request
def only_this_computer() -> Any:
    """Answer only the dashboard itself.

    - The host name must be this computer. A web page on another site could otherwise point its
      own domain at 127.0.0.1 ("DNS rebinding") and read the API.
    - A request that changes something (upload, build, ask, rename, delete) must not come from
      another website. Browsers send the Origin header with such requests, and plain HTML forms
      on any site could otherwise post to http://localhost:5000.
    """
    if urlsplit(f"//{request.host}").hostname not in LOCAL_HOSTS:
        return error("This dashboard only answers on localhost.", 403)
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        origin = request.headers.get("Origin")
        other_site = origin is not None and urlsplit(origin).netloc != request.host
        if other_site or request.headers.get("Sec-Fetch-Site") == "cross-site":
            return error("Requests from other websites are not allowed.", 403)
    return None


@app.before_request
def start_warm_up() -> None:
    # The server and its pages start at once; the slow models load in the background meanwhile
    global _warm_up_started
    if not _warm_up_started and app.config["WARM_UP_MODEL"]:
        _warm_up_started = True
        threading.Thread(target=warm_up_models, daemon=True).start()


def indexed_papers(current: Store | None) -> list[str]:
    """Filenames of the papers that have chunks in the loaded index (so they can be asked about)."""
    return sorted({chunk["source"] for chunk in current[1]}) if current else []


def pdfs_in_data() -> list[str]:
    folder = papers_dir()
    return sorted(p.name for p in folder.glob("*") if p.suffix.lower() == ".pdf") if folder.exists() else []


def papers_to_index(current: Store | None) -> list[str]:
    """PDFs in storage/papers/ that are not in the index yet, or that changed after they were indexed
    (for example uploaded again with the same name). Build index is only useful for these."""
    return papers_needing_index(papers_dir(), current[2] if current else None)


def unreadable_papers(current: Store | None) -> list[str]:
    """Papers that were indexed but gave no text at all (for example a scan that OCR could not read)."""
    if current is None:
        return []
    papers = current[2].get("papers", {})
    return sorted(name for name in pdfs_in_data() if papers.get(name, {}).get("chunks") == 0)


# ---------- Pages ----------

@app.get("/")
def overview() -> str:
    return render_template("overview.html")


@app.get("/chat")
def chat_page() -> str:
    return render_template("chat.html")


@app.get("/how-it-works")
def how_it_works() -> str:
    return render_template("how_it_works.html")


# ---------- Papers ----------

@app.post("/upload")
def upload() -> Any:
    files = [f for f in request.files.getlist("files") if f.filename]
    if not files:
        return error("No files uploaded. Choose one or more PDF files.", 400)

    papers_dir().mkdir(parents=True, exist_ok=True)
    saved, skipped, overwritten = [], [], []

    for f in files:
        filename = f.filename or ""
        if not filename.lower().endswith(".pdf"):
            skipped.append({"name": filename, "reason": "Not a .pdf file"})
            continue

        # A real PDF always starts with the bytes "%PDF"
        header = f.stream.read(4)
        f.stream.seek(0)
        if header != b"%PDF":
            skipped.append({"name": filename, "reason": "Not a real PDF (content does not start with %PDF)"})
            continue

        # Remove unsafe characters and paths, e.g. "../x.pdf" or spaces
        name = secure_filename(filename)
        if not name.lower().endswith(".pdf"):
            skipped.append({"name": filename, "reason": "Invalid filename"})
            continue

        path = papers_dir() / name
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


def plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


@app.post("/process")
def process() -> Any:
    """Build index: read and embed the papers that are new or changed. The others keep their vectors."""
    with process_lock:
        try:
            summary = run_ingestion(papers_dir(), index_dir())
        except ValueError as e:  # no PDFs, or no text in any PDF
            return error(str(e), 400)
        load_index_into_memory()

    indexed = summary["indexed"]
    if indexed:
        message = (f"Indexed {plural(len(indexed), 'paper')} ({plural(summary['pages'], 'page')}, "
                   f"{plural(summary['new_chunks'], 'chunk')}) in {summary['seconds']} s.")
    else:
        message = "Everything is already indexed."
    return jsonify({"summary": summary, "message": message})


@app.delete("/api/papers/<name>")
def delete_paper(name: str) -> Any:
    """Delete a paper: its PDF, all its chats, and its chunks in the index. Nothing else.

    The other papers are not indexed again (a new paper stays "not indexed" until you click
    Build index), so this takes only a moment.
    """
    path = papers_dir() / name
    # Only plain file names of PDFs in storage/papers/ (no paths like "../app.py")
    if name != secure_filename(name) or not name.lower().endswith(".pdf"):
        return error("Paper not found.", 404)

    with process_lock:
        if not path.is_file():  # checked inside the lock: two deletes at once remove it only once
            return error("Paper not found.", 404)
        path.unlink()
        chats_deleted = delete_chats_for_paper(chats_dir(), name)
        forget(name, index_dir())
        current = store
        if current is not None and (name in current[2].get("papers", {}) or name in indexed_papers(current)):
            index, chunks, info = current
            new_index, new_chunks = remove_paper(index, chunks, name)
            if new_chunks:
                papers = {key: value for key, value in info.get("papers", {}).items() if key != name}
                save_store(new_index, new_chunks, index_dir(), {**info, "papers": papers})
                load_index_into_memory()
            else:
                clear_index()  # that was the last indexed paper

    return jsonify({
        "deleted": name,
        "chats_deleted": chats_deleted,
        "message": f"Deleted the paper and {plural(chats_deleted, 'chat')}.",
    })


# ---------- Asking ----------

def event_line(event: dict[str, Any]) -> str:
    """One event of a streamed answer: a JSON object on its own line (NDJSON)."""
    return json.dumps(event, ensure_ascii=False) + "\n"


@app.post("/ask")
def ask() -> Any:
    """Answer a question about one paper.

    JSON in: {"question": "...", "paper": "x.pdf"} for a new chat, or {"question": "...", "chat_id": "..."}
    to continue a chat (earlier questions and answers are used for follow-ups), plus optional "k".
    With "stream": true the answer arrives word by word as NDJSON events:
    start (chat id, chunks found), token (a piece of text) ..., then done (the full answer) or error.
    Without it, the full answer comes back as one JSON object.
    """
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return error("Send JSON like {\"question\": \"...\", \"paper\": \"paper.pdf\", \"k\": 3}.", 400)

    question = data.get("question", "")
    if not isinstance(question, str) or not question.strip():
        return error("Question is empty. Please type a question.", 400)
    question = question.strip()

    k = data.get("k", 3)
    if isinstance(k, bool) or k not in ALLOWED_K:  # bool check: True == 1 in Python
        return error("k must be 1, 3 or 5.", 400)

    current = store  # take one consistent snapshot
    if current is None:
        return error("No index yet. Upload PDFs and click Build index first.", 409)
    index, chunks, _ = current

    # Every chat is about one paper. An existing chat keeps its paper; a new chat uses the paper sent by the page.
    chat_id = data.get("chat_id")
    history = []
    if chat_id is not None:
        try:
            paper = get_chat(chats_dir(), chat_id)["paper"]
            history = get_history(chats_dir(), chat_id)
        except KeyError:
            return error("This chat was not found. Start a new chat.", 404)
    else:
        paper = data.get("paper")
    if paper not in indexed_papers(current):
        return error("Pick a paper that is in the index. If it is new, click Build index first.", 400)

    events = answer_question_stream(question, index, chunks, k=k, source=paper, history=history)
    try:
        # Search, then wait for the first piece of the answer: if Ollama is not running, this is
        # where it fails, and a normal JSON error can still be returned
        found = next(events)
        first = next(events)
    except (ConnectionError, RuntimeError) as e:  # Ollama not running / model not downloaded
        return error(str(e), 503)
    results = found["results"]
    new_id = chat_id or new_chat_id()
    started = time.perf_counter()
    target = chats_dir()

    def save(result: dict[str, Any]) -> dict[str, Any]:
        # Raises KeyError if the chat was deleted while its answer was being written
        chat = add_exchange(target, chat_id, paper, result, new_id=new_id)
        return {**result, "chat_id": chat["id"], "paper": paper, "title": chat["title"]}

    if not data.get("stream"):
        final = first
        try:
            for final in events:
                pass
            return jsonify(save(final["result"]))
        except (ConnectionError, RuntimeError) as e:  # Ollama stopped in the middle of the answer
            return error(str(e), 503)
        except KeyError:
            return error(CHAT_DELETED, 404)

    def stream() -> Iterator[str]:
        pieces: list[str] = []
        finished = False
        try:
            yield event_line({"type": "start", "chat_id": new_id, "paper": paper, "sources": len(results)})
            for event in itertools.chain([first], events):  # chain: one event at a time, as they come
                if event["type"] == "token":
                    pieces.append(event["text"])
                    yield event_line(event)
                elif event["type"] == "done":
                    finished = True
                    yield event_line({"type": "done", "result": save(event["result"])})
        except KeyError:
            yield event_line({"type": "error", "error": CHAT_DELETED, "status": 404})
        except (ConnectionError, RuntimeError) as e:
            finished = True
            yield event_line({"type": "error", "error": str(e), "status": 503})
        except Exception:
            finished = True
            app.logger.exception("Error while streaming an answer")
            yield event_line({"type": "error", "error": "Something went wrong on the server.", "status": 500})
        finally:
            # The user pressed Stop (the browser closed the connection): keep what was written so far
            if not finished and "".join(pieces).strip():
                partial = {"answer": "".join(pieces).strip(), "prompt_tokens": None, "answer_tokens": None,
                           "seconds": round(time.perf_counter() - started, 2)}
                try:
                    save({**make_result(question, k, results, partial), "stopped": True})
                except KeyError:
                    pass  # the chat was deleted meanwhile: nothing to keep

    # X-Accel-Buffering: no proxy may hold the pieces back (they must reach the page at once)
    return Response(stream(), mimetype="application/x-ndjson", headers={"X-Accel-Buffering": "no"})


@app.get("/api/suggestions")
def suggestions() -> Any:
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
def chats() -> Any:
    return jsonify(list_chats(chats_dir()))


@app.get("/api/chats/<chat_id>")
def chat_detail(chat_id: str) -> Any:
    try:
        return jsonify(get_chat(chats_dir(), chat_id))
    except KeyError:
        return error("Chat not found.", 404)


@app.patch("/api/chats/<chat_id>")
def chat_rename(chat_id: str) -> Any:
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
def chat_delete(chat_id: str) -> Any:
    try:
        delete_chat(chats_dir(), chat_id)
    except KeyError:
        return error("Chat not found.", 404)
    return jsonify({"deleted": chat_id})


# ---------- Status ----------

def is_ollama_running() -> bool:
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
def status() -> Any:
    current = store
    ollama_running = is_ollama_running()

    return jsonify({
        "index_ready": current is not None,
        "chunks": len(current[1]) if current else 0,
        "built_at": current[2].get("built_at") if current else None,
        # The index was made by an older version of the app: Build index updates it
        "index_outdated": current is not None and not is_compatible(current[2]),
        "pdfs_in_data": pdfs_in_data(),
        "indexed_papers": indexed_papers(current),
        "papers_to_index": papers_to_index(current),
        "unreadable_papers": unreadable_papers(current),
        "ollama_running": ollama_running,
        "boot_id": BOOT_ID,
    })


@app.errorhandler(RequestEntityTooLarge)
def too_large(e: RequestEntityTooLarge) -> Any:
    return error("File too large. The maximum upload size is 25 MB.", 413)


@app.errorhandler(HTTPException)
def http_error(e: HTTPException) -> Any:
    # e.g. 404 page not found, 405 wrong method
    return error(e.description or "Request failed.", e.code or 500)


@app.errorhandler(Exception)
def unexpected_error(e: Exception) -> Any:
    # Log the full traceback in the terminal, but never send it to the user
    app.logger.exception("Unexpected error")
    return error("Something went wrong on the server. Check the terminal for details.", 500)


# Load the index once at startup (starts fine without one)
load_index_into_memory()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
