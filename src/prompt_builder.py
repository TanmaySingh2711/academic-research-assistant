"""Prompt construction: combine the question and retrieved chunks into chat messages for the LLM."""

# Exact reply when the answer is not in the context (Objective 8 checks for this sentence)
NOT_FOUND_MESSAGE = "I could not find this in the uploaded papers."

# Short, direct rules work best for a small (3B) model
SYSTEM_PROMPT = f"""You are a research assistant that answers questions about research papers.

Follow these rules:
1. Answer ONLY using the context given in the user message.
2. Do not use outside knowledge. Do not make up facts, numbers or citations.
3. Cite the sources you used with their numbers, like [Source 1] or [Source 2].
4. If the context does not contain the answer, reply exactly: {NOT_FOUND_MESSAGE}
5. Keep the answer clear and short: a few sentences or a short list."""


def format_context(results):
    """Turn retrieved results into one context string, one numbered block per chunk."""
    blocks = []
    for number, r in enumerate(results, start=1):  # results are already in rank order
        blocks.append(f"[Source {number}] {r['source']}, page {r['page']}\n{r['text']}")
    return "\n\n".join(blocks)  # empty list -> empty string


def build_messages(question, results):
    """Build the system + user chat messages for Ollama's chat API."""
    if not question or not question.strip():
        raise ValueError("Question is empty. Please type a question.")

    # With no chunks, say so clearly, so the model replies with NOT_FOUND_MESSAGE
    context = format_context(results) or "No context found."

    # Context first, then the question, with clear labels.
    # The reminder comes last because small models follow the most recent instruction best.
    user_content = (
        f"Context:\n{context}\n\nQuestion: {question.strip()}\n\n"
        f"Remember: answer only from the context above and cite [Source N]. "
        f"If the answer is not in the context, reply exactly: {NOT_FOUND_MESSAGE}"
    )

    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]


def get_sources(results):
    """Return the sources in rank order, numbered the same way as in the context.

    "text" is the full chunk text, so the dashboard can show what the model read.
    """
    return [
        {"source_number": number, "source": r["source"], "page": r["page"], "score": r["score"], "text": r["text"]}
        for number, r in enumerate(results, start=1)
    ]
