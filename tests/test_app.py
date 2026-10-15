"""app.py: every route of the Flask backend, in temporary folders with the fake LLM."""

import io
import json
import os
from pathlib import Path
from typing import Any

import pytest

import app as app_module
import src.rag_pipeline
from src.vector_store import INFO_FILE
from tests.conftest import OTHER, PAPER, FakeLLM

NEW = "new_paper.pdf"


def status(client: Any) -> dict:
    return client.get("/status").get_json()


def ask(client: Any, **body: Any) -> Any:
    return client.post("/ask", json=body)


def events(response: Any) -> list[dict]:
    return [json.loads(line) for line in response.get_data(as_text=True).splitlines() if line.strip()]


def upload_copy(client: Any, project: dict[str, Path], name: str) -> Any:
    """Upload one of the sample PDFs again under another name."""
    data = (project["papers"] / PAPER).read_bytes()
    return client.post("/upload", content_type="multipart/form-data", data={"files": [(io.BytesIO(data), name)]})


# ---------- Status, upload, Build index ----------

def test_status_after_build(app_client: Any) -> None:
    s = status(app_client)
    assert s["index_ready"] and s["chunks"] > 0 and not s["index_outdated"]
    assert s["indexed_papers"] == s["pdfs_in_data"] and len(s["pdfs_in_data"]) == 3
    assert s["papers_to_index"] == [] and s["unreadable_papers"] == []
    assert len(s["boot_id"]) == 32


def test_upload_checks_the_files(app_client: Any, project: dict[str, Path]) -> None:
    pdf = (project["papers"] / PAPER).read_bytes()
    body = app_client.post("/upload", content_type="multipart/form-data", data={"files": [
        (io.BytesIO(pdf), PAPER), (io.BytesIO(b"notes"), "notes.txt"), (io.BytesIO(b"not a pdf"), "fake.pdf"),
        (io.BytesIO(pdf), "../../evil name.pdf"),
    ]}).get_json()
    assert body["saved"] == [PAPER, "evil_name.pdf"]
    assert [s["name"] for s in body["skipped"]] == ["notes.txt", "fake.pdf"]
    assert "Overwrote existing" in body["message"]
    assert (project["papers"] / "evil_name.pdf").exists()
    assert app_client.post("/upload", data={}).status_code == 400


def test_upload_too_large(app_client: Any) -> None:
    app_module.app.config["MAX_CONTENT_LENGTH"] = 100
    try:
        response = upload_copy(app_client, {"papers": Path(app_module.app.config["PAPERS_DIR"])}, NEW)
        assert response.status_code == 413 and "25 MB" in response.get_json()["error"]
    finally:
        app_module.app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024


def test_build_index_only_indexes_the_new_paper(app_client: Any, project: dict[str, Path]) -> None:
    upload_copy(app_client, project, NEW)
    assert status(app_client)["papers_to_index"] == [NEW]
    body = app_client.post("/process").get_json()
    assert body["summary"]["indexed"] == [NEW]
    assert body["message"].startswith("Indexed 1 paper (2 pages,")
    assert NEW in status(app_client)["indexed_papers"]
    assert app_client.post("/process").get_json()["message"] == "Everything is already indexed."


def test_build_index_errors_without_pdfs(app_client: Any, project: dict[str, Path]) -> None:
    for pdf in project["papers"].glob("*.pdf"):
        pdf.unlink()
    assert "No PDF files" in app_client.post("/process").get_json()["error"]


def test_old_index_is_marked_outdated(app_client: Any, project: dict[str, Path]) -> None:
    info_path = project["index"] / INFO_FILE
    info = json.loads(info_path.read_text())
    info_path.write_text(json.dumps({**info, "pipeline_version": 1}))
    app_module.load_index_into_memory()
    s = status(app_client)
    assert s["index_outdated"] and s["papers_to_index"] == s["pdfs_in_data"]
    assert s["indexed_papers"] == s["pdfs_in_data"]  # still searchable until Build index


