"""Vector store: keep chunk vectors in a FAISS index and save/load it with the chunk metadata."""

import json
from datetime import datetime
from pathlib import Path

import faiss
import numpy as np

INDEX_FILE = "faiss.index"
CHUNKS_FILE = "chunks.json"
INFO_FILE = "info.json"


def normalize_vectors(vectors):
    """Scale every row to length 1 (divide each row by its own norm)."""
    vectors = np.asarray(vectors, dtype=np.float32)
    # Norm (length) of each row: sqrt(x1^2 + x2^2 + ... + xn^2), kept as a column for broadcasting
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    # Guard against division by zero: an all-zero row stays all zeros
    norms[norms == 0] = 1.0
    return (vectors / norms).astype(np.float32)


def build_index(vectors):
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


def remove_paper(index, chunks, source):
    """Return a new (index, chunks) without one paper. Nothing is embedded again, so it is fast.

    A Flat index keeps the vectors as they are, so they can be read back and copied,
    leaving out the rows of that paper. Row i still matches chunks[i] afterwards.
    """
    keep = [row for row, chunk in enumerate(chunks) if chunk["source"] != source]
    vectors = index.reconstruct_n(0, index.ntotal)  # all stored vectors (already normalized)
    new_index = faiss.IndexFlatIP(index.d)
    if keep:
        new_index.add(vectors[keep])
    return new_index, [chunks[row] for row in keep]


def save_store(index, chunks, index_dir="index", model_name="all-MiniLM-L6-v2", chunk_size=100, overlap=20,
               built_at=None):
    """Save the index, the chunks (same order as the vectors) and build info to index_dir.

    built_at: when the index was built (default: now). Removing a paper keeps the old time,
    because the other papers were not indexed again.
    """
    index_dir = Path(index_dir)
    index_dir.mkdir(exist_ok=True)

    faiss.write_index(index, str(index_dir / INDEX_FILE))

    # Row i in the index = chunks[i], so the list order must not change
    with open(index_dir / CHUNKS_FILE, "w", encoding="utf-8") as f:
        json.dump(chunks, f, ensure_ascii=False, indent=2)

    info = {
        "model_name": model_name,
        "embedding_dimension": index.d,
        "num_chunks": len(chunks),
        "chunk_size": chunk_size,
        "overlap": overlap,
        "built_at": built_at or datetime.now().isoformat(timespec="seconds"),
    }
    with open(index_dir / INFO_FILE, "w", encoding="utf-8") as f:
        json.dump(info, f, indent=2)


def load_store(index_dir="index"):
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
