"""Re-ranking: a cross-encoder reads the question and a chunk TOGETHER and scores how well they match.

The embedding model (a bi-encoder) turns the question and each chunk into vectors separately,
which is fast enough to compare against every chunk, but it never sees both texts at once.
A cross-encoder sees both at once, so it judges much better whether a chunk really answers the
question, but it is too slow to run on every chunk. So: search first, then re-rank only the
best few candidates with the cross-encoder.
"""

import math
import threading
from typing import Any

# Small (22M parameters) model trained on MS MARCO, a large set of real search questions
MODEL_NAME = "cross-encoder/ms-marco-MiniLM-L6-v2"

_model: Any = None
_model_lock = threading.Lock()


def load_reranker() -> Any:
    """Load the cross-encoder once (downloaded on first use, then cached like the embedding model)."""
    global _model
    with _model_lock:
        if _model is None:
            from sentence_transformers import CrossEncoder  # imported here: slow import, see embedder.py

            _model = CrossEncoder(MODEL_NAME)
    return _model


def rerank_scores(question: str, texts: list[str]) -> list[float]:
    """A relevance score between 0 and 1 for each text (higher = answers the question better)."""
    if not texts:
        return []
    logits = load_reranker().predict([(question, text) for text in texts], show_progress_bar=False)
    # The model outputs raw scores (logits); the sigmoid turns them into 0..1
    return [1 / (1 + math.exp(-float(logit))) for logit in logits]
