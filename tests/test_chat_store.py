"""src/chat_store.py: saving, listing, renaming and deleting chats (one JSON file per chat)."""

from pathlib import Path

import pytest

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


def fake_result(question: str, answer: str = "An answer [Source 1].", not_found: bool = False, **extra: object) -> dict:
    """The same shape as the dictionary returned by answer_question()."""
    sources = [] if not_found else [{"source_number": 1, "source": "paper.pdf", "page": 2, "score": 0.8, "text": "t"}]
    return {"question": question, "answer": answer, "not_found": not_found, "sources": sources,
            "k": 3, "prompt_tokens": 600, "answer_tokens": 40, "seconds": 1.2, **extra}


def test_a_new_chat_and_a_follow_up(tmp_path: Path) -> None:
    assert list_chats(tmp_path) == []
    chat = add_exchange(tmp_path, None, "paper.pdf", fake_result("What is the main idea?"))
    assert len(chat["id"]) == 12 and chat["paper"] == "paper.pdf"
    assert chat["title"] == "What is the main idea?"
    assert [m["role"] for m in chat["messages"]] == ["user", "assistant"]

    add_exchange(tmp_path, chat["id"], "paper.pdf", fake_result("And the results?", "They are good."))
    saved = get_chat(tmp_path, chat["id"])
    assert len(saved["messages"]) == 4
    assert saved["messages"][3]["sources"][0]["text"] == "t"
    assert get_history(tmp_path, chat["id"]) == [
        {"question": "What is the main idea?", "answer": "An answer [Source 1]."},
        {"question": "And the results?", "answer": "They are good."},
    ]


def test_new_id_given_in_advance_and_stopped_answers(tmp_path: Path) -> None:
    chat_id = new_chat_id()
    chat = add_exchange(tmp_path, None, "paper.pdf", fake_result("Q?", stopped=True), new_id=chat_id)
    assert chat["id"] == chat_id
    assert chat["messages"][1]["stopped"] is True
    second = add_exchange(tmp_path, chat_id, "paper.pdf", fake_result("Q2?"))
    assert "stopped" not in second["messages"][3]


def test_list_is_newest_first_with_summaries(tmp_path: Path) -> None:
    first = add_exchange(tmp_path, None, "a.pdf", fake_result("First?"))
    add_exchange(tmp_path, first["id"], "a.pdf", fake_result("More?"))
    second = add_exchange(tmp_path, None, "b.pdf", fake_result("Capital?", "I could not find this.", True))
    summaries = list_chats(tmp_path)
    assert [s["id"] for s in summaries] == [second["id"], first["id"]]
    assert summaries[1]["questions"] == 2 and summaries[0]["preview"] == "I could not find this."
    (tmp_path / "broken.json").write_text("{not json")
    (tmp_path / "half.json").write_text('{"id": "x"}')
    assert len(list_chats(tmp_path)) == 2  # broken files are skipped


def test_rename(tmp_path: Path) -> None:
    chat = add_exchange(tmp_path, None, "a.pdf", fake_result("Q?"))
    assert rename_chat(tmp_path, chat["id"], "  My   chat \n")["title"] == "My chat"
    assert rename_chat(tmp_path, chat["id"], "x" * 100)["title"] == "x" * 60
    with pytest.raises(ValueError):
        rename_chat(tmp_path, chat["id"], "   ")


def test_delete(tmp_path: Path) -> None:
    a1 = add_exchange(tmp_path, None, "a.pdf", fake_result("1?"))
    add_exchange(tmp_path, None, "a.pdf", fake_result("2?"))
    b = add_exchange(tmp_path, None, "b.pdf", fake_result("3?"))
    delete_chat(tmp_path, a1["id"])
    with pytest.raises(KeyError):
        delete_chat(tmp_path, a1["id"])
    assert delete_chats_for_paper(tmp_path, "a.pdf") == 1
    assert [c["id"] for c in list_chats(tmp_path)] == [b["id"]]


@pytest.mark.parametrize("bad_id", ["../app", "ABCDEF123456", "123", None, 5])
def test_bad_ids_are_refused(tmp_path: Path, bad_id: object) -> None:
    with pytest.raises(KeyError):
        get_chat(tmp_path, bad_id)
