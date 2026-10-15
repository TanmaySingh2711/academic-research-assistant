"""Prompt construction: combine the question, the earlier turns of the chat and the retrieved chunks
into chat messages for the LLM."""

from src.schema import Message, SearchResult, Source, Turn

# Exact reply when the answer is not in the context (Objective 8 checks for this sentence)
NOT_FOUND_MESSAGE = "I could not find this in the uploaded papers."

# Earlier questions and answers sent with a follow-up question, so "it" and "that" can be understood.
# Only the last few: older turns rarely matter and every word makes the model slower.
HISTORY_TURNS = 2
HISTORY_ANSWER_CHARS = 600  # long earlier answers are shortened

# Short, direct rules work best for a small (3B) model
SYSTEM_PROMPT = f"""You are a research assistant that answers questions about research papers.

Follow these rules:
1. Answer ONLY using the context given in the user message.
2. Do not use outside knowledge. Do not make up facts, numbers or citations.
3. Put the source number right after every fact, like [Source 1] or [Source 2].
   Do not write "according to the context"; cite the source instead.
4. If the context does not contain the answer, reply exactly: {NOT_FOUND_MESSAGE}
5. Keep the answer clear and short: a few sentences or a short list.
6. The earlier chat only explains what the question refers to. Facts must come from the context."""


def format_context(results: list[SearchResult]) -> str:
    """Turn retrieved results into one context string, one numbered block per chunk."""
    blocks = []
    for number, r in enumerate(results, start=1):  # results are already in rank order
        blocks.append(f"[Source {number}] {r['source']}, page {r['page']}\n{r['text']}")
    return "\n\n".join(blocks)  # empty list -> empty string


def format_history(history: list[Turn] | None) -> str:
    """The last few turns of the chat as text, oldest first ("" when there are none).

    They go inside the user message (not as separate chat messages): a small model given
    earlier chat messages tends to answer from the chat instead of from the new context."""
    lines = []
    for turn in (history or [])[-HISTORY_TURNS:]:
        answer = " ".join(turn["answer"].split())
        if len(answer) > HISTORY_ANSWER_CHARS:
            answer = answer[:HISTORY_ANSWER_CHARS].rsplit(" ", 1)[0] + " ..."
        lines.append(f"Q: {turn['question']}\nA: {answer}")
    return "\n".join(lines)


def build_messages(question: str, results: list[SearchResult], history: list[Turn] | None = None) -> list[Message]:
    """Build the system + user chat messages for Ollama's chat API."""
    if not question or not question.strip():
        raise ValueError("Question is empty. Please type a question.")

    # With no chunks, say so clearly, so the model replies with NOT_FOUND_MESSAGE
    context = format_context(results) or "No context found."

    # Earlier turns first (only to explain words like "it"), then the context, then the question.
    # The reminder comes last because small models follow the most recent instruction best.
    earlier = format_history(history)
    user_content = (
        (f"Earlier in this chat (only to understand what the question refers to):\n{earlier}\n\n" if earlier else "")
        + f"Context:\n{context}\n\nQuestion: {question.strip()}\n\n"
        f"Remember: answer only from the context above and put [Source N] after every fact. "
        f"If the answer is not in the context, reply exactly: {NOT_FOUND_MESSAGE}"
    )

    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]


def get_sources(results: list[SearchResult]) -> list[Source]:
    """Return the sources in rank order, numbered the same way as in the context.

    "text" is the full chunk text, so the dashboard can show what the model read.
    """
    return [
        {"source_number": number, "source": r["source"], "page": r["page"], "score": r["score"], "text": r["text"]}
        for number, r in enumerate(results, start=1)
    ]
