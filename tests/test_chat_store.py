"""Test src/chat_store.py: saving, reading and listing chats (no LLM needed, uses a temp folder)."""

import sys
import tempfile

from src.chat_store import add_exchange, get_chat, list_chats

failures: list[str] = []


def check(ok, label):
    print(f"  {label:<50} {'OK' if ok else 'FAIL'}")
    if not ok:
        failures.append(label)


def fake_result(question, answer="An answer [Source 1].", not_found=False):
    """The same shape as the dictionary returned by answer_question()."""
    sources = [] if not_found else [{"source_number": 1, "source": "paper.pdf", "page": 2, "score": 0.8, "text": "t"}]
    return {"question": question, "answer": answer, "not_found": not_found, "sources": sources,
            "k": 3, "prompt_tokens": 600, "answer_tokens": 40, "seconds": 1.2}


with tempfile.TemporaryDirectory() as chats_dir:
    check(list_chats(chats_dir) == [], "empty folder gives an empty list")

    # A new chat is created on the first question
    chat = add_exchange(chats_dir, None, "paper.pdf", fake_result("What is the main idea?"))
    check(len(chat["id"]) == 12, "new chat gets a 12 character id")
    check(chat["paper"] == "paper.pdf", "chat remembers its paper")
    check(chat["title"] == "What is the main idea?", "first question becomes the title")
    check([m["role"] for m in chat["messages"]] == ["user", "assistant"], "one exchange = user + assistant message")

    # A follow-up question goes into the same chat
    add_exchange(chats_dir, chat["id"], "paper.pdf", fake_result("And the results?"))
    saved = get_chat(chats_dir, chat["id"])
    check(len(saved["messages"]) == 4, "follow-up is added to the same chat")
    check(saved["messages"][3]["sources"][0]["text"] == "t", "sources are saved with their chunk text")

    # A second chat about all papers
    other = add_exchange(chats_dir, None, None, fake_result("Capital of France?", "I could not find this.", True))
    summaries = list_chats(chats_dir)
    check(len(summaries) == 2, "list shows both chats")
    check(summaries[0]["id"] == other["id"], "newest chat comes first")
    check(summaries[0]["paper"] is None, "all-papers chat has paper None")
    check(summaries[1]["questions"] == 2, "summary counts the questions")

    # Bad ids are refused, so no file outside the folder can be read
    for bad_id in ["../app", "ABCDEF123456", "123", None]:
        try:
            get_chat(chats_dir, bad_id)
            check(False, f"bad id {bad_id!r} is refused")
        except KeyError:
            check(True, f"bad id {bad_id!r} is refused")

if failures:
    sys.exit(f"{len(failures)} check(s) failed: {failures}")
