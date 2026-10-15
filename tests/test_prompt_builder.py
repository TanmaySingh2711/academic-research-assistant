"""src/prompt_builder.py: the exact messages sent to the LLM."""

import pytest

from src.prompt_builder import (
    HISTORY_ANSWER_CHARS,
    HISTORY_TURNS,
    NOT_FOUND_MESSAGE,
    SYSTEM_PROMPT,
    build_messages,
    format_context,
    format_history,
    get_sources,
)
from src.schema import SearchResult, Turn


def result(rank: int, page: int, text: str) -> SearchResult:
    return {"rank": rank, "score": 0.9 - rank / 10, "chunk_id": rank, "source": "p.pdf", "page": page, "text": text}


RESULTS = [result(1, 3, "First chunk."), result(2, 5, "Second chunk.")]


def test_context_is_numbered_in_rank_order() -> None:
    expected = "[Source 1] p.pdf, page 3\nFirst chunk.\n\n[Source 2] p.pdf, page 5\nSecond chunk."
    assert format_context(RESULTS) == expected
    assert format_context([]) == ""


def test_messages_have_rules_context_question_and_reminder() -> None:
    system, user = build_messages("  What is it?  ", RESULTS)
    assert system == {"role": "system", "content": SYSTEM_PROMPT}
    assert NOT_FOUND_MESSAGE in system["content"]
    content = user["content"]
    assert content.startswith("Context:\n[Source 1]")
    assert "Question: What is it?\n" in content
    assert content.index("Context:") < content.index("Question:") < content.index("Remember:")
    assert "Earlier in this chat" not in content


def test_no_chunks_says_so() -> None:
    assert "Context:\nNo context found." in build_messages("Hi?", [])[1]["content"]


def test_empty_question_is_refused() -> None:
    with pytest.raises(ValueError):
        build_messages("   ", RESULTS)


def test_history_is_added_before_the_context() -> None:
    history: list[Turn] = [{"question": f"Q{i}?", "answer": f"A{i}."} for i in range(4)]
    content = build_messages("And then?", RESULTS, history)[1]["content"]
    assert content.startswith("Earlier in this chat")
    assert content.index("Earlier") < content.index("Context:")
    # only the last HISTORY_TURNS turns
    assert "Q0?" not in content and f"Q{4 - HISTORY_TURNS}?" in content and "Q3?\nA: A3." in content


def test_long_earlier_answers_are_shortened() -> None:
    text = format_history([{"question": "Q?", "answer": "word " * 400}])
    assert text.endswith(" ...")
    assert len(text) < HISTORY_ANSWER_CHARS + 20
    assert format_history(None) == "" and format_history([]) == ""


def test_sources_keep_the_numbers_and_text() -> None:
    assert get_sources(RESULTS) == [
        {"source_number": 1, "source": "p.pdf", "page": 3, "score": 0.8, "text": "First chunk."},
        {"source_number": 2, "source": "p.pdf", "page": 5, "score": 0.7, "text": "Second chunk."},
    ]
