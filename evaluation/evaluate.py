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

Splitting the work (CI runs the answers on 4 machines at the same time):
  python -m evaluation.evaluate --answers --shard 1/4 --save part1.json    every 4th question, saved
  python -m evaluation.evaluate --combine part*.json --min-correct 0.9     one report for all parts
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
from src.schema import Chunk, SearchResult, Turn

# The search and answer code (PyTorch, FAISS, ...) is imported only where it is needed, so
# --combine runs with the standard library alone.

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


def build_eval_index(data_dir: Path | None, chunk_size: int, overlap: int) -> tuple[Path, Path]:
    """Write the corpus (unless data_dir is given) and build a fresh index for it."""
    from src.ingest import run_ingestion

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


# ---------- Measuring: one record per question ----------

def retrieval_records(questions: list[dict], index: Any, chunks: list[Chunk], k: int, method: str) -> list[dict]:
    """Search for every question and record the rank of the chunk with the answer."""
    from src.rag_pipeline import find_chunks

    records = []
    for item in questions:
        if item["type"] == "not_found":
            continue
        start = time.perf_counter()
        results = find_chunks(item["question"], index, chunks, k=10, source=item["paper"],
                              history=history_for(item, {}), method=method)
        rank = first_hit_rank(results, item)
        miss = None
        if rank is None or rank > k:
            got = ", ".join(f"p{r['page']}" for r in results[:k])
            miss = (f"  rank {rank or '-':>2} | {item['paper'][:22]:<22} | want p{item['pages']} got {got} | "
                    f"{item['question']}")
        records.append({"type": item["type"], "rank": rank, "miss": miss, "seconds": time.perf_counter() - start})
    return records


def answer_records(questions: list[dict], index: Any, chunks: list[Chunk], k: int) -> list[dict]:
    """Ask every question (the earlier turns of a follow-up first) and record whether the answer is right."""
    from src.rag_pipeline import answer_question

    answers: dict[str, str] = {}
    records = []
    for item in questions:
        start = time.perf_counter()
        # The earlier turns of a follow-up are asked first, so the history holds real answers
        for earlier in item.get("history", []):
            if earlier not in answers:
                answers[earlier] = answer_question(earlier, index, chunks, k=k, source=item["paper"])["answer"]
        result = answer_question(item["question"], index, chunks, k=k, source=item["paper"],
                                 history=history_for(item, answers))
        answer = result["answer"]
        cited = None  # only questions with an answer in the paper are checked for citations
        if item["type"] == "not_found":
            ok = result["not_found"]
        else:
            ok = not result["not_found"] and has_facts(answer, item["keywords"])
            numbers = {int(n) for n in CITATION.findall(answer)}
            pages = {s["page"] for s in result["sources"] if s["source_number"] in numbers}
            cited = bool(pages & set(item["pages"]))
        wrong = None if ok else f"  [{item['type']}] {item['question']}\n      -> {' '.join(answer.split())[:220]}"
        records.append({"type": item["type"], "ok": ok, "cited": cited, "wrong": wrong,
                        "seconds": time.perf_counter() - start})
        print("." if ok else "x", end="", flush=True)
    print()
    return records


# ---------- Reporting ----------

def report_retrieval(records: list[dict], k: int, method: str) -> dict:
    """Print Hit@1/3/5 and MRR per question type and return the numbers for all questions."""
    by_type: dict[str, list[int | None]] = defaultdict(list)
    for record in records:
        by_type[record["type"]].append(record["rank"])
        by_type["all"].append(record["rank"])

    def metrics(ranks: list[int | None]) -> dict:
        n = len(ranks)
        return {
            "n": n,
            **{f"hit@{cut}": sum(1 for r in ranks if r is not None and r <= cut) / n for cut in (1, 3, 5)},
            "mrr": sum(1 / r for r in ranks if r is not None) / n,
        }

    table = {kind: metrics(ranks) for kind, ranks in by_type.items()}
    per_question = sum(r["seconds"] for r in records) / len(records) * 1000
    print(f"Retrieval, method {method!r} (searching one paper, like the app; {per_question:.0f} ms per question)")
    print(f"  {'type':<11} {'n':>3} {'Hit@1':>7} {'Hit@3':>7} {'Hit@5':>7} {'MRR':>7}")
    for kind in ["all"] + sorted(kind for kind in table if kind != "all"):
        m = table[kind]
        print(f"  {kind:<11} {m['n']:>3} {m['hit@1']:>7.1%} {m['hit@3']:>7.1%} {m['hit@5']:>7.1%} {m['mrr']:>7.3f}")
    misses = [r["miss"] for r in records if r["miss"]]
    if misses:
        print(f"\n  Not in the top {k}:")
        print("\n".join(misses))
    print()
    return table["all"]