def test_unreadable_paper(app_client: Any, project: dict[str, Path]) -> None:
    from evaluation.pdf_writer import make_pdf

    make_pdf(project["papers"] / "empty.pdf", [""])
    app_client.post("/process")
    s = status(app_client)
    assert s["unreadable_papers"] == ["empty.pdf"] and "empty.pdf" not in s["papers_to_index"]


# ---------- Asking ----------

@pytest.mark.parametrize("body, code, message", [
    ({"question": "   ", "paper": PAPER}, 400, "empty"),
    ({"question": "Hi?", "paper": PAPER, "k": 7}, 400, "k must be"),
    ({"question": "Hi?", "paper": PAPER, "k": True}, 400, "k must be"),
    ({"question": "Hi?"}, 400, "Pick a paper"),
    ({"question": "Hi?", "paper": "missing.pdf"}, 400, "Pick a paper"),
    ({"question": "Hi?", "chat_id": "000000000000"}, 404, "not found"),
    ({"question": "Hi?", "chat_id": "../app"}, 404, "not found"),
])
def test_ask_validation(app_client: Any, body: dict, code: int, message: str) -> None:
    response = ask(app_client, **body)
    assert response.status_code == code and message in response.get_json()["error"]


def test_ask_needs_json_and_an_index(app_client: Any) -> None:
    assert app_client.post("/ask", data="text").status_code == 400
    app_module.store = None
    assert ask(app_client, question="Hi?", paper=PAPER).status_code == 409


def test_ask_and_follow_up(app_client: Any, fake_llm: FakeLLM) -> None:
    first = ask(app_client, question="What reward function does the agent use?", paper=PAPER).get_json()
    assert first["paper"] == PAPER and first["title"] == "What reward function does the agent use?"
    assert first["sources"] and all(s["source"] == PAPER for s in first["sources"])

    follow = ask(app_client, question="How was it evaluated?", chat_id=first["chat_id"], k=1).get_json()
    assert follow["chat_id"] == first["chat_id"] and follow["paper"] == PAPER and follow["k"] == 1
    prompt = fake_llm.calls[-1][-1]["content"]
    assert "Earlier in this chat" in prompt and "Q: What reward function does the agent use?" in prompt

    chat = app_client.get(f"/api/chats/{first['chat_id']}").get_json()
    assert [m["role"] for m in chat["messages"]] == ["user", "assistant"] * 2


def test_ask_streams_the_answer(app_client: Any) -> None:
    response = ask(app_client, question="What reward function does the agent use?", paper=PAPER, stream=True)
    assert response.mimetype == "application/x-ndjson"
    found = events(response)
    assert found[0]["type"] == "start" and found[0]["paper"] == PAPER and found[0]["sources"] == 3
    tokens = [e["text"] for e in found if e["type"] == "token"]
    done = found[-1]
    assert done["type"] == "done" and done["result"]["answer"] == "".join(tokens).strip()
    assert done["result"]["chat_id"] == found[0]["chat_id"]
    assert app_client.get(f"/api/chats/{found[0]['chat_id']}").status_code == 200


def test_not_found_answer_has_no_sources(app_client: Any) -> None:
    done = events(ask(app_client, question="What is the capital of France?", paper=OTHER, stream=True))[-1]
    assert done["result"]["not_found"] and done["result"]["sources"] == []


def test_stop_keeps_the_part_that_was_written(app_client: Any, fake_llm: FakeLLM) -> None:
    response = app_client.post("/ask", json={"question": "What reward does the agent get?", "paper": PAPER,
                                             "stream": True}, buffered=False)
    pieces = iter(response.response)
    start = json.loads(next(pieces))
    next(pieces), next(pieces)  # two words arrive, then the user presses Stop
    response.close()

    chat = app_client.get(f"/api/chats/{start['chat_id']}").get_json()
    answer = chat["messages"][1]
    assert answer["stopped"] is True
    assert 0 < len(answer["content"].split()) < len(fake_llm.reply(fake_llm.calls[-1]).split())


