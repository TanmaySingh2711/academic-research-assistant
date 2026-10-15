"""src/suggestions.py: suggested questions for a paper (fake LLM)."""

import json
from pathlib import Path

from src.suggestions import (
    NUMBER_OF_QUESTIONS,
    SUGGESTIONS_FILE,
    build_messages,
    forget,
    get_suggestions,
    parse_questions,
)
from src.vector_store import load_store
from tests.conftest import PAPER, FakeLLM


def test_parse_questions_cleans_the_reply() -> None:
    reply = """Here are 4 questions about the paper:
1. What reward does the cautious curiosity agent use?
2) How is the agent compared with human players?
- "Why does curiosity follow an inverted U-shaped curve?"
* What reward does the cautious curiosity agent use?
Q5: Which game is used to test the agent?
What else?
"""
    assert parse_questions(reply) == [
        "What reward does the cautious curiosity agent use?",
        "How is the agent compared with human players?",
        "Why does curiosity follow an inverted U-shaped curve?",
        "Which game is used to test the agent?",
    ][:NUMBER_OF_QUESTIONS]
    assert parse_questions("Sorry, I cannot help with that.") == []


def test_build_messages() -> None:
    system, user = build_messages("Title. Abstract text.")
    assert system["role"] == "system" and "Title. Abstract text." in user["content"]


def test_questions_are_saved_per_paper(project: dict[str, Path], fake_llm: FakeLLM) -> None:
    _, chunks, info = load_store(project["index"])
    questions = get_suggestions(PAPER, chunks, info, project["index"])
    assert questions == ["What does the agent learn?", "How was it evaluated?", "Why is it useful?"]
    calls = len(fake_llm.calls)

    assert get_suggestions(PAPER, chunks, info, project["index"]) == questions
    assert len(fake_llm.calls) == calls  # read from suggestions.json, the model was not asked again

    saved = json.loads((project["index"] / SUGGESTIONS_FILE).read_text())
    assert saved["papers"][PAPER]["indexed_at"] == info["papers"][PAPER]["indexed_at"]

    # The paper was indexed again: new questions are written
    info["papers"][PAPER]["indexed_at"] = "2099-01-01T00:00:00"
    get_suggestions(PAPER, chunks, info, project["index"])
    assert len(fake_llm.calls) == calls + 1

    forget(PAPER, project["index"])
    assert PAPER not in json.loads((project["index"] / SUGGESTIONS_FILE).read_text())["papers"]
    assert get_suggestions("missing.pdf", chunks, info, project["index"]) == []
