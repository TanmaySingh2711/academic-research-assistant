"""src/retriever.py and src/reranker.py: finding the chunks that answer a question."""

from pathlib import Path

import pytest

from src.reranker import load_reranker, rerank_scores
from src.retriever import METHODS, check_model_matches, retrieve
from src.vector_store import load_store
from tests.conftest import OTHER, PAPER


@pytest.fixture(scope="module")
def store(sample_index: tuple[Path, Path]) -> tuple:
    return load_store(sample_index[1])


@pytest.mark.parametrize("method", METHODS)
def test_every_method_finds_the_answer(store: tuple, method: str) -> None:
    index, chunks, _ = store
    results = retrieve("What reward function does the cautious curiosity agent use?", index, chunks, k=3,
                       method=method)
    assert [r["rank"] for r in results] == [1, 2, 3]
    assert results[0]["source"] == PAPER and results[0]["page"] == 1
    assert results[0]["score"] >= results[1]["score"] >= results[2]["score"]


def test_source_filter_keeps_one_paper(store: tuple) -> None:
    index, chunks, _ = store
    results = retrieve("How can reinforcement learning be used for load testing?", index, chunks, k=3, source=PAPER)
    assert results and all(r["source"] == PAPER for r in results)
    assert retrieve("anything", index, chunks, source="missing.pdf") == []


def test_k_larger_than_the_paper_returns_all_its_chunks(store: tuple) -> None:
    index, chunks, _ = store
    count = sum(1 for c in chunks if c["source"] == OTHER)
    assert len(retrieve("frame rate", index, chunks, k=50, source=OTHER)) == count


def test_rerank_scores_are_between_zero_and_one(store: tuple) -> None:
    index, chunks, _ = store
    results = retrieve("Which bugs can the platform inject?", index, chunks, k=3)
    assert all(0.0 <= r["score"] <= 1.0 for r in results)
    assert results[0]["score"] > 0.5


def test_previous_question_helps_a_follow_up(store: tuple) -> None:
    index, chunks, _ = store
    # "And how was it evaluated?" alone does not say which agent; the previous question does
    results = retrieve("And how was it evaluated?", index, chunks, k=1, source=PAPER,
                       previous="What is the cautious curiosity agent?")
    assert "judges" in results[0]["text"]


def test_bad_input_is_refused(store: tuple) -> None:
    index, chunks, _ = store
    with pytest.raises(ValueError, match="empty"):
        retrieve("   ", index, chunks)
    with pytest.raises(ValueError, match="at least 1"):
        retrieve("question", index, chunks, k=0)
    with pytest.raises(ValueError, match="method"):
        retrieve("question", index, chunks, method="magic")


def test_reranker() -> None:
    assert load_reranker() is load_reranker()
    good, bad = rerank_scores("How many bugs were found?", ["The agent found 12 bugs.", "Cakes need flour."])
    assert good > bad
    assert rerank_scores("question", []) == []


def test_check_model_matches() -> None:
    check_model_matches({"model_name": "sentence-transformers/all-MiniLM-L6-v2"})
    with pytest.raises(ValueError, match="different models"):
        check_model_matches({"model_name": "other-model"})