def test_ollama_not_running_gives_503(app_client: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    def broken(*args: Any, **kwargs: Any) -> Any:
        raise ConnectionError("Ollama is not running. Start the Ollama app and try again.")
        yield  # makes this a generator, like the real stream_answer

    monkeypatch.setattr(src.rag_pipeline, "stream_answer", broken)
    response = ask(app_client, question="Hi?", paper=PAPER, stream=True)
    assert response.status_code == 503 and "Ollama is not running" in response.get_json()["error"]
    assert app_client.get("/api/chats").get_json() == []  # nothing was saved


def test_error_in_the_middle_of_a_stream(app_client: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    def breaks_later(*args: Any, **kwargs: Any) -> Any:
        yield {"token": "Half "}
        raise ConnectionError("Ollama stopped.")

    monkeypatch.setattr(src.rag_pipeline, "stream_answer", breaks_later)
    found = events(ask(app_client, question="Hi?", paper=PAPER, stream=True))
    assert found[-1] == {"type": "error", "error": "Ollama stopped.", "status": 503}
    whole = ask(app_client, question="Hi?", paper=PAPER)  # without streaming: a normal JSON error
    assert whole.status_code == 503 and whole.get_json()["error"] == "Ollama stopped."


# ---------- Suggestions ----------

def test_suggestions(app_client: Any) -> None:
    body = app_client.get(f"/api/suggestions?paper={PAPER}").get_json()
    assert body["paper"] == PAPER and len(body["questions"]) == 3
    assert app_client.get("/api/suggestions?paper=missing.pdf").status_code == 400
    app_module.store = None
    assert app_client.get(f"/api/suggestions?paper={PAPER}").status_code == 409


# ---------- Chats ----------

def test_rename_and_delete_chat(app_client: Any) -> None:
    chat_id = ask(app_client, question="First question?", paper=PAPER).get_json()["chat_id"]
    assert app_client.patch(f"/api/chats/{chat_id}", json={"title": " New name "}).get_json()["title"] == "New name"
    assert app_client.patch(f"/api/chats/{chat_id}", json={"title": "  "}).status_code == 400
    assert app_client.patch(f"/api/chats/{chat_id}", json={}).status_code == 400
    assert app_client.patch("/api/chats/000000000000", json={"title": "x"}).status_code == 404
    assert [c["title"] for c in app_client.get("/api/chats").get_json()] == ["New name"]

    assert app_client.delete(f"/api/chats/{chat_id}").get_json() == {"deleted": chat_id}
    assert app_client.delete(f"/api/chats/{chat_id}").status_code == 404
    assert app_client.get(f"/api/chats/{chat_id}").status_code == 404


# ---------- Deleting a paper ----------

def test_delete_paper_does_only_that(app_client: Any, project: dict[str, Path], fake_llm: FakeLLM) -> None:
    ask(app_client, question="Question one?", paper=PAPER)
    ask(app_client, question="Question two?", paper=OTHER)
    upload_copy(app_client, project, NEW)  # a new paper that is not indexed yet
    before = status(app_client)

    body = app_client.delete(f"/api/papers/{PAPER}").get_json()
    assert body["chats_deleted"] == 1 and body["message"] == "Deleted the paper and 1 chat."
    after = status(app_client)
    assert not (project["papers"] / PAPER).exists()
    assert PAPER not in after["indexed_papers"] and len(after["indexed_papers"]) == 2
    assert after["papers_to_index"] == [NEW]  # the new paper was NOT indexed by the delete
    assert after["built_at"] == before["built_at"]  # nothing was built
    assert [c["paper"] for c in app_client.get("/api/chats").get_json()] == [OTHER]
    info = json.loads((project["index"] / INFO_FILE).read_text())
    assert PAPER not in info["papers"] and info["num_chunks"] == after["chunks"]

    # The other papers still answer
    assert ask(app_client, question="What is load testing?", paper=OTHER).status_code == 200

    # A paper that was never indexed can be deleted too
    assert app_client.delete(f"/api/papers/{NEW}").status_code == 200
    assert status(app_client)["papers_to_index"] == []


def test_deleting_the_last_paper_clears_the_index(app_client: Any, project: dict[str, Path]) -> None:
    for name in sorted(os.listdir(project["papers"])):
        app_client.delete(f"/api/papers/{name}")
    s = status(app_client)
    assert not s["index_ready"] and s["pdfs_in_data"] == [] and s["chunks"] == 0
    assert not (project["index"] / INFO_FILE).exists()


@pytest.mark.parametrize("name", ["missing.pdf", "..%2Fapp.py", "notes.txt"])
def test_delete_paper_refuses_bad_names(app_client: Any, name: str) -> None:
    assert app_client.delete(f"/api/papers/{name}").status_code == 404


# ---------- Errors ----------

def test_errors_are_json(app_client: Any) -> None:
    missing = app_client.get("/no-such-page")
    assert missing.status_code == 404 and "error" in missing.get_json()
    assert app_client.get("/ask").status_code == 405


# ---------- Only the dashboard itself may use the API ----------

@pytest.mark.parametrize("host", ["localhost:5000", "127.0.0.1:5000", "[::1]:5000"])
def test_local_host_names_are_answered(app_client: Any, host: str) -> None:
    assert app_client.get("/status", headers={"Host": host}).status_code == 200


def test_other_host_names_are_refused(app_client: Any) -> None:
    # A page on evil.example could point its own domain at 127.0.0.1 (DNS rebinding)
    response = app_client.get("/status", headers={"Host": "evil.example:5000"})
    assert response.status_code == 403 and "localhost" in response.get_json()["error"]


@pytest.mark.parametrize("headers", [{"Origin": "https://evil.example"}, {"Sec-Fetch-Site": "cross-site"}])
def test_changes_from_other_websites_are_refused(app_client: Any, headers: dict) -> None:
    assert app_client.post("/process", headers=headers).status_code == 403
    assert app_client.delete(f"/api/papers/{PAPER}", headers=headers).status_code == 403
    assert status(app_client)["papers_to_index"] == [] and PAPER in status(app_client)["pdfs_in_data"]


def test_the_dashboard_itself_may_change_things(app_client: Any) -> None:
    headers = {"Origin": "http://localhost", "Sec-Fetch-Site": "same-origin"}
    assert app_client.post("/process", headers=headers).status_code == 200


def test_chat_deleted_while_its_answer_is_written(app_client: Any) -> None:
    chat_id = ask(app_client, question="First question?", paper=PAPER).get_json()["chat_id"]
    response = app_client.post("/ask", json={"question": "More?", "chat_id": chat_id, "stream": True},
                               buffered=False)
    pieces = iter(response.response)
    next(pieces)  # the answer has started
    app_client.delete(f"/api/chats/{chat_id}")
    last = json.loads(list(pieces)[-1])
    response.close()
    assert last["type"] == "error" and last["status"] == 404 and "deleted" in last["error"]
    assert app_client.get("/api/chats").get_json() == []  # the chat did not come back


@pytest.mark.ollama
def test_real_answer_from_ollama(app_client: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    import src.generator

    monkeypatch.setattr(src.rag_pipeline, "stream_answer", src.generator.stream_answer)
    done = events(ask(app_client, question="What reward function does the cautious curiosity agent use?",
                      paper=PAPER, stream=True))[-1]
    assert done["type"] == "done"
    answer = done["result"]["answer"].lower()
    assert "intrinsic" in answer or "curiosity" in answer
    assert done["result"]["sources"]
