"""Test the Flask routes with Flask's built-in test client (no browser or server needed).

Everything happens in temporary folders with 3 sample PDFs, so your real data/, index/
and chats/ folders are never changed (this test also deletes a paper).
"""

import io
import json
import sys
import tempfile
from pathlib import Path

import app as app_module
from tests.make_sample_pdfs import DOCUMENTS, make_pdf

app = app_module.app

# ---------- Temporary folders with sample papers ----------

temp = tempfile.TemporaryDirectory()
root = Path(temp.name)
for folder in ("data", "index", "chats"):
    (root / folder).mkdir()
for name, pages in DOCUMENTS.items():
    make_pdf(root / "data" / name, pages)
app.config.update(DATA_DIR=root / "data", INDEX_DIR=root / "index", CHATS_DIR=root / "chats")
app_module.load_index_into_memory()  # nothing there yet, so the app starts without an index

PAPER = "sample_curiosity_agent.pdf"
OTHER = "sample_load_testing.pdf"

client = app.test_client()
failures: list[str] = []


def show(label, response, expected_status, short_answer=False):
    """Print the status code and JSON body of a response, and check the status code."""
    body = response.get_json()
    if short_answer and body and "answer" in body:
        body = dict(body, answer=body["answer"][:200] + ("..." if len(body["answer"]) > 200 else ""))
    ok = response.status_code == expected_status
    print(f"\n### {label}")
    print(f"status {response.status_code} (expected {expected_status}) {'OK' if ok else 'FAIL'}")
    print(json.dumps(body, indent=2, ensure_ascii=False))
    if not ok:
        failures.append(label)
    return body or {}


def check(ok, label):
    print(f"  {label:<60} {'OK' if ok else 'FAIL'}")
    if not ok:
        failures.append(label)


def ask(label, payload, expected=200):
    return show(label, client.post("/ask", json=payload), expected, short_answer=True)


# ---------- Upload and build ----------

status = show("GET /status (no index yet)", client.get("/status"), 200)
check(status.get("papers_to_index") == sorted(DOCUMENTS), "before Build index, every paper is waiting to be indexed")

response = client.post("/upload", content_type="multipart/form-data", data={
    "files": [
        (io.BytesIO((root / "data" / PAPER).read_bytes()), PAPER),
        (io.BytesIO(b"just some notes"), "notes.txt"),
    ],
})
body = show("POST /upload (existing PDF + notes.txt)", response, 200)
check(body.get("saved") == [PAPER] and [s["name"] for s in body.get("skipped", [])] == ["notes.txt"],
      "upload saves the PDF and skips notes.txt")

response = client.post("/upload", content_type="multipart/form-data", data={
    "files": [(io.BytesIO(b"this is not really a pdf"), "fake.pdf")],
})
body = show("POST /upload (fake.pdf with text content)", response, 200)
check(not body.get("saved") and [s["name"] for s in body.get("skipped", [])] == ["fake.pdf"],
      "a .pdf name with text content is skipped")

show("POST /process", client.post("/process"), 200)
status = show("GET /status (after process)", client.get("/status"), 200)
check(status.get("indexed_papers") == sorted(DOCUMENTS), "all 3 sample papers are indexed")
check(status.get("papers_to_index") == [], "after Build index, nothing is waiting (Build index is greyed out)")

# ---------- Asking (every chat is about one paper) ----------

ask("POST /ask (empty question)", {"question": "   ", "paper": PAPER}, 400)
ask("POST /ask (k=7)", {"question": "What is curiosity?", "paper": PAPER, "k": 7}, 400)
ask("POST /ask (no paper)", {"question": "What is curiosity?"}, 400)
ask("POST /ask (paper not indexed)", {"question": "Hi?", "paper": "missing.pdf"}, 400)
ask("POST /ask (unknown chat)", {"question": "Hi?", "chat_id": "000000000000"}, 404)

first = ask("POST /ask (new chat 1 about the paper)",
            {"question": "What reward function does the cautious curiosity agent use?", "paper": PAPER, "k": 3})
chat_1 = first.get("chat_id")
check(first.get("paper") == PAPER and all(s["source"] == PAPER for s in first.get("sources", [])),
      "sources all come from the chosen paper")

follow = ask("POST /ask (follow-up in chat 1)", {"question": "How was the agent evaluated?", "chat_id": chat_1, "k": 1})
check(follow.get("chat_id") == chat_1 and follow.get("paper") == PAPER, "follow-up stays in the same chat and paper")

second = ask("POST /ask (new chat 2 about the same paper)", {"question": "What is the main idea?", "paper": PAPER})
chat_2 = second.get("chat_id")
check(chat_2 not in (None, chat_1), "a paper can have more than one chat")

# The model's wording can vary, so only the status code is checked for the off-topic question
ask("POST /ask (off-topic, other paper)", {"question": "What is the capital of France?", "paper": OTHER})

body = show("GET /api/suggestions (one paper)", client.get(f"/api/suggestions?paper={PAPER}"), 200)
check(isinstance(body.get("questions"), list), "suggestions are a list of questions")
show("GET /api/suggestions (paper not indexed)", client.get("/api/suggestions?paper=missing.pdf"), 400)

# ---------- Chats: list, rename, delete ----------

chats = client.get("/api/chats").get_json()
print(f"\n### GET /api/chats: {len(chats)} chats")
for chat in chats:
    print(f"  {chat['id']} | {chat['questions']} question(s) | {chat['paper']} | {chat['title']}")
check(len(chats) == 3 and sum(chat["paper"] == PAPER for chat in chats) == 2, "3 chats, 2 of them about the paper")

response = client.patch(f"/api/chats/{chat_1}", json={"title": "  My renamed chat "})
body = show("PATCH /api/chats/<chat 1> (rename)", response, 200)
check(body.get("title") == "My renamed chat", "the new name is saved (spaces trimmed)")
show("PATCH /api/chats/<chat 1> (empty name)", client.patch(f"/api/chats/{chat_1}", json={"title": "   "}), 400)
show("PATCH /api/chats/<unknown>", client.patch("/api/chats/000000000000", json={"title": "x"}), 404)

show("DELETE /api/chats/<chat 2>", client.delete(f"/api/chats/{chat_2}"), 200)
show("GET /api/chats/<chat 2> (after delete)", client.get(f"/api/chats/{chat_2}"), 404)
show("GET /api/chats/<bad id>", client.get("/api/chats/..%2Fapp"), 404)

messages = client.get(f"/api/chats/{chat_1}").get_json().get("messages", [])
check(len(messages) == 4, "chat 1 still has 2 questions and 2 answers")

# ---------- Delete a paper: its PDF and chats go, the index is rebuilt ----------

body = show(f"DELETE /api/papers/{PAPER}", client.delete(f"/api/papers/{PAPER}"), 200)
check(body.get("chats_deleted") == 1, "the paper's remaining chat was deleted with it")
check(not (root / "data" / PAPER).exists(), "the PDF file is gone")
status = client.get("/status").get_json()
check(PAPER not in status["indexed_papers"] and len(status["indexed_papers"]) == 2, "the index was rebuilt without it")
check(all(chat["paper"] != PAPER for chat in client.get("/api/chats").get_json()), "no chats about the paper are left")
show("DELETE /api/papers/<not there>", client.delete("/api/papers/missing.pdf"), 404)
show("DELETE /api/papers/<unsafe name>", client.delete("/api/papers/..%2Fapp.py"), 404)

temp.cleanup()

if failures:
    sys.exit(f"{len(failures)} check(s) failed: {failures}")
