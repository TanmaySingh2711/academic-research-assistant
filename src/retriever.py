"""Retrieval: turn a question into a vector and find the top-k most similar chunks in FAISS."""

from src.embedder import MODEL_NAME, embed_texts
from src.vector_store import normalize_vectors


def embed_query(question):
    """Embed the question with the SAME model as the chunks and normalize it. Shape: (1, 384)."""
    vector = embed_texts([question], show_progress=False)
    # Normalized query . normalized chunk = cosine similarity (same as the index)
    return normalize_vectors(vector)


def retrieve(question, index, chunks, k=3, source=None):
    """Return the k chunks most similar to the question, best first.

    If source is a filename, only chunks from that paper are returned.
    """
    if not question or not question.strip():
        raise ValueError("Question is empty. Please type a question.")
    if k < 1:
        raise ValueError(f"k must be at least 1 (got {k})")
    k = min(k, len(chunks))  # cannot return more chunks than we have

    query = embed_query(question)
    # For one paper, rank ALL chunks and keep that paper's best k.
    # Exact search over a few hundred chunks takes only milliseconds.
    search_k = index.ntotal if source else k
    # FAISS returns two (1, search_k) arrays: similarity scores and row numbers, best first
    scores, ids = index.search(query, search_k)

    results = []
    for score, row in zip(scores[0], ids[0]):
        chunk = chunks[row]  # row i in the index = chunks[i]
        if source and chunk["source"] != source:
            continue
        results.append({
            "rank": len(results) + 1,
            "score": round(float(score), 4),
            "chunk_id": chunk["chunk_id"],
            "source": chunk["source"],
            "page": chunk["page"],
            "text": chunk["text"],
        })
        if len(results) == k:
            break
    return results


def check_model_matches(info):
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
