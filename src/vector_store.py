"""Vector store: keep chunk vectors in a FAISS index and save/load it with the chunk metadata."""

import json
from pathlib import Path
from typing import Any

import faiss
import numpy as np

from src.schema import Chunk

INDEX_FILE = "faiss.index"
CHUNKS_FILE = "chunks.json"
INFO_FILE = "info.json"


def normalize_vectors(vectors: Any) -> np.ndarray:
    """Scale every row to length 1 (divide each row by its own norm)."""
    vectors = np.asarray(vectors, dtype=np.float32)
    # Norm (length) of each row: sqrt(x1^2 + x2^2 + ... + xn^2), kept as a column for broadcasting
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    # Guard against division by zero: an all-zero row stays all zeros
    norms[norms == 0] = 1.0
    return (vectors / norms).astype(np.float32)


def build_index(vectors: Any) -> Any:
    """Normalize the vectors and put them in a FAISS IndexFlatIP."""
    vectors = normalize_vectors(vectors)
    dimension = vectors.shape[1]  # 384 for all-MiniLM-L6-v2

    # IndexFlatIP scores by inner product (dot product). For vectors of length 1,
    # cosine similarity = dot(a, b) / (|a| * |b|) = dot(a, b) / (1 * 1) = dot(a, b),
    # so this index ranks chunks by cosine similarity.
    # "Flat" means no shortcuts: every search compares against every stored vector
    # (exact search). That is fast enough for a few hundred or thousand chunks.
    index = faiss.IndexFlatIP(dimension)
    index.add(vectors)  # row i of vectors becomes vector i in the index
    return index


def all_vectors(index: Any) -> np.ndarray:
    """Every stored vector, row i = vector i. A Flat index keeps them unchanged, so they can be read back."""
    if index.ntotal == 0:
        return np.zeros((0, index.d), dtype=np.float32)
    return index.reconstruct_n(0, index.ntotal)


def remove_paper(index: Any, chunks: list[Chunk], source: str) -> tuple[Any, list[Chunk]]:
    """Return a new (index, chunks) without one paper. Nothing is embedded again, so it is fast.

    The other vectors are copied as they are, leaving out the rows of that paper.
    Row i still matches chunks[i] afterwards.
    """
    keep = [row for row, chunk in enumerate(chunks) if chunk["source"] != source]
    new_index = faiss.IndexFlatIP(index.d)
    if keep:
        new_index.add(all_vectors(index)[keep])
    return new_index, renumber([chunks[row] for row in keep])


def renumber(chunks: list[Chunk]) -> list[Chunk]:
    """Make chunk_id equal to the row number again (after chunks were removed or added)."""
    for row, chunk in enumerate(chunks):
        chunk["chunk_id"] = row
    return chunks


def save_store(index: Any, chunks: list[Chunk], index_dir: str | Path, info: dict[str, Any]) -> None:
    """Save the index, the chunks (same order as the vectors) and the build info to index_dir.

    info holds how the index was built (model, chunk size, ...) and one entry per indexed paper
    (see src/ingest.py); the vector count and size are filled in here.
    """
    index_dir = Path(index_dir)
    index_dir.mkdir(parents=True, exist_ok=True)

    faiss.write_index(index, str(index_dir / INDEX_FILE))

    # Row i in the index = chunks[i], so the list order must not change
    with open(index_dir / CHUNKS_FILE, "w", encoding="utf-8") as f:
        json.dump(chunks, f, ensure_ascii=False, indent=2)

    info = {**info, "embedding_dimension": index.d, "num_chunks": len(chunks)}
    with open(index_dir / INFO_FILE, "w", encoding="utf-8") as f:
        json.dump(info, f, indent=2)


def load_store(index_dir: str | Path) -> tuple[Any, list[Chunk], dict[str, Any]]:
    """Load and return (index, chunks, info) from index_dir."""
    index_dir = Path(index_dir)
    paths = [index_dir / INDEX_FILE, index_dir / CHUNKS_FILE, index_dir / INFO_FILE]
    missing = [p.name for p in paths if not p.exists()]
    if missing:
        raise FileNotFoundError(
            f"Missing {', '.join(missing)} in '{index_dir}'. Build the index first: python scripts/build_index.py"
        )

    index = faiss.read_index(str(paths[0]))
    with open(paths[1], encoding="utf-8") as f:
        chunks = json.load(f)
    with open(paths[2], encoding="utf-8") as f:
        info = json.load(f)

    # Every vector needs a matching chunk, otherwise row numbers point to the wrong text
    if index.ntotal != len(chunks):
        raise ValueError(
            f"Index is out of date: {index.ntotal} vectors but {len(chunks)} chunks. "
            "Rebuild it: python scripts/build_index.py"
        )

    return index, chunks, info
