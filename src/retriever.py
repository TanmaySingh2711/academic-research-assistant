"""Retrieval: find the chunks that best answer a question.

Methods (the evaluation in evaluation/evaluate.py compares them):
  "vector"  FAISS: the question vector against every chunk vector (cosine similarity)
  "bm25"    keyword search (src/bm25.py)
  "hybrid"  both rankings merged with reciprocal rank fusion
  "rerank"  hybrid, then the best CANDIDATES chunks are re-scored by a cross-encoder (src/reranker.py)
"""

from typing import Any

from src.bm25 import BM25
from src.embedder import MODEL_NAME, embed_texts
from src.reranker import rerank_scores
from src.schema import Chunk, SearchResult
from src.vector_store import normalize_vectors

DEFAULT_METHOD = "rerank"
METHODS = ("vector", "bm25", "hybrid", "rerank")
CANDIDATES = 20  # chunks the cross-encoder re-scores
RRF_K = 60  # standard constant of reciprocal rank fusion

# The BM25 index is built once per chunk list and reused for every question.
# Chunks and index are kept as one pair, replaced in one step, so a question asked while the
# index is being rebuilt never gets a BM25 index that belongs to other chunks.
_bm25_cache: tuple[list[Chunk] | None, BM25 | None] = (None, None)


def embed_query(question: str) -> Any:
    """Embed the question with the SAME model as the chunks and normalize it. Shape: (1, 384)."""
    vector = embed_texts([question], show_progress=False)
    # Normalized query . normalized chunk = cosine similarity (same as the index)
    return normalize_vectors(vector)


def bm25_for(chunks: list[Chunk]) -> BM25:
    global _bm25_cache
    cached_chunks, index = _bm25_cache
    if cached_chunks is not chunks or index is None:
        index = BM25(chunks)
        _bm25_cache = (chunks, index)
    return index


def vector_scores(question: str, index: Any, rows: list[int]) -> dict[int, float]:
    """Cosine similarity of the question with each chunk row in `rows`."""
    # Exact search over every vector takes only milliseconds for a few thousand chunks
    scores, ids = index.search(embed_query(question), index.ntotal)
    wanted = set(rows)
    return {int(row): float(score) for score, row in zip(scores[0], ids[0]) if row in wanted}


def ranking(scores: dict[int, float]) -> list[int]:
    """Rows sorted from best to worst score."""
    return sorted(scores, key=lambda row: scores[row], reverse=True)


def fuse(*rankings: list[int]) -> dict[int, float]:
    """Reciprocal rank fusion: every ranking gives a row 1 / (60 + its rank).

    Only the positions are used, not the raw scores, so a cosine similarity (0 to 1) and a
    BM25 score (0 to about 30) can be combined without rescaling them."""
    fused: dict[int, float] = {}
    for order in rankings:
        for rank, row in enumerate(order, start=1):
            fused[row] = fused.get(row, 0.0) + 1 / (RRF_K + rank)
    return fused


def retrieve(question: str, index: Any, chunks: list[Chunk], k: int = 3, source: str | None = None,
             method: str = DEFAULT_METHOD, previous: str | None = None) -> list[SearchResult]:
    """Return the k chunks that best answer the question, best first.

    If source is a filename, only chunks from that paper are searched.
    previous: the previous question of the chat. A follow-up like "And its recall?" does not say
    what "its" is, so the search also runs with "previous question + question", and every chunk
    keeps its better result. A question about a new topic still finds its chunks on its own.
    """
    if not question or not question.strip():
        raise ValueError("Question is empty. Please type a question.")
    if k < 1:
        raise ValueError(f"k must be at least 1 (got {k})")
    if method not in METHODS:
        raise ValueError(f"method must be one of {METHODS} (got {method!r})")

    rows = [row for row, chunk in enumerate(chunks) if source is None or chunk["source"] == source]
    if not rows:
        return []

    def keyword_scores(query: str) -> dict[int, float]:
        return dict(zip(rows, bm25_for(chunks).score(query, rows)))

    queries = [question] if not previous else [question, f"{previous} {question}"]
    rankings = []  # one ranking per query and search method, merged below
    for query in queries:
        if method in ("vector", "hybrid", "rerank"):
            rankings.append(ranking(vector_scores(query, index, rows)))
        if method in ("bm25", "hybrid", "rerank"):
            rankings.append(ranking(keyword_scores(query)))
    scores = fuse(*rankings)

    if method == "rerank":
        candidates = ranking(scores)[:CANDIDATES]
        texts = [chunks[row]["text"] for row in candidates]
        per_query = [rerank_scores(query, texts) for query in queries]
        scores = {row: max(found[i] for found in per_query) for i, row in enumerate(candidates)}
    elif len(rankings) == 1:
        # One plain ranking: show its own score (cosine similarity or BM25), not the fusion score
        scores = vector_scores(question, index, rows) if method == "vector" else keyword_scores(question)

    results: list[SearchResult] = []
    for row in ranking(scores)[:k]:
        chunk = chunks[row]
        results.append({
            "rank": len(results) + 1,
            "score": round(scores[row], 4),
            "chunk_id": chunk["chunk_id"],
            "source": chunk["source"],
            "page": chunk["page"],
            "text": chunk["text"],
        })
    return results


def check_model_matches(info: dict[str, Any]) -> None:
    """Raise an error if the index was built with a different model than the one embedder.py loads.

    Compares names only, so it is instant and does not need to load the model.
    """
    # Names can look like "sentence-transformers/all-MiniLM-L6-v2"; compare the part after "/"
    current = MODEL_NAME.split("/")[-1]
    built_with = info["model_name"].split("/")[-1]
    if current != built_with:
        raise ValueError(
            f"The index was built with '{built_with}' but the current model is '{current}'. "
            "Vectors from different models cannot be compared. Rebuild it: python scripts/build_index.py"
        )