def report_answers(records: list[dict], k: int) -> dict:
    """Print the share of correct answers per question type and of correct citations."""
    totals: dict[str, list[int]] = defaultdict(lambda: [0, 0])  # type -> [correct, count]
    for record in records:
        for kind in (record["type"], "all"):
            totals[kind][0] += record["ok"]
            totals[kind][1] += 1
    checked = [r["cited"] for r in records if r["cited"] is not None]
    per_question = sum(r["seconds"] for r in records) / len(records)

    print(f"\nAnswers (llama3.2:3b, k={k}; {per_question:.1f} s per question)")
    for kind in ["all"] + sorted(kind for kind in totals if kind != "all"):
        correct, count = totals[kind]
        print(f"  {kind:<11} {correct:>3}/{count:<3} {correct / count:>7.1%}")
    print(f"  cited the correct page: {sum(checked)}/{len(checked)} ({sum(checked) / len(checked):.1%})")
    wrong = [r["wrong"] for r in records if r["wrong"]]
    if wrong:
        print("\n  Wrong:")
        print("\n".join(wrong))
    print()
    return {"correct": totals["all"][0] / totals["all"][1], "cited": sum(checked) / len(checked)}


def evaluate_retrieval(questions: list[dict], index: Any, chunks: list[Chunk], k: int,
                       method: str | None = None) -> dict:
    """Measure and report retrieval in one call."""
    from src.retriever import DEFAULT_METHOD

    method = method or DEFAULT_METHOD
    return report_retrieval(retrieval_records(questions, index, chunks, k, method), k, method)


def check_gates(retrieval: dict, answers: dict | None, min_hit3: float | None, min_correct: float | None) -> None:
    """Exit with an error when a result is below its minimum (used by CI)."""
    if min_hit3 is not None and retrieval["hit@3"] < min_hit3:
        sys.exit(f"Hit@3 is {retrieval['hit@3']:.1%}, below the minimum of {min_hit3:.1%}")
    if answers is not None and min_correct is not None and answers["correct"] < min_correct:
        sys.exit(f"{answers['correct']:.1%} of the answers are correct, below the minimum of {min_correct:.1%}")


def shard(questions: list[dict], spec: str) -> list[dict]:
    """Every n-th question for part i of n ("2/4" = questions 2, 6, 10, ...)."""
    part, parts = (int(x) for x in spec.split("/"))
    if not 1 <= part <= parts:
        raise SystemExit(f"--shard must look like 1/4 (got {spec})")
    return questions[part - 1::parts]


def combine(files: list[Path], min_hit3: float | None, min_correct: float | None) -> None:
    """Join the records saved by --save and report them as one run."""
    parts = [json.loads(path.read_text(encoding="utf-8")) for path in files]
    k, method = parts[0]["k"], parts[0]["method"]
    retrieval = report_retrieval([r for part in parts for r in part["retrieval"]], k, method)
    answers = None
    if all(part["answers"] is not None for part in parts):
        answers = report_answers([r for part in parts for r in part["answers"]], k)
    check_gates(retrieval, answers, min_hit3, min_correct)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--answers", action="store_true", help="also ask the LLM (needs Ollama)")
    parser.add_argument("--k", type=int, default=3, help="chunks given to the LLM (default 3, like the app)")
    parser.add_argument("--data", type=Path, help="folder with your own PDFs (needs --questions)")
    parser.add_argument("--questions", type=Path, default=QUESTIONS_FILE, help="questions file")
    parser.add_argument("--method", help="vector, bm25, hybrid or rerank (default: the app's method); "
                                         "'compare' runs every method (retrieval only)")
    parser.add_argument("--chunk-size", type=int, help="words per chunk (default: the app's setting)")
    parser.add_argument("--overlap", type=int, help="overlap in words (default: the app's setting)")
    parser.add_argument("--shard", help="run only part of the questions, like 1/4")
    parser.add_argument("--save", type=Path, help="save the results of every question to this JSON file")
    parser.add_argument("--combine", type=Path, nargs="+", help="report the files saved by --save as one run")
    parser.add_argument("--min-hit3", type=float, help="fail if Hit@3 is below this value (0 to 1)")
    parser.add_argument("--min-correct", type=float, help="fail if the share of correct answers is lower (0 to 1)")
    args = parser.parse_args()

    if args.combine:
        combine(args.combine, args.min_hit3, args.min_correct)
        return

    from src.ingest import CHUNK_SIZE, OVERLAP
    from src.retriever import DEFAULT_METHOD, METHODS
    from src.vector_store import load_store

    method = args.method or DEFAULT_METHOD
    if method not in METHODS + ("compare",):
        parser.error(f"--method must be one of {', '.join(METHODS)} or compare")

    questions = json.loads(args.questions.read_text(encoding="utf-8"))
    if args.shard:
        questions = shard(questions, args.shard)
    chunk_size = args.chunk_size or CHUNK_SIZE
    overlap = OVERLAP if args.overlap is None else args.overlap
    _, index_dir = build_eval_index(args.data, chunk_size, overlap)
    index, chunks, _ = load_store(index_dir)

    if method == "compare":
        for each in METHODS:
            report_retrieval(retrieval_records(questions, index, chunks, args.k, each), args.k, each)
        return

    found = retrieval_records(questions, index, chunks, args.k, method)
    retrieval = report_retrieval(found, args.k, method)
    asked = answer_records(questions, index, chunks, args.k) if args.answers else None
    answers = report_answers(asked, args.k) if asked else None

    if args.save:
        args.save.parent.mkdir(parents=True, exist_ok=True)
        args.save.write_text(json.dumps({"k": args.k, "method": method, "retrieval": found, "answers": asked},
                                        indent=2), encoding="utf-8")
    check_gates(retrieval, answers, args.min_hit3, args.min_correct)


if __name__ == "__main__":
    main()
