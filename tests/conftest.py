"""Shared test setup (pytest loads this file by itself).

Everything runs in temporary folders, so your real data/, index/ and chats/ are never touched.
Most tests use a fake LLM, so they are fast, give the same result every time and need no
Ollama. Tests marked "ollama" use the real model and are skipped when Ollama is not running.
"""

import shutil
import socket
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from src.ingest import run_ingestion
from tests.make_sample_pdfs import DOCUMENTS, make_pdf

PAPER = "sample_curiosity_agent.pdf"
OTHER = "sample_load_testing.pdf"


def ollama_running() -> bool:
    try:
        socket.create_connection(("127.0.0.1", 11434), timeout=0.3).close()
        return True
    except OSError:
        return False


def pytest_collection_modifyitems(config: Any, items: list[Any]) -> None:
    """Skip the tests that need Ollama when it is not running."""
    if ollama_running():
        return
    skip = pytest.mark.skip(reason="Ollama is not running")
    for item in items:
        if "ollama" in item.keywords:
            item.add_marker(skip)


@pytest.fixture(scope="session")
def sample_index(tmp_path_factory: Any) -> tuple[Path, Path]:
    """The 3 sample papers and an index built from them, made once for the whole test run."""
    root = tmp_path_factory.mktemp("sample")
    data, index = root / "data", root / "index"
    data.mkdir()
    for name, pages in DOCUMENTS.items():
        make_pdf(data / name, pages)
    run_ingestion(data, index)
    return data, index


@pytest.fixture
def project(sample_index: tuple[Path, Path], tmp_path: Path) -> dict[str, Path]:
    """A fresh copy of the sample papers and index for one test, plus an empty chats folder."""
    data, index = sample_index
    folders = {"data": tmp_path / "data", "index": tmp_path / "index", "chats": tmp_path / "chats"}
    shutil.copytree(data, folders["data"], copy_function=shutil.copy2)  # copy2 keeps the file times
    shutil.copytree(index, folders["index"])
    folders["chats"].mkdir()
    return folders


class FakeLLM:
    """Stands in for Ollama: answers with the first sentence of the first source, citing it.

    "capital of france" gets the not-found sentence. delay slows the words down (to test Stop).
    """

    def __init__(self) -> None:
        self.calls: list[list[dict[str, str]]] = []
        self.delay = 0.0

    def reply(self, messages: list[dict[str, str]]) -> str:
        question = messages[-1]["content"]
        if "capital of france" in question.lower():
            return "I could not find this in the uploaded papers."
        if "Context:" not in question:  # suggested questions
            return "1. What does the agent learn?\n2. How was it evaluated?\nNot a question\n- Why is it useful?"
        first_source = question.split("[Source 1]", 1)[1].split("\n", 2)[1]
        return f"{first_source.split('. ')[0]}. [Source 1]"

    def stream(self, messages: list[dict[str, str]], model: str = "", temperature: float = 0.0) -> Iterator[dict]:
        self.calls.append(messages)
        for word in self.reply(messages).split(" "):
            if self.delay:
                time.sleep(self.delay)
            yield {"token": word + " "}
        yield {"done": True, "model": "fake", "prompt_tokens": 100, "answer_tokens": 10, "seconds": 0.1}


@pytest.fixture
def fake_llm(monkeypatch: pytest.MonkeyPatch) -> FakeLLM:
    """Replace the real LLM everywhere it is used."""
    import src.generator
    import src.rag_pipeline

    llm = FakeLLM()
    # generate_answer calls src.generator.stream_answer, so one patch covers it (and suggestions);
    # rag_pipeline imported stream_answer by name, so it is patched there too
    monkeypatch.setattr(src.generator, "stream_answer", llm.stream)
    monkeypatch.setattr(src.rag_pipeline, "stream_answer", llm.stream)
    return llm


@pytest.fixture
def app_client(project: dict[str, Path], fake_llm: FakeLLM) -> Iterator[Any]:
    """The Flask app pointed at the temporary folders, with the fake LLM."""
    import app as app_module

    app = app_module.app
    old = {key: app.config[key] for key in ("DATA_DIR", "INDEX_DIR", "CHATS_DIR", "WARM_UP_MODEL")}
    app.config.update(DATA_DIR=project["data"], INDEX_DIR=project["index"], CHATS_DIR=project["chats"],
                      WARM_UP_MODEL=False)
    app_module.load_index_into_memory()
    yield app.test_client()
    app.config.update(old)
    app_module.load_index_into_memory()
