"""Measure how well the assistant finds the right page and answers correctly.

It builds an index of the evaluation corpus (in .cache/eval, your own index is not touched), then
asks every question in evaluation/questions.json through the same functions the app uses.

Retrieval (no LLM needed, about a minute):
  Hit@K   share of questions where the chunk with the answer (correct page + expected facts) is in the top K
  MRR     mean reciprocal rank: 1 if the first correct chunk is ranked 1st, 1/2 if 2nd, ... (0 if not in top 10)

Answers (needs Ollama, a few minutes):
  correct     the answer contains every expected fact (keywords), or says "not found" when it should
  cited       the answer cites a [Source N] that comes from the correct page

Usage:
  python -m evaluation.evaluate                 retrieval only
  python -m evaluation.evaluate --answers       retrieval and answers
  python -m evaluation.evaluate --min-hit3 0.95                  fail if Hit@3 is lower (used by CI)
  python -m evaluation.evaluate --answers --min-correct 0.9      fail if fewer answers are correct
"""

import argparse
import json
import re
import shutil
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

from evaluation.corpus import build_corpus
from src.ingest import CHUNK_SIZE, OVERLAP, run_ingestion
from src.rag_pipeline import answer_question, find_chunks
from src.retriever import DEFAULT_METHOD, METHODS
from src.schema import Chunk, SearchResult, Turn
from src.vector_store import load_store

ROOT = Path(__file__).resolve().parent.parent
WORK_DIR = ROOT / ".cache" / "eval"
QUESTIONS_FILE = Path(__file__).resolve().parent / "questions.json"
CITATION = re.compile(r"\[Source (\d+)\]")


def contains(answer: str, keyword: str) -> bool:
    """True if the keyword is in the answer. Numbers must match whole ("9" does not match "89")."""
    answer, keyword = answer.lower(), keyword.lower()
    if any(ch.isdigit() for ch in keyword):
        return re.search(r"(?<![\d.])" + re.escape(keyword) + r"(?![\d])", answer) is not None
    return keyword in answer


def has_facts(answer: str, groups: list[list[str]]) -> bool:
    """Every group must match; inside a group any one of the alternatives is enough."""
    return all(any(contains(answer, keyword) for keyword in group) for group in groups)


def first_hit_rank(results: list[SearchResult], item: dict) -> int | None:
    """Rank of the first chunk that is on the correct page AND contains the expected facts.

    A chunk from the right page is not enough: a page is cut into several chunks, and only
    the one with the answer helps the LLM."""
    for result in results:
        if result["page"] in item["pages"] and has_facts(result["text"], item["keywords"]):
            return result["rank"]
    return None


def build_eval_index(data_dir: Path | None, chunk_size: int = CHUNK_SIZE, overlap: int = OVERLAP) -> tuple[Path, Path]:
    """Write the corpus (unless data_dir is given) and build a fresh index for it."""
    if WORK_DIR.exists():
        shutil.rmtree(WORK_DIR)
    index_dir = WORK_DIR / "index"
    if data_dir is None:
        data_dir = WORK_DIR / "corpus"
        build_corpus(data_dir)
    summary = run_ingestion(data_dir, index_dir, chunk_size=chunk_size, overlap=overlap)
    print(f"Index: {summary['pdfs']} PDFs, {summary['pages']} pages, {summary['chunks']} chunks "
          f"({summary['seconds']} s)\n")
    return data_dir, index_dir


def history_for(item: dict, answers: dict[str, str]) -> list[Turn]:
    """Earlier turns of the chat as [{"question", "answer"}]. The answer is filled in by --answers."""
    return [{"question": q, "answer": answers.get(q, "")} for q in item.get("history", [])]


def evaluate_retrieval(questions: list[dict], index: Any, chunks: list[Chunk], k: int,
                       method: str = DEFAULT_METHOD) -> dict:
    by_type: dict[str, list[int | None]] = defaultdict(list)
    misses = []
    start = time.perf_counter()
    for item in questions:
        if item["type"] == "not_found":
            continue
        results = find_chunks(item["question"], index, chunks, k=10, source=item["paper"],
                              history=history_for(item, {}), method=method)
        rank = first_hit_rank(results, item)
        by_type[item["type"]].append(rank)
        by_type["all"].append(rank)
        if rank is None or rank > k:
            got = ", ".join(f"p{r['page']}" for r in results[:k])
            misses.append(f"  rank {rank or '-':>2} | {item['paper'][:22]:<22} | want p{item['pages']} got {got} | "
                          f"{item['question']}")
    seconds = time.perf_counter() - start

    def metrics(ranks: list[int | None]) -> dict:
        n = len(ranks)
        return {
            "n": n,
            **{f"hit@{cut}": sum(1 for r in ranks if r is not None and r <= cut) / n for cut in (1, 3, 5)},
            "mrr": sum(1 / r for r in ranks if r is not None) / n,
        }

    table = {kind: metrics(ranks) for kind, ranks in by_type.items()}
    per_question = seconds / len(by_type["all"]) * 1000
    print(f"Retrieval, method {method!r} (searching one paper, like the app; {per_question:.0f} ms per question)")
    print(f"  {'type':<11} {'n':>3} {'Hit@1':>7} {'Hit@3':>7} {'Hit@5':>7} {'MRR':>7}")
    for kind in ["all"] + sorted(k for k in table if k != "all"):
        m = table[kind]
        print(f"  {kind:<11} {m['n']:>3} {m['hit@1']:>7.1%} {m['hit@3']:>7.1%} {m['hit@5']:>7.1%} {m['mrr']:>7.3f}")
    if misses:
        print(f"\n  Not in the top {k}:")
        print("\n".join(misses))
    print()
    return table["all"]


