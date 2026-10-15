"""src/ingest.py: Build index only reads and embeds new or changed papers."""

import json
import os
import shutil
from pathlib import Path

import pytest

import src.ingest
from evaluation.pdf_writer import make_pdf
from src.ingest import file_signature, is_compatible, papers_needing_index, run_ingestion
from src.vector_store import INFO_FILE, load_store
from tests.conftest import DOCUMENTS, OTHER, PAPER


@pytest.fixture
def embedded(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    """Counts how many chunks are embedded in each call (to see what Build index really does)."""
    counts: list[int] = []
    real = src.ingest.embed_chunks

    def counting(chunks: list) -> object:
        counts.append(len(chunks))
        return real(chunks)

    monkeypatch.setattr(src.ingest, "embed_chunks", counting)
    return counts


def make_data(folder: Path, names: list[str]) -> Path:
    folder.mkdir(exist_ok=True)
    for name in names:
        make_pdf(folder / name, DOCUMENTS[name])
    return folder


def test_first_build_indexes_everything(tmp_path: Path, embedded: list[int]) -> None:
    data = make_data(tmp_path / "data", [PAPER, OTHER])
    summary = run_ingestion(data, tmp_path / "index")
    assert summary["indexed"] == sorted([PAPER, OTHER]) and summary["removed"] == []
    assert summary["pdfs"] == 2 and summary["pages"] == 4 and summary["chunks"] == summary["new_chunks"]
    _, chunks, info = load_store(tmp_path / "index")
    assert set(info["papers"]) == {PAPER, OTHER}
    assert info["papers"][PAPER]["file"] == file_signature(data / PAPER)
    assert info["papers"][PAPER]["pages"] == 2
    assert [c["chunk_id"] for c in chunks] == list(range(len(chunks)))
    assert is_compatible(info)


def test_adding_a_paper_embeds_only_that_paper(tmp_path: Path, embedded: list[int]) -> None:
    data = make_data(tmp_path / "data", [PAPER])
    run_ingestion(data, tmp_path / "index")
    before = load_store(tmp_path / "index")[1]

    make_data(data, [OTHER])
    assert papers_needing_index(data, load_store(tmp_path / "index")[2]) == [OTHER]
    summary = run_ingestion(data, tmp_path / "index")
    assert summary["indexed"] == [OTHER]
    assert embedded[-1] == summary["new_chunks"] == summary["chunks"] - len(before)
    _, after, info = load_store(tmp_path / "index")
    assert [c["text"] for c in after[:len(before)]] == [c["text"] for c in before]  # old chunks kept as they were
    assert papers_needing_index(data, info) == []

    assert run_ingestion(data, tmp_path / "index")["indexed"] == []  # nothing to do the second time
    assert len(embedded) == 2


def test_a_changed_or_deleted_paper_is_updated(tmp_path: Path, embedded: list[int]) -> None:
    data = make_data(tmp_path / "data", [PAPER, OTHER])
    run_ingestion(data, tmp_path / "index")

    stat = (data / PAPER).stat()
    os.utime(data / PAPER, ns=(stat.st_atime_ns, stat.st_mtime_ns + 5_000_000_000))  # uploaded again
    info = load_store(tmp_path / "index")[2]
    assert papers_needing_index(data, info) == [PAPER]
    assert run_ingestion(data, tmp_path / "index")["indexed"] == [PAPER]

    (data / OTHER).unlink()
    summary = run_ingestion(data, tmp_path / "index")
    assert summary["removed"] == [OTHER] and summary["indexed"] == []
    assert {c["source"] for c in load_store(tmp_path / "index")[1]} == {PAPER}


def test_an_index_from_other_settings_is_rebuilt(tmp_path: Path, embedded: list[int]) -> None:
    data = make_data(tmp_path / "data", [PAPER, OTHER])
    run_ingestion(data, tmp_path / "index")
    info_path = tmp_path / "index" / INFO_FILE
    info = json.loads(info_path.read_text())
    info["pipeline_version"] = 1  # made by an older version of the app
    info_path.write_text(json.dumps(info))

    assert not is_compatible(info)
    assert papers_needing_index(data, info) == sorted([PAPER, OTHER])
    assert papers_needing_index(data, None) == sorted([PAPER, OTHER])
    assert run_ingestion(data, tmp_path / "index")["indexed"] == sorted([PAPER, OTHER])
    assert run_ingestion(data, tmp_path / "index", full=True)["indexed"] == sorted([PAPER, OTHER])


def test_errors(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="No PDF files"):
        run_ingestion(tmp_path / "missing", tmp_path / "index")
    (tmp_path / "data").mkdir()
    shutil.copy(Path(__file__), tmp_path / "data" / "notes.txt")
    with pytest.raises(ValueError, match="No PDF files"):
        run_ingestion(tmp_path / "data", tmp_path / "index")
    make_pdf(tmp_path / "data" / "empty.pdf", [""])
    with pytest.raises(ValueError, match="No text could be extracted"):
        run_ingestion(tmp_path / "data", tmp_path / "index")
