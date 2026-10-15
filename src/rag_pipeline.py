"""RAG pipeline: question -> retrieve chunks -> build prompt -> generate answer with sources."""

from collections.abc import Iterator
from typing import Any

from src.generator import generate_answer, is_not_found, stream_answer
from src.prompt_builder import build_messages, get_sources
from src.retriever import DEFAULT_METHOD, retrieve
from src.schema import Chunk, Message, SearchResult, Turn


def find_chunks(question: str, index: Any, chunks: list[Chunk], k: int = 3, source: str | None = None,
                history: list[Turn] | None = None, method: str = DEFAULT_METHOD) -> list[SearchResult]:
    """The chunks the answer will be based on, best first. A follow-up question is also searched
    together with the previous question of the chat (see retrieve)."""
    previous = history[-1]["question"] if history else None
    return retrieve(question, index, chunks, k=k, source=source, method=method, previous=previous)


def prepare(question: str, index: Any, chunks: list[Chunk], k: int, source: str | None,
            history: list[Turn] | None) -> tuple[list[SearchResult], list[Message]]:
    """Retrieve the chunks and build the prompt for the LLM."""
    results = find_chunks(question, index, chunks, k=k, source=source, history=history)
    return results, build_messages(question, results, history)


def make_result(question: str, k: int, results: list[SearchResult], generated: dict[str, Any]) -> dict[str, Any]:
    """The answer with its sources, as the app returns and saves it."""
    not_found = is_not_found(generated["answer"])
    return {
        "question": question,
        "answer": generated["answer"],
        "not_found": not_found,
        # No sources when the model says the answer is not in the papers
        "sources": [] if not_found else get_sources(results),
        "k": k,
        "prompt_tokens": generated["prompt_tokens"],
        "answer_tokens": generated["answer_tokens"],
        "seconds": generated["seconds"],
    }


def answer_question(question: str, index: Any, chunks: list[Chunk], k: int = 3, source: str | None = None,
                    history: list[Turn] | None = None) -> dict[str, Any]:
    """Answer a question from the indexed papers.

    source: a paper filename to search only that paper, or None to search all papers.
    history: earlier questions and answers of the same chat, oldest first.
    """
    results, messages = prepare(question, index, chunks, k, source, history)
    return make_result(question, k, results, generate_answer(messages))


def answer_question_stream(question: str, index: Any, chunks: list[Chunk], k: int = 3, source: str | None = None,
                           history: list[Turn] | None = None) -> Iterator[dict[str, Any]]:
    """Like answer_question, but the answer arrives piece by piece. This is what the app uses.

    Yields {"type": "sources", "results": [...]} once the chunks are found, then {"type": "token",
    "text": "..."} for every piece of the answer, and finally {"type": "done", "result": {...}}
    with the same dictionary answer_question returns.
    """
    results, messages = prepare(question, index, chunks, k, source, history)
    yield {"type": "sources", "results": results}
    pieces: list[str] = []
    for event in stream_answer(messages):
        if "token" in event:
            pieces.append(event["token"])
            yield {"type": "token", "text": event["token"]}
        else:
            generated = {**event, "answer": "".join(pieces).strip()}
            yield {"type": "done", "result": make_result(question, k, results, generated)}
