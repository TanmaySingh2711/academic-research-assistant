"""Test the Flask routes with Flask's built-in test client (no browser or server needed)."""

import io
import json
import sys
from pathlib import Path

from app import app

client = app.test_client()
failures = []


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

if failures:
    sys.exit(f"{len(failures)} check(s) failed: {failures}")
