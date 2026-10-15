"""src/generator.py: talking to Ollama (a fake Ollama module here; the real one in the "ollama" tests)."""

import sys
import types
from collections.abc import Iterator
from typing import Any

import pytest

from src.generator import LLM_MODEL, SEED, generate_answer, is_not_found, stream_answer
from src.schema import Message

MESSAGES: list[Message] = [{"role": "system", "content": "rules"}, {"role": "user", "content": "question"}]


class Part:
    def __init__(self, content: str, done: bool = False) -> None:
        self.message = types.SimpleNamespace(content=content)
        self.done = done
        self.model = "llama3.2:3b"
        self.prompt_eval_count = 120 if done else None
        self.eval_count = 7 if done else None


class ResponseError(Exception):
    def __init__(self, status_code: int) -> None:
        super().__init__("error")
        self.status_code = status_code


@pytest.fixture
def fake_ollama(monkeypatch: pytest.MonkeyPatch) -> types.SimpleNamespace:
    """A stand-in for the ollama library. Set .error to make chat() fail."""
    module = types.SimpleNamespace(ResponseError=ResponseError, error=None, calls=[])

    def chat(**kwargs: Any) -> Iterator[Part]:
        module.calls.append(kwargs)
        if module.error:
            raise module.error
        yield Part("The answer ")
        yield Part("is 42 [Source 1].")
        yield Part("", done=True)

    module.chat = chat
    monkeypatch.setitem(sys.modules, "ollama", module)
    return module


def test_stream_answer_yields_pieces_then_numbers(fake_ollama: types.SimpleNamespace) -> None:
    events = list(stream_answer(MESSAGES))
    assert events[:2] == [{"token": "The answer "}, {"token": "is 42 [Source 1]."}]
    assert events[2]["done"] and events[2]["prompt_tokens"] == 120 and events[2]["answer_tokens"] == 7
    call = fake_ollama.calls[0]
    assert call["model"] == LLM_MODEL and call["stream"] is True
    assert call["options"] == {"temperature": 0.1, "seed": SEED}


def test_generate_answer_joins_the_pieces(fake_ollama: types.SimpleNamespace) -> None:
    result = generate_answer(MESSAGES)
    assert result["answer"] == "The answer is 42 [Source 1]."
    assert result["model"] == "llama3.2:3b" and result["answer_tokens"] == 7


def test_ollama_not_running(fake_ollama: types.SimpleNamespace) -> None:
    fake_ollama.error = ConnectionError("refused")
    with pytest.raises(ConnectionError, match="Ollama is not running"):
        generate_answer(MESSAGES)


def test_model_not_downloaded(fake_ollama: types.SimpleNamespace) -> None:
    fake_ollama.error = ResponseError(404)
    with pytest.raises(RuntimeError, match="ollama pull"):
        generate_answer(MESSAGES)
    fake_ollama.error = ResponseError(500)
    with pytest.raises(ResponseError):
        generate_answer(MESSAGES)


@pytest.mark.parametrize("answer, expected", [
    ("I could not find this in the uploaded papers.", True),
    ("Could not find this in the uploaded papers", True),
    ("i couldn't find that", True),
    ("The agent uses curiosity [Source 1]. I could not find more details.", False),
    ("The reward is 1.", False),
])
def test_is_not_found_checks_only_the_start(answer: str, expected: bool) -> None:
    assert is_not_found(answer) is expected


@pytest.mark.ollama
def test_real_model_answers() -> None:
    result = generate_answer([{"role": "user", "content": "Reply with exactly the word: ready"}])
    assert "ready" in result["answer"].lower()
    assert result["prompt_tokens"] and result["answer_tokens"]
