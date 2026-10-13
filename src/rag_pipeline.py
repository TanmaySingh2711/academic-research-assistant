"""RAG pipeline: question -> retrieve chunks -> build prompt -> generate answer with sources."""

from src.generator import generate_answer, is_not_found
from src.prompt_builder import build_messages, get_sources
from src.retriever import retrieve


def answer_question(question, index, chunks, k=3):
    """Answer a question from the indexed papers. This is the function the Flask app calls."""
    results = retrieve(question, index, chunks, k=k)
    messages = build_messages(question, results)
    generated = generate_answer(messages)

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
