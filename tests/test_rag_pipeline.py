"""src/rag_pipeline.py: the whole path from question to answer with sources (fake LLM)."""

from pathlib import Path

import pytest

from src.rag_pipeline import answer_question, answer_question_stream, find_chunks
from src.schema import Turn
from src.vector_store import load_store
from tests.conftest import PAPER, FakeLLM


@pytest.fixture
def store(sample_index: tuple[Path, Path]) -> tuple:
    return load_store(sample_index[1])


def test_answer_with_sources(store: tuple, fake_llm: FakeLLM) -> None:
    index, chunks, _ = store
    result = answer_question("What reward function does the agent use?", index, chunks, k=3, source=PAPER)
    assert result["answer"].endswith("[Source 1]")
    assert not result["not_found"]
    assert [s["source_number"] for s in result["sources"]] == [1, 2, 3]
    assert all(s["source"] == PAPER for s in result["sources"])
    assert result["k"] == 3 and result["prompt_tokens"] == 100


def test_not_found_has_no_sources(store: tuple, fake_llm: FakeLLM) -> None:
    index, chunks, _ = store
    result = answer_question("What is the capital of France?", index, chunks, source=PAPER)
    assert result["not_found"] and result["sources"] == []


def test_history_reaches_the_prompt_and_the_search(store: tuple, fake_llm: FakeLLM) -> None:
    index, chunks, _ = store
    history: list[Turn] = [{"question": "What is the cautious curiosity agent?", "answer": "An agent that explores."}]
    answer_question("How was it evaluated?", index, chunks, k=1, source=PAPER, history=history)
    assert "Q: What is the cautious curiosity agent?" in fake_llm.calls[-1][-1]["content"]
    assert "judges" in find_chunks("How was it evaluated?", index, chunks, k=1, source=PAPER,
                                   history=history)[0]["text"]


def test_stream_gives_sources_tokens_and_done(store: tuple, fake_llm: FakeLLM) -> None:
    index, chunks, _ = store
    events = list(answer_question_stream("What reward does the agent get?", index, chunks, k=2, source=PAPER))
    assert events[0]["type"] == "sources" and len(events[0]["results"]) == 2
    tokens = [e["text"] for e in events if e["type"] == "token"]
    assert events[-1]["type"] == "done"
    final = events[-1]["result"]
    assert final["answer"] == "".join(tokens).strip()
    assert final == answer_question("What reward does the agent get?", index, chunks, k=2, source=PAPER)  \
        | {"seconds": final["seconds"]}
