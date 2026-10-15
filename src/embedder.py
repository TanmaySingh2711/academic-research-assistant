"""Embeddings: turn chunk text into vectors with the local all-MiniLM-L6-v2 model."""

import threading
from typing import Any

import numpy as np

from src.schema import Chunk

# The embedding model used for both chunks and questions
MODEL_NAME = "all-MiniLM-L6-v2"

# Cached model, so the slow loading happens only once
_model: Any = None
_model_lock = threading.Lock()  # two requests at the same time still load the model only once


def load_model() -> Any:
    """Load the SentenceTransformer model once and reuse it on later calls."""
    global _model
    with _model_lock:
        if _model is None:
            # Imported here, not at the top: sentence-transformers (with PyTorch) takes about 8 seconds
            # to import, and the app can already start and show its pages while that happens.
            from sentence_transformers import SentenceTransformer

            # First run downloads the model from Hugging Face (free, no login), then it is cached locally
            _model = SentenceTransformer(MODEL_NAME)
    return _model


def embed_texts(texts: list[str], batch_size: int = 32, show_progress: bool = True) -> np.ndarray:
    """Embed a list of strings and return a float32 array of shape (len(texts), embedding_size)."""
    model = load_model()
    embeddings = model.encode(
        texts,
        batch_size=batch_size,
        show_progress_bar=show_progress,
        convert_to_numpy=True,
        normalize_embeddings=False,  # normalization happens in vector_store.normalize_vectors
    )
    return embeddings.astype(np.float32)


def embed_chunks(chunks: list[Chunk]) -> np.ndarray:
    """Embed the text of each chunk; row i of the result belongs to chunks[i]."""
    texts = [chunk["text"] for chunk in chunks]
    return embed_texts(texts)
