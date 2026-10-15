"""src/embedder.py: sentences become 384-number vectors, similar meaning gives similar vectors."""

import numpy as np

from src.embedder import embed_chunks, embed_texts, load_model
from src.schema import Chunk


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))


def test_model_is_loaded_once() -> None:
    assert load_model() is load_model()


def test_vectors_have_384_numbers() -> None:
    vectors = embed_texts(["one sentence", "another sentence"], show_progress=False)
    assert vectors.shape == (2, 384)
    assert vectors.dtype == np.float32


def test_similar_meaning_is_closer() -> None:
    game, rl, cake = embed_texts([
        "An agent learns to play a video game using rewards.",
        "Reinforcement learning trains a game-playing agent.",
        "How to bake a chocolate cake at home.",
    ], show_progress=False)
    assert cosine(game, rl) > cosine(game, cake) + 0.3


def test_embed_chunks_keeps_the_order() -> None:
    chunks: list[Chunk] = [{"chunk_id": i, "source": "p.pdf", "page": 1, "text": t, "word_count": 1}
                           for i, t in enumerate(["cats", "planets"])]
    vectors = embed_chunks(chunks)
    cats, planets = embed_texts(["cats", "planets"], show_progress=False)
    assert np.allclose(vectors[0], cats, atol=1e-5) and np.allclose(vectors[1], planets, atol=1e-5)
