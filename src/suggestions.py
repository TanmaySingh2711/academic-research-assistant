"""Suggested questions: the local model reads the start of a paper and writes a few questions about it.

The questions are saved in index/suggestions.json, so each paper is read only once per index build.
"""

import json
import re
import threading
from pathlib import Path

from src.generator import generate_answer

NUMBER_OF_QUESTIONS = 4
START_CHUNKS = 5  # the first chunks of a paper: usually title, abstract and introduction
SUGGESTIONS_FILE = "suggestions.json"

_lock = threading.Lock()  # one paper at a time, and one write at a time

SYSTEM_PROMPT = "You write short questions about research papers. Reply with the questions only."

# A list marker at the start of a line: "-", "*", a bullet, "1.", "2)", "Q1:" ...
_LIST_MARKER = re.compile(r"^\s*(?:[-*" + chr(0x2022) + r"]|\d+[.)]|Q\d*[:.])\s*")


def build_messages(paper_start):
    """Chat messages that ask the model for questions about the start of a paper."""
    user = (
        f"Here is the start of a research paper:\n\n{paper_start}\n\n"
        f"Write {NUMBER_OF_QUESTIONS} different short questions (at most 12 words each) that a student "
        "could ask about this paper and that the text above helps to answer. "
        "Write one question per line, with no numbers and no other text."
    )
    return [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user}]


def parse_questions(text, limit=NUMBER_OF_QUESTIONS):
    """Turn the model's reply into a clean list of questions (list markers removed, no duplicates)."""
    questions = []
    for line in text.splitlines():
        question = _LIST_MARKER.sub("", line).strip().strip('"').strip()
        if not question.endswith("?") or not 12 <= len(question) <= 140:
            continue  # skip intro lines like "Here are some questions:" and odd lengths
        if question.lower() not in [q.lower() for q in questions]:
            questions.append(question)
    return questions[:limit]


def _load(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def get_suggestions(paper, chunks, info, index_dir):
    """Return the questions for one paper: saved ones if they exist, otherwise ask the model once.

    Raises ConnectionError / RuntimeError (from generate_answer) when Ollama is not available.
    """
    path = Path(index_dir) / SUGGESTIONS_FILE
    with _lock:
        saved = _load(path)
        # Questions from an older index may belong to other papers or other text, so start fresh
        if saved.get("built_at") != info.get("built_at"):
            saved = {"built_at": info.get("built_at"), "papers": {}}
        if paper in saved["papers"]:
            return saved["papers"][paper]

        start = [chunk["text"] for chunk in chunks if chunk["source"] == paper][:START_CHUNKS]
        if not start:
            return []
        reply = generate_answer(build_messages("\n\n".join(start)), temperature=0.3)
        questions = parse_questions(reply["answer"])

        if questions:  # an empty or odd reply is not saved, so the next visit tries again
            saved["papers"][paper] = questions
            path.write_text(json.dumps(saved, ensure_ascii=False, indent=2), encoding="utf-8")
        return questions
