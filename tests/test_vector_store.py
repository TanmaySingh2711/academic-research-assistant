"""src/vector_store.py: the FAISS index, removing a paper, saving and loading."""

from pathlib import Path

import numpy as np
import pytest

from src.schema import Chunk
from src.vector_store import (
    all_vectors,
    build_index,
    load_store,
    normalize_vectors,
    remove_paper,
    renumber,
    save_store,
)


def chunks_for(sources: list[str]) -> list[Chunk]:
    return [{"chunk_id": i, "source": s, "page": 1, "text": f"chunk {i}", "word_count": 2}
            for i, s in enumerate(sources)]


def random_vectors(n: int) -> np.ndarray:
    return np.random.default_rng(0).normal(size=(n, 384)).astype(np.float32)


def test_normalize_vectors_gives_length_one() -> None:
    vectors = normalize_vectors([[3.0, 4.0], [0.0, 0.0]])
    assert np.allclose(np.linalg.norm(vectors[0]), 1.0)
    assert np.allclose(vectors[1], 0.0)  # an all-zero row stays zero (no division by zero)


def test_every_vector_finds_itself_with_score_one() -> None:
    vectors = random_vectors(20)
    index = build_index(vectors)
    scores, ids = index.search(normalize_vectors(vectors[[3, 17]]), 1)
    assert ids[:, 0].tolist() == [3, 17]
    assert np.allclose(scores[:, 0], 1.0, atol=1e-5)


def test_remove_paper_keeps_the_other_vectors_in_order() -> None:
    vectors = random_vectors(6)
    index = build_index(vectors)
    chunks = chunks_for(["a.pdf", "b.pdf", "a.pdf", "c.pdf", "b.pdf", "c.pdf"])
    new_index, new_chunks = remove_paper(index, chunks, "b.pdf")
    assert [c["text"] for c in new_chunks] == ["chunk 0", "chunk 2", "chunk 3", "chunk 5"]
    assert [c["chunk_id"] for c in new_chunks] == [0, 1, 2, 3]  # row i = chunk_id i again
    assert np.allclose(all_vectors(new_index), normalize_vectors(vectors[[0, 2, 3, 5]]), atol=1e-6)

    empty_index, empty = remove_paper(build_index(vectors[:1]), chunks_for(["a.pdf"]), "a.pdf")
    assert empty == [] and empty_index.ntotal == 0 and all_vectors(empty_index).shape == (0, 384)


def test_renumber() -> None:
    chunks = chunks_for(["a", "b"])
    chunks[0]["chunk_id"], chunks[1]["chunk_id"] = 7, 9
    assert [c["chunk_id"] for c in renumber(chunks)] == [0, 1]


def test_save_and_load(tmp_path: Path) -> None:
    index = build_index(random_vectors(3))
    save_store(index, chunks_for(["a", "a", "b"]), tmp_path / "nested" / "index", {"model_name": "m", "papers": {}})
    loaded, chunks, info = load_store(tmp_path / "nested" / "index")
    assert loaded.ntotal == 3 and len(chunks) == 3
    assert info == {"model_name": "m", "papers": {}, "embedding_dimension": 384, "num_chunks": 3}


def test_load_store_errors(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="Build the index first"):
        load_store(tmp_path)
    save_store(build_index(random_vectors(2)), chunks_for(["a"] * 3), tmp_path, {})  # 2 vectors, 3 chunks
    with pytest.raises(ValueError, match="out of date"):
        load_store(tmp_path)
