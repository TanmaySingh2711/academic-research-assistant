"""Quick test for src/vector_store.py: load the saved store, show normalization, and check the index order."""

import json
import sys
from pathlib import Path

import numpy as np

from src.vector_store import load_store, normalize_vectors

INDEX_DIR = "index"

index, chunks, info = load_store(INDEX_DIR)

print("=== info.json ===")
print(json.dumps(info, indent=2))

print("\n=== Index ===")
print(f"index.ntotal (vectors):  {index.ntotal}")
print(f"index.d (dimension):     {index.d}")
print(f"number of chunks:        {len(chunks)}")

print("\n=== Size on disk ===")
for name in ("faiss.index", "chunks.json"):
    print(f"  {name:<12} {(Path(INDEX_DIR) / name).stat().st_size / 1024:.1f} KB")

print("\n=== Normalization demo (random test vectors, not normalized) ===")
rng = np.random.default_rng(42)
test_vectors = rng.normal(size=(3, 384)).astype(np.float32)
normalized = normalize_vectors(test_vectors)
for i in range(3):
    print(f"  vector {i}: norm before = {np.linalg.norm(test_vectors[i]):.4f} | "
          f"after = {np.linalg.norm(normalized[i]):.4f}")

print("\n=== Sanity check: each stored vector should find itself ===")
failed = 0
for i in (0, len(chunks) // 2, len(chunks) - 1):
    vector = index.reconstruct(i).reshape(1, -1)  # FAISS expects a 2D array (1 query)
    scores, ids = index.search(vector, 1)
    found, score = int(ids[0][0]), float(scores[0][0])
    ok = found == i and abs(score - 1.0) < 1e-4
    failed += not ok
    print(f"  chunk {i:3} -> found chunk {found:3} | score {score:.4f} | "
          f"{chunks[found]['source'][:30]}..., page {chunks[found]['page']} | {'OK' if ok else 'FAIL'}")

if failed or index.ntotal != len(chunks):
    sys.exit("Vector store check failed")
