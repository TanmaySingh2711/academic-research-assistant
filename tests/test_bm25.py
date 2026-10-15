"""src/bm25.py: keyword search."""

from src.bm25 import BM25, tokenize
from src.schema import Chunk


def chunk(text: str) -> Chunk:
    return {"chunk_id": 0, "source": "p.pdf", "page": 1, "text": text, "word_count": len(text.split())}


def test_tokenize_keeps_numbers_and_drops_stopwords() -> None:
    assert tokenize("The threshold was 0.035 for 85,000 frames") == ["threshold", "0.035", "85000", "frame"]
    assert tokenize("Studies of levels") == ["study", "level"]


def test_exact_terms_score_highest() -> None:
    chunks = [chunk("The model reached an AUC of 0.87 on the test set."),
              chunk("The model was trained for many hours."),
              chunk("A different paper about racing games.")]
    scores = BM25(chunks).score("What AUC did the model reach?", [0, 1, 2])
    assert scores[0] > scores[1] > 0
    assert scores[2] == 0


def test_rare_words_count_more_than_common_ones() -> None:
    chunks = [chunk("agent agent agent LightGBM"), chunk("agent agent agent agent"), chunk("agent")]
    index = BM25(chunks)
    assert index.idf["lightgbm"] > index.idf["agent"]
    assert index.score("LightGBM agent", [0, 1])[0] > index.score("LightGBM agent", [0, 1])[1]


def test_empty_index_scores_nothing() -> None:
    assert BM25([]).score("anything", []) == []
