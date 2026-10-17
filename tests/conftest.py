"""Shared test setup (pytest loads this file by itself).

Everything runs in temporary folders, so your real storage/ folder is never touched.
Most tests use a fake LLM, so they are fast, give the same result every time and need no
Ollama. Tests marked "ollama" use the real model and are skipped when Ollama is not running.

CI sets REQUIRE_ALL_TESTS=1: then a skipped test (no Ollama, no browser, no OCR) fails the run,
so a missing tool can never make CI look green while tests did not really run.
"""

import os
import shutil
import socket
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from evaluation.pdf_writer import make_pdf
from src.ingest import run_ingestion

PAPER = "sample_curiosity_agent.pdf"
OTHER = "sample_load_testing.pdf"

# 3 small sample papers (2 pages each) used by most tests. They are synthetic, so the repo
# needs no real papers (those belong to their authors).
SAMPLE_NOTE = "Synthetic sample text generated for automated tests. It is not a real research paper."

DOCUMENTS = {
    "sample_curiosity_agent.pdf": [
        "Sample paper A: A cautious curiosity agent for human-like game playing. " + SAMPLE_NOTE + " "
        "Abstract. We describe a game-playing agent that is driven by curiosity. The agent receives an "
        "intrinsic reward when it reaches game states that it cannot yet predict well, and an extrinsic reward "
        "from the game score. The total reward function is the sum of the intrinsic curiosity reward and the "
        "extrinsic reward. To make the agent behave more like a human player, the curiosity reward follows an "
        "inverted U-shaped curve: the agent is most curious about states with a medium information gap, and less "
        "curious about states that are either fully known or completely unknown. In this way the agent explores "
        "the level without taking extreme risks, which human players also tend to avoid. We call this cautious "
        "curiosity.",
        "Evaluation. We compared the cautious curiosity agent with a random agent, a standard curiosity agent and "
        "an average human player in a simple platform game. Human judges watched short videos of each player and "
        "rated how human-like the behaviour looked. The cautious curiosity agent was rated more human-like than the "
        "other agents, while it still finished the level. It made some mistakes, hesitated before jumps and explored "
        "side areas, which the judges described as natural. The random agent did not finish the level within the "
        "time limit. These results suggest that a reward function based on a medium information gap can make an "
        "agent play more like an average human, not like an expert who rushes to the goal. Future work could test "
        "more games and larger groups of judges.",
    ],
    "sample_load_testing.pdf": [
        "Sample paper B: Reinforcement learning for load testing of video games. " + SAMPLE_NOTE + " "
        "Abstract. Load testing checks whether a game keeps a stable frame rate when many objects, effects or "
        "players are on the screen. Manual load testing is slow, because human testers must play for hours to find "
        "the places where the game becomes slow. We train a reinforcement learning agent that plays the game and "
        "receives a reward when the number of frames per second drops. The reward function combines two parts: a "
        "game reward that keeps the agent playing well, and a performance reward that is high when rendering a "
        "frame takes longer than usual. By maximising this reward, the agent learns to visit the areas of the "
        "level where performance problems appear.",
        "Study. We injected artificial performance bugs into a racing game at known positions on the track. The "
        "agent found most of these positions after training, and it found them more often than a random agent and "
        "an agent that was trained only to win the race. Each low frame rate point found by the agent was stored "
        "with its position, so developers can reproduce the problem. The approach still needs a reward function "
        "that is adapted to each game, and training takes several hours on a normal computer. Even so, the results "
        "show that reinforcement learning can support load testing of video games and reduce the manual work of "
        "human testers.",
    ],
    "sample_bug_detection.pdf": [
        "Sample paper C: A platform for automated bug detection in 3D video games. " + SAMPLE_NOTE + " "
        "Abstract. Bugs in 3D games break the experience of the player, but testing every interaction by hand is "
        "not practical. We present a platform that places an agent inside 3D environments that contain known bugs. "
        "The platform can inject several kinds of bugs: missing textures, objects that flicker or disappear, the "
        "camera clipping through walls, the player falling through the floor, and objects that stay frozen in the "
        "air. For each bug the platform produces a label mask that marks which pixels of the agent's view show the "
        "bug. These masks make it possible to train and evaluate models that detect bugs from images.",
        "Environments. The platform contains simple rooms and a larger maze, where the agent can move and look "
        "around freely. Researchers can add new bug types by writing a small script that changes the environment, "
        "and by choosing a colour for the bug in the label mask. The platform records the observations of the agent "
        "together with the masks, which gives a data set for learning. We hope the platform helps researchers "
        "compare methods for automated bug detection, for example models that learn what normal game frames look "
        "like and report frames that look unusual. The platform is meant for research and experiments, not for "
        "testing a finished commercial game.",
    ],
}


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


def pytest_sessionfinish(session: Any, exitstatus: int) -> None:
    """With REQUIRE_ALL_TESTS=1 (set in CI), any skipped test makes the whole run fail."""
    if os.environ.get("REQUIRE_ALL_TESTS") != "1":
        return
    reporter = session.config.pluginmanager.get_plugin("terminalreporter")
    skipped = reporter.stats.get("skipped", []) if reporter else []
    if skipped:
        reporter.write_line(f"REQUIRE_ALL_TESTS=1, but {len(skipped)} test(s) were skipped:", red=True)
        for report in skipped:
            reporter.write_line(f"  {report.nodeid}: {report.longrepr[-1] if report.longrepr else ''}", red=True)
        session.exitstatus = pytest.ExitCode.TESTS_FAILED


@pytest.fixture(scope="session")
def sample_index(tmp_path_factory: Any) -> tuple[Path, Path]:
    """The 3 sample papers and an index built from them, made once for the whole test run."""
    root = tmp_path_factory.mktemp("sample")
    papers, index = root / "papers", root / "index"
    papers.mkdir()
    for name, pages in DOCUMENTS.items():
        make_pdf(papers / name, pages)
    run_ingestion(papers, index)
    return papers, index


@pytest.fixture
def project(sample_index: tuple[Path, Path], tmp_path: Path) -> dict[str, Path]:
    """A fresh copy of the sample papers and index for one test, plus an empty chats folder."""
    papers, index = sample_index
    folders = {"papers": tmp_path / "papers", "index": tmp_path / "index", "chats": tmp_path / "chats"}
    shutil.copytree(papers, folders["papers"], copy_function=shutil.copy2)  # copy2 keeps the file times
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
    old = {key: app.config[key] for key in ("PAPERS_DIR", "INDEX_DIR", "CHATS_DIR", "WARM_UP_MODEL")}
    app.config.update(PAPERS_DIR=project["papers"], INDEX_DIR=project["index"], CHATS_DIR=project["chats"],
                      WARM_UP_MODEL=False)
    app_module.load_index_into_memory()
    yield app.test_client()
    app.config.update(old)
    app_module.load_index_into_memory()
