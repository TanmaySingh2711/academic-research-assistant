"""Quick test for src/retriever.py: ask questions, show top-k chunks, and compare k=1/3/5."""

import time

from src.embedder import load_model
from src.retriever import check_model_matches, retrieve
from src.vector_store import load_store

index, chunks, info = load_store("index")
check_model_matches(info)
load_model()  # load the model first, so the timings below do not include loading
print(f"Store loaded: {index.ntotal} vectors, model '{info['model_name']}' matches.\n")

QUESTIONS = [
    "What reward function does the cautious curiosity agent use?",
    "How can reinforcement learning be used for load testing of games?",
    "What kinds of bugs can the World of Bugs platform detect?",
    "How does an AI agent behave more like a human player?",
    "What is the capital of France?",
]


def short(name, length=25):
    """Shorten a filename for printing."""
    return name if len(name) <= length else name[:length] + "..."


for number, question in enumerate(QUESTIONS, start=1):
    start = time.perf_counter()
    results = retrieve(question, index, chunks, k=3)
    elapsed_ms = (time.perf_counter() - start) * 1000

    print(f"Q{number}: {question}  ({elapsed_ms:.1f} ms)")
    for r in results:
        text = r["text"][:150].replace("\n", " ")
        print(f"  #{r['rank']} score {r['score']:.4f} | {short(r['source'])} p{r['page']} | chunk {r['chunk_id']}")
        print(f"     {text}")
    print()

print("=== Top-K experiment (question 2) ===")
question = QUESTIONS[1]
by_k = {k: retrieve(question, index, chunks, k=k) for k in (1, 3, 5)}
print(f"{'rank':<5}" + "".join(f"| {'k=' + str(k):<36}" for k in by_k))
for rank in range(1, 6):
    row = f"{rank:<5}"
    for k, results in by_k.items():
        if rank <= len(results):
            r = results[rank - 1]
            row += f"| {r['score']:.4f} {short(r['source'], 20):<23} p{r['page']:<3} "
        else:
            row += f"| {'':<36}"
    print(row)

print("\n=== One paper only (source filter) ===")
paper = sorted({c["source"] for c in chunks})[0]
filtered = retrieve(QUESTIONS[1], index, chunks, k=3, source=paper)
for r in filtered:
    print(f"  #{r['rank']} score {r['score']:.4f} | {short(r['source'])} p{r['page']} | chunk {r['chunk_id']}")
if len(filtered) != 3 or any(r["source"] != paper for r in filtered) or [r["rank"] for r in filtered] != [1, 2, 3]:
    raise SystemExit(f"Source filter failed: expected 3 chunks from {paper} ranked 1, 2, 3")
print(f"  OK: all 3 results come from {short(paper)}")
