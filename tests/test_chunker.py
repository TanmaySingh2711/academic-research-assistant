"""Quick test for src/chunker.py: chunk all PDFs in data/ and print stats, samples and an overlap check."""

import sys
from collections import Counter

from src.chunker import chunk_pages
from src.loader import load_pdfs

OVERLAP = 20

pages = load_pdfs("data")
chunks = chunk_pages(pages, chunk_size=100, overlap=OVERLAP)

print("=== Totals ===")
print(f"Total pages:  {len(pages)}")
print(f"Total chunks: {len(chunks)}")

print("\n=== Chunks per PDF ===")
for source, count in sorted(Counter(c["source"] for c in chunks).items()):
    print(f"  {count:4}  {source}")

print("\n=== Word count per chunk ===")
counts = [c["word_count"] for c in chunks]
print(f"  smallest: {min(counts)} | largest: {max(counts)} | average: {sum(counts) / len(counts):.1f}")

print("\n=== 2 sample chunks ===")
for c in (chunks[0], chunks[len(chunks) // 2]):
    print(f"\n--- chunk_id={c['chunk_id']} | {c['source']} | page {c['page']} | {c['word_count']} words ---")
    print(c["text"])

print("\n=== Overlap proof ===")
# Find the first two neighbouring chunks that come from the same page
for a, b in zip(chunks, chunks[1:]):
    if a["source"] == b["source"] and a["page"] == b["page"]:
        end_of_a = a["text"].split()[-OVERLAP:]
        start_of_b = b["text"].split()[:OVERLAP]
        print(f"chunk {a['chunk_id']} and chunk {b['chunk_id']} ({a['source']}, page {a['page']})")
        print(f"\nLast {OVERLAP} words of chunk {a['chunk_id']}:\n  {' '.join(end_of_a)}")
        print(f"\nFirst {OVERLAP} words of chunk {b['chunk_id']}:\n  {' '.join(start_of_b)}")
        print(f"\nMatch: {end_of_a == start_of_b}")
        if end_of_a != start_of_b:
            sys.exit("Overlap check failed: neighbouring chunks do not share the overlap words")
        break

print("\n=== Experiment: chunk size vs overlap ===")
for size, ov in [(100, 20), (150, 30), (200, 40)]:
    print(f"  chunk_size={size:3}, overlap={ov:2} -> {len(chunk_pages(pages, size, ov))} chunks")
