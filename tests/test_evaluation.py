"""Quality gate: retrieval on the evaluation corpus must stay good (see evaluation/evaluate.py)."""

import json
from pathlib import Path

import pytest

from evaluation.corpus import PAPERS, build_corpus
from evaluation.evaluate import QUESTIONS_FILE, contains, evaluate_retrieval, first_hit_rank, has_facts
from src.ingest import run_ingestion
from src.vector_store import load_store


@pytest.fixture(scope="module")
def corpus_store(tmp_path_factory: pytest.TempPathFactory) -> tuple:
    root = tmp_path_factory.mktemp("eval")
    build_corpus(root / "corpus")
    run_ingestion(root / "corpus", root / "index")
    return load_store(root / "index")


def test_questions_file_is_valid() -> None:
    questions = json.loads(QUESTIONS_FILE.read_text(encoding="utf-8"))
    assert len(questions) >= 60
    for item in questions:
        assert item["paper"] in PAPERS
        if item["type"] != "not_found":
            pages = len(PAPERS[item["paper"]]["pages"])
            assert item["pages"] and all(1 <= page <= pages for page in item["pages"])
            assert item["keywords"] and all(group for group in item["keywords"])


def test_keyword_matching() -> None:
    assert contains("It found 9 crashes", "9") and not contains("It found 89 crashes", "9")
    assert not contains("a value of 0.050", "0.05") and contains("Anonymised data", "anonymi")
    assert has_facts("Unity and Unreal", [["Unity"], ["Unreal", "Godot"]])
    assert not has_facts("Unity only", [["Unity"], ["Unreal"]])
    results = [{"rank": 1, "page": 2, "text": "nothing"}, {"rank": 2, "page": 2, "text": "threshold 0.035"}]
    assert first_hit_rank(results, {"pages": [2], "keywords": [["0.035"]]}) == 2  # type: ignore[arg-type]


def test_retrieval_quality(corpus_store: tuple) -> None:
    index, chunks, _ = corpus_store
    questions = json.loads(QUESTIONS_FILE.read_text(encoding="utf-8"))
    metrics = evaluate_retrieval(questions, index, chunks, k=3)
    assert metrics["hit@3"] >= 0.95
    assert metrics["mrr"] >= 0.9


def test_corpus_pdfs_have_the_layout_of_real_papers(tmp_path: Path) -> None:
    paths = build_corpus(tmp_path)
    assert [p.name for p in paths] == list(PAPERS)
    assert all(p.read_bytes().startswith(b"%PDF") for p in paths)
