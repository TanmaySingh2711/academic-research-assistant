"""Test the Flask routes with Flask's built-in test client (no browser or server needed)."""

import io
import json
import sys
import tempfile
from pathlib import Path

from app import app

# Save the test chats in a temporary folder, not in the real chats/ folder
chats_tmp = tempfile.TemporaryDirectory()
app.config["CHATS_DIR"] = chats_tmp.name

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
    return body


show("GET /status", client.get("/status"), 200)

# Upload one existing PDF (overwritten with the same file) and a fake .txt file
existing_pdf = sorted(Path("data").glob("*.pdf"))[0]
response = client.post("/upload", content_type="multipart/form-data", data={
    "files": [
        (io.BytesIO(existing_pdf.read_bytes()), existing_pdf.name),
        (io.BytesIO(b"just some notes"), "notes.txt"),
    ],
})
body = show("POST /upload (existing PDF + notes.txt)", response, 200)
if body["saved"] != [existing_pdf.name] or [s["name"] for s in body["skipped"]] != ["notes.txt"]:
    failures.append("upload: wrong saved/skipped lists")

# A .pdf name, but the content is plain text
response = client.post("/upload", content_type="multipart/form-data", data={
    "files": [(io.BytesIO(b"this is not really a pdf"), "fake.pdf")],
})
body = show("POST /upload (fake.pdf with text content)", response, 200)
if body["saved"] or [s["name"] for s in body["skipped"]] != ["fake.pdf"]:
    failures.append("upload: fake.pdf was not skipped")

show("POST /process", client.post("/process"), 200)
show("GET /status (after process)", client.get("/status"), 200)

show("POST /ask (empty question)", client.post("/ask", json={"question": "   ", "k": 3}), 400)
show("POST /ask (k=7)", client.post("/ask", json={"question": "What is curiosity?", "k": 7}), 400)
show("POST /ask (real question, k=3)", client.post("/ask", json={
    "question": "What reward function does the cautious curiosity agent use?", "k": 3,
}), 200, short_answer=True)
# The model's wording can vary, so only the status code is checked here (not_found is printed)
show("POST /ask (off-topic)", client.post("/ask", json={"question": "What is the capital of France?"}), 200)

# ---------- Chat history and asking about one paper ----------

status = client.get("/status").get_json()
paper = status["indexed_papers"][0]
body = show("POST /ask (one paper, new chat)", client.post("/ask", json={
    "question": "What is the main idea of this paper?", "k": 3, "paper": paper,
}), 200, short_answer=True)
chat_id = body["chat_id"]
if body["paper"] != paper or any(s["source"] != paper for s in body["sources"]):
    failures.append("one paper: sources must all come from the chosen paper")

body = show("POST /ask (follow-up in the same chat)", client.post("/ask", json={
    "question": "What are the results?", "k": 1, "chat_id": chat_id,
}), 200, short_answer=True)
if body["chat_id"] != chat_id or body["paper"] != paper:
    failures.append("follow-up: must stay in the same chat and paper")

body = show("GET /api/suggestions (one paper)", client.get(f"/api/suggestions?paper={paper}"), 200)
if not isinstance(body.get("questions"), list):
    failures.append("/api/suggestions: expected a list of questions")
show("GET /api/suggestions (paper not indexed)", client.get("/api/suggestions?paper=missing.pdf"), 400)

show("POST /ask (paper not indexed)", client.post("/ask", json={"question": "Hi?", "paper": "missing.pdf"}), 400)
show("POST /ask (unknown chat)", client.post("/ask", json={"question": "Hi?", "chat_id": "000000000000"}), 404)

response = client.get("/api/chats")
chats = response.get_json()
print(f"\n### GET /api/chats\nstatus {response.status_code}, {len(chats)} chats")
for chat in chats:
    print(f"  {chat['id']} | {chat['questions']} question(s) | paper={chat['paper']} | {chat['title']}")
if response.status_code != 200 or len(chats) != 3:
    failures.append("/api/chats: expected 3 chats (2 all-papers chats + 1 paper chat)")

response = client.get(f"/api/chats/{chat_id}")
messages = response.get_json().get("messages", [])
print(f"\n### GET /api/chats/{chat_id}\nstatus {response.status_code}, {len(messages)} messages")
if response.status_code != 200 or len(messages) != 4:
    failures.append("/api/chats/<id>: expected 4 messages (2 questions, 2 answers)")

show("GET /api/chats/<bad id>", client.get("/api/chats/..%2Fapp"), 404)
chats_tmp.cleanup()

if failures:
    sys.exit(f"{len(failures)} check(s) failed: {failures}")
