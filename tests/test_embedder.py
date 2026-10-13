"""Quick test for src/embedder.py: embed all chunks, check token lengths, and a small meaning demo."""

import time

import numpy as np

from src.chunker import chunk_pages
from src.embedder import embed_chunks, embed_texts, load_model
from src.loader import load_pdfs

pages = load_pdfs("data")
chunks = chunk_pages(pages)
model = load_model()  # load first, so the timing below measures only embedding

print("=== Embedding all chunks ===")
start = time.perf_counter()
embeddings = embed_chunks(chunks)
elapsed = time.perf_counter() - start

print(f"Chunks embedded: {len(chunks)}")
print(f"Time taken:      {elapsed:.2f} seconds")
print(f"Device:          {'GPU' if model.device.type == 'cuda' else 'CPU'} ({model.device})")
print(f"Shape:           {embeddings.shape}")
print(f"Dtype:           {embeddings.dtype}")
print(f"First 8 numbers of chunk 0: {np.round(embeddings[0][:8], 4)}")

print("\nVector length (norm) of the first 3 vectors (1.0 would mean normalized):")
for i in range(3):
    print(f"  chunk {i}: {np.linalg.norm(embeddings[i]):.4f}")

print("\n=== Token length check ===")
limit = model.max_seq_length
# Count tokens with the model's own tokenizer, including the special tokens [CLS] and [SEP]
token_counts = [len(model.tokenizer(c["text"])["input_ids"]) for c in chunks]
print(f"max_seq_length: {limit}")
print(f"Tokens per chunk: smallest {min(token_counts)} | largest {max(token_counts)} | "
      f"average {sum(token_counts) / len(token_counts):.1f}")

over = [(c, n) for c, n in zip(chunks, token_counts) if n > limit]
print(f"Chunks over the limit: {len(over)} of {len(chunks)}")
for c, n in over:
    print(f"  chunk_id={c['chunk_id']:3} | {c['source']} | page {c['page']} | {n} tokens")

print("\n=== Meaning demo: cosine similarity with sentence 1 ===")
sentences = [
    "An agent learns to play a video game using rewards.",
    "Reinforcement learning trains a game-playing agent.",
    "Automated tools can find bugs in 3D games.",
    "How to bake a chocolate cake at home.",
]
vecs = embed_texts(sentences, show_progress=False)
for i in range(1, len(sentences)):
    # cosine similarity = dot product / (norm of a * norm of b)
    cos = np.dot(vecs[0], vecs[i]) / (np.linalg.norm(vecs[0]) * np.linalg.norm(vecs[i]))
    print(f"  1 vs {i + 1}: {cos:.4f}  \"{sentences[i]}\"")