def evaluate_answers(questions: list[dict], index: Any, chunks: list[Chunk], k: int) -> dict:
    answers: dict[str, str] = {}
    totals: dict[str, list[int]] = defaultdict(lambda: [0, 0])  # type -> [correct, count]
    cited = [0, 0]
    wrong = []
    start = time.perf_counter()
    for item in questions:
        # The earlier turns of a follow-up are asked first, so the history holds real answers
        for earlier in item.get("history", []):
            if earlier not in answers:
                answers[earlier] = answer_question(earlier, index, chunks, k=k, source=item["paper"])["answer"]
        result = answer_question(item["question"], index, chunks, k=k, source=item["paper"],
                                 history=history_for(item, answers))
        answer = result["answer"]
        if item["type"] == "not_found":
            ok = result["not_found"]
        else:
            ok = not result["not_found"] and has_facts(answer, item["keywords"])
            numbers = {int(n) for n in CITATION.findall(answer)}
            pages = {s["page"] for s in result["sources"] if s["source_number"] in numbers}
            cited[0] += bool(pages & set(item["pages"]))
            cited[1] += 1
        for kind in (item["type"], "all"):
            totals[kind][0] += ok
            totals[kind][1] += 1
        if not ok:
            wrong.append(f"  [{item['type']}] {item['question']}\n      -> {' '.join(answer.split())[:220]}")
        print("." if ok else "x", end="", flush=True)
    seconds = time.perf_counter() - start

    print(f"\n\nAnswers (llama3.2:3b, k={k}; {seconds / totals['all'][1]:.1f} s per question)")
    for kind in ["all"] + sorted(k for k in totals if k != "all"):
        correct, count = totals[kind]
        print(f"  {kind:<11} {correct:>3}/{count:<3} {correct / count:>7.1%}")
    print(f"  cited the correct page: {cited[0]}/{cited[1]} ({cited[0] / cited[1]:.1%})")
    if wrong:
        print("\n  Wrong:")
        print("\n".join(wrong))
    print()
    return {"correct": totals["all"][0] / totals["all"][1], "cited": cited[0] / cited[1]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--answers", action="store_true", help="also ask the LLM (needs Ollama)")
    parser.add_argument("--k", type=int, default=3, help="chunks given to the LLM (default 3, like the app)")
    parser.add_argument("--data", type=Path, help="folder with your own PDFs (needs --questions)")
    parser.add_argument("--questions", type=Path, default=QUESTIONS_FILE, help="questions file")
    parser.add_argument("--method", choices=METHODS + ("compare",), default=DEFAULT_METHOD,
                        help="retrieval method; 'compare' runs every method (retrieval only)")
    parser.add_argument("--chunk-size", type=int, default=CHUNK_SIZE, help=f"words per chunk (default {CHUNK_SIZE})")
    parser.add_argument("--overlap", type=int, default=OVERLAP, help=f"overlap in words (default {OVERLAP})")
    parser.add_argument("--min-hit3", type=float, help="fail if Hit@3 is below this value (0 to 1)")
    parser.add_argument("--min-correct", type=float, help="fail if the share of correct answers is lower (0 to 1)")
    args = parser.parse_args()

    questions = json.loads(args.questions.read_text(encoding="utf-8"))
    _, index_dir = build_eval_index(args.data, args.chunk_size, args.overlap)
    index, chunks, _ = load_store(index_dir)

    if args.method == "compare":
        for method in METHODS:
            evaluate_retrieval(questions, index, chunks, args.k, method)
        return
    retrieval = evaluate_retrieval(questions, index, chunks, args.k, args.method)
    if args.answers:
        answers = evaluate_answers(questions, index, chunks, args.k)
        if args.min_correct is not None and answers["correct"] < args.min_correct:
            sys.exit(f"{answers['correct']:.1%} of the answers are correct, "
                     f"below the minimum of {args.min_correct:.1%}")

    if args.min_hit3 is not None and retrieval["hit@3"] < args.min_hit3:
        sys.exit(f"Hit@3 is {retrieval['hit@3']:.1%}, below the minimum of {args.min_hit3:.1%}")


if __name__ == "__main__":
    main()
