"""Chat history: every conversation is saved as one JSON file in the chats/ folder.

A chat belongs to one paper (its filename) or to all papers (paper = None),
so the dashboard can group the history by paper.
"""

import json
import re
import threading
import uuid
from datetime import datetime
from pathlib import Path

_lock = threading.Lock()  # one write at a time
_ID_PATTERN = re.compile(r"^[0-9a-f]{12}$")  # ids are 12 hex characters (no paths possible)
TITLE_LENGTH = 60
PREVIEW_LENGTH = 120


def _now():
    # Milliseconds, so two chats saved in the same second still sort in the right order
    return datetime.now().isoformat(timespec="milliseconds")


def _path(chats_dir, chat_id):
    """File path of a chat. Raises KeyError for an invalid id."""
    if not isinstance(chat_id, str) or not _ID_PATTERN.match(chat_id):
        raise KeyError(chat_id)
    return Path(chats_dir) / f"{chat_id}.json"


def _save(chats_dir, chat):
    """Write the chat to a temporary file first, then swap it in, so a crash never leaves half a file."""
    Path(chats_dir).mkdir(parents=True, exist_ok=True)
    path = _path(chats_dir, chat["id"])
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(chat, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def get_chat(chats_dir, chat_id):
    """Return the full chat. Raises KeyError if it does not exist."""
    path = _path(chats_dir, chat_id)
    if not path.exists():
        raise KeyError(chat_id)
    return json.loads(path.read_text(encoding="utf-8"))


def add_exchange(chats_dir, chat_id, paper, result):
    """Save one question and its answer. Creates a new chat when chat_id is None.

    result is the dictionary returned by answer_question(). Returns the updated chat.
    """
    with _lock:
        if chat_id is None:
            now = _now()
            chat = {
                "id": uuid.uuid4().hex[:12],
                "paper": paper,
                "title": result["question"][:TITLE_LENGTH],
                "created_at": now,
                "updated_at": now,
                "messages": [],
            }
        else:
            chat = get_chat(chats_dir, chat_id)

        now = _now()
        chat["messages"].append({"role": "user", "content": result["question"], "time": now})
        chat["messages"].append({
            "role": "assistant",
            "content": result["answer"],
            "not_found": result["not_found"],
            "sources": result["sources"],  # includes the chunk text, so old chats still show it
            "k": result["k"],
            "prompt_tokens": result["prompt_tokens"],
            "answer_tokens": result["answer_tokens"],
            "seconds": result["seconds"],
            "time": now,
        })
        chat["updated_at"] = now
        _save(chats_dir, chat)
        return chat


def rename_chat(chats_dir, chat_id, title):
    """Give a chat a new title. Raises KeyError if it does not exist, ValueError for an empty title."""
    title = " ".join(str(title).split())[:TITLE_LENGTH]  # one line, not too long
    if not title:
        raise ValueError("The chat name cannot be empty.")
    with _lock:
        chat = get_chat(chats_dir, chat_id)
        chat["title"] = title
        _save(chats_dir, chat)
        return chat


def delete_chat(chats_dir, chat_id):
    """Delete one chat. Raises KeyError if it does not exist."""
    with _lock:
        path = _path(chats_dir, chat_id)
        if not path.exists():
            raise KeyError(chat_id)
        path.unlink()


def delete_chats_for_paper(chats_dir, paper):
    """Delete every chat about one paper (paper=None: chats about all papers). Returns how many."""
    deleted = 0
    with _lock:
        for path in Path(chats_dir).glob("*.json"):
            try:
                chat = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if chat.get("paper") == paper:
                path.unlink()
                deleted += 1
    return deleted


def list_chats(chats_dir):
    """Return a short summary of every chat, newest first."""
    found = []  # (file change time, summary) pairs
    for path in Path(chats_dir).glob("*.json"):
        try:
            chat = json.loads(path.read_text(encoding="utf-8"))
            modified = path.stat().st_mtime_ns
        except (OSError, ValueError):
            continue  # skip a broken file instead of failing the whole list
        answers = [m for m in chat["messages"] if m["role"] == "assistant"]
        found.append((modified, {
            "id": chat["id"],
            "paper": chat["paper"],
            "title": chat["title"],
            "created_at": chat["created_at"],
            "updated_at": chat["updated_at"],
            "questions": len(answers),
            "preview": answers[-1]["content"][:PREVIEW_LENGTH] if answers else "",
        }))
    # Newest first; the file change time decides when two saved times are equal
    found.sort(key=lambda pair: (pair[1]["updated_at"], pair[0]), reverse=True)
    return [summary for _, summary in found]
