"""Generation: send the chat messages to the local LLM (Ollama) and return the answer."""

import time

# Phrases that mean "the answer is not in the papers" (lenient check, the model may reword it)
NOT_FOUND_PHRASES = [
    "could not find",
    "couldn't find",
    "not find this",
    "not in the uploaded papers",
    "not mentioned in the context",
    "does not contain the answer",
    "no information",
]


def generate_answer(messages, model="llama3.2:3b", temperature=0.1):
    """Send messages to Ollama and return the answer with token counts and time taken."""
    import ollama  # imported here so the app starts faster (it is only needed for answers)

    start = time.perf_counter()
    try:
        # Low temperature = the model picks the most likely words, with little randomness.
        # For RAG we want factual, repeatable answers that stick to the context, not creative ones.
        response = ollama.chat(model=model, messages=messages, options={"temperature": temperature})
    except ConnectionError:
        raise ConnectionError("Ollama is not running. Start the Ollama app and try again.") from None
    except ollama.ResponseError as e:
        if e.status_code == 404:
            raise RuntimeError(f"Model '{model}' is not downloaded. Run: ollama pull {model}") from None
        raise

    return {
        "answer": response.message.content.strip(),
        "model": response.model or model,
        "prompt_tokens": response.prompt_eval_count,  # tokens the model read (None if missing)
        "answer_tokens": response.eval_count,  # tokens the model wrote (None if missing)
        "seconds": round(time.perf_counter() - start, 2),
    }


def is_not_found(answer):
    """Return True if the answer STARTS with a not-found phrase.

    Only the start is checked, so a real answer that ends with the not-found
    sentence (a partial answer) still counts as an answer and keeps its sources.
    """
    answer = answer.strip().lower()
    for phrase in NOT_FOUND_PHRASES:
        # Also allow a leading "I ", as in "I could not find this in the uploaded papers."
        if answer.startswith(phrase) or answer.startswith("i " + phrase):
            return True
    return False
