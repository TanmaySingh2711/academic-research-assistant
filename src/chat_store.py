"""Chat history: every conversation is saved as one JSON file in the chats folder (storage/chats/).

A chat belongs to one paper (its filename), so the dashboard can group the chats by paper.
"""

import json
import re
import threading
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from src.schema import Turn

_lock = threading.Lock()  # one write at a time
_ID_PATTERN = re.compile(r"^[0-9a-f]{12}$")  # ids are 12 hex characters (no paths possible)
TITLE_LENGTH = 60
PREVIEW_LENGTH = 120


_last_time = datetime.min


def _now() -> str:
    """The current time, always later than the time returned before.

    The Windows clock can return the same time for a few milliseconds, so two chats saved
    right after each other would get the same time and could be listed in the wrong order."""
    global _last_time
    now = datetime.now()
    if now <= _last_time:
        now = _last_time + timedelta(microseconds=1)
    _last_time = now
    return now.isoformat(timespec="microseconds")


def _path(chats_dir: str | Path, chat_id: Any) -> Path:
    """File path of a chat. Raises KeyError for an invalid id."""
    if not isinstance(chat_id, str) or not _ID_PATTERN.match(chat_id):
        raise KeyError(chat_id)
    return Path(chats_dir) / f"{chat_id}.json"


def _save(chats_dir: str | Path, chat: dict[str, Any]) -> None:
    """Write the chat to a temporary file first, then swap it in, so a crash never leaves half a file."""
    Path(chats_dir).mkdir(parents=True, exist_ok=True)
    path = _path(chats_dir, chat["id"])
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(chat, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def get_chat(chats_dir: str | Path, chat_id: Any) -> dict[str, Any]:
    """Return the full chat. Raises KeyError if it does not exist (or its file is broken)."""
    path = _path(chats_dir, chat_id)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise KeyError(chat_id) from None


def new_chat_id() -> str:
    return uuid.uuid4().hex[:12]


def add_exchange(chats_dir: str | Path, chat_id: str | None, paper: str, result: dict[str, Any],
                 new_id: str | None = None) -> dict[str, Any]:
    """Save one question and its answer. Creates a new chat when chat_id is None
    (with the id new_id if given, so the page can know it before the answer is finished).

    result is the dictionary returned by answer_question(). Returns the updated chat.
    """
    with _lock:
        if chat_id is None:
            now = _now()
            chat = {
                "id": new_id or new_chat_id(),
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
            **({"stopped": True} if result.get("stopped") else {}),  # the user pressed Stop
        })
        chat["updated_at"] = now
        _save(chats_dir, chat)
        return chat


def get_history(chats_dir: str | Path, chat_id: Any) -> list[Turn]:
    """The questions and answers of a chat so far, oldest first. Raises KeyError if it does not exist."""
    messages = get_chat(chats_dir, chat_id)["messages"]
    questions = [m["content"] for m in messages if m["role"] == "user"]
    answers = [m["content"] for m in messages if m["role"] == "assistant"]
    return [{"question": q, "answer": a} for q, a in zip(questions, answers)]


def rename_chat(chats_dir: str | Path, chat_id: Any, title: str) -> dict[str, Any]:
    """Give a chat a new title. Raises KeyError if it does not exist, ValueError for an empty title."""
    title = " ".join(str(title).split())[:TITLE_LENGTH]  # one line, not too long
    if not title:
        raise ValueError("The chat name cannot be empty.")
    with _lock:
        chat = get_chat(chats_dir, chat_id)
        chat["title"] = title
        _save(chats_dir, chat)
        return chat


def delete_chat(chats_dir: str | Path, chat_id: Any) -> None:
    """Delete one chat. Raises KeyError if it does not exist."""
    with _lock:
        path = _path(chats_dir, chat_id)
        if not path.exists():
            raise KeyError(chat_id)
        path.unlink()


def delete_chats_for_paper(chats_dir: str | Path, paper: str) -> int:
    """Delete every chat about one paper. Returns how many."""
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


def list_chats(chats_dir: str | Path) -> list[dict[str, Any]]:
    """Return a short summary of every chat, newest first."""
    found: list[tuple[int, dict[str, Any]]] = []  # (file change time, summary) pairs
    for path in Path(chats_dir).glob("*.json"):
        try:
            chat = json.loads(path.read_text(encoding="utf-8"))
            modified = path.stat().st_mtime_ns
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
        except (OSError, ValueError, KeyError, TypeError):
            continue  # skip a broken file instead of failing the whole list
    # Newest first; the file change time decides when two saved times are equal
    found.sort(key=lambda pair: (pair[1]["updated_at"], pair[0]), reverse=True)
    return [summary for _, summary in found]
