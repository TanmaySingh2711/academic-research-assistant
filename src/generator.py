"""Generation: send the chat messages to the local LLM (Ollama) and return the answer.

The answer can come back in one piece (generate_answer) or word by word while the model
writes it (stream_answer), so the dashboard can show it at once, like ChatGPT.
"""

import time
from collections.abc import Iterator
from typing import Any

from src.schema import Message

LLM_MODEL = "llama3.2:3b"

# Low temperature = the model picks the most likely words, with little randomness.
# For RAG we want factual answers that stick to the context, not creative ones.
# A fixed seed makes the same question with the same context give (almost always) the same
# answer, so the evaluation (evaluation/evaluate.py) can be repeated and compared.
TEMPERATURE = 0.1
SEED = 42

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


def _options(temperature: float) -> dict[str, Any]:
    return {"temperature": temperature, "seed": SEED}


def stream_answer(messages: list[Message], model: str = LLM_MODEL,
                  temperature: float = TEMPERATURE) -> Iterator[dict[str, Any]]:
    """Yield {"token": "..."} for every piece of the answer, then one {"done": True, ...numbers}.

    Raises ConnectionError when Ollama is not running and RuntimeError when the model is missing
    (when the first piece is requested, because the request starts then).
    """
    import ollama  # imported here so the app starts faster (it is only needed for answers)

    start = time.perf_counter()
    final: Any = None
    try:
        for part in ollama.chat(model=model, messages=messages, options=_options(temperature), stream=True):
            if part.message.content:
                yield {"token": part.message.content}
            if part.done:
                final = part
    except ConnectionError:
        raise ConnectionError("Ollama is not running. Start the Ollama app and try again.") from None
    except ollama.ResponseError as e:
        if e.status_code == 404:
            raise RuntimeError(f"Model '{model}' is not downloaded. Run: ollama pull {model}") from None
        raise

    yield {
        "done": True,
        "model": (final.model if final else None) or model,
        "prompt_tokens": final.prompt_eval_count if final else None,  # tokens the model read
        "answer_tokens": final.eval_count if final else None,  # tokens the model wrote
        "seconds": round(time.perf_counter() - start, 2),
    }


def generate_answer(messages: list[Message], model: str = LLM_MODEL,
                    temperature: float = TEMPERATURE) -> dict[str, Any]:
    """Send messages to Ollama and return the whole answer with token counts and time taken."""
    pieces = []
    result: dict[str, Any] = {}
    for event in stream_answer(messages, model=model, temperature=temperature):
        if "token" in event:
            pieces.append(event["token"])
        else:
            result = event
    return {
        "answer": "".join(pieces).strip(),
        "model": result.get("model", model),
        "prompt_tokens": result.get("prompt_tokens"),
        "answer_tokens": result.get("answer_tokens"),
        "seconds": result.get("seconds", 0.0),
    }


def is_not_found(answer: str) -> bool:
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
