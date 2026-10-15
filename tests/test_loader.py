"""src/loader.py: reading PDFs and removing the text that is not content."""

from pathlib import Path
from typing import Any

import pytest

from evaluation.pdf_writer import make_pdf
from src.loader import (
    attach_captions,
    clean_text,
    drop_references,
    load_pdf,
    load_pdfs,
    repeated_edge_lines,
    strip_edges,
    table_to_text,
)

HEADER = "Journal of Testing, Vol. 3, 2026"
BODY = "Results. The agent found {n} bugs in the level, which is more than the random baseline found."


def paper(tmp_path: Path, name: str = "paper.pdf", **layout: Any) -> Path:
    """A 4-page PDF with a header, page numbers, an arXiv stamp, a table and a reference list."""
    pages = [
        "A Study of Testing Agents\n\n" + BODY.format(n=11),
        BODY.format(n=22),
        {"text": "Table 1: Bugs found by each agent.\n\n" + BODY.format(n=33),
         "table": [["Agent", "Bugs"], ["Curious", "33"], ["Random", "7"]]},
        BODY.format(n=44) + "\n\nReferences\n\n[1] A. Author. A paper about other things. 2020.",
    ]
    path = tmp_path / name
    options: dict[str, Any] = {"header": HEADER, "page_numbers": True, "watermark": "arXiv:2601.00001v1"}
    make_pdf(path, pages, **(options | layout))
    return path


def test_clean_text_fixes_common_pdf_problems() -> None:
    assert clean_text(None) == ""
    assert clean_text("infor-\nmation") == "information"
    assert clean_text("a  \t b") == "a b"
    assert clean_text("one\n\n\n\ntwo") == "one\n\ntwo"
    assert clean_text("eﬃcient") == "efficient"  # the "ffi" ligature
    assert clean_text("exp (cid:18) x (cid:19)") == "exp x"


def test_load_pdf_keeps_content_and_page_numbers(tmp_path: Path) -> None:
    pages = load_pdf(paper(tmp_path))
    assert [p["page"] for p in pages] == [1, 2, 3, 4]
    assert all(p["source"] == "paper.pdf" for p in pages)
    for number, page in zip((11, 22, 33, 44), pages):
        assert f"found {number} bugs" in page["text"]


def test_header_page_number_and_stamp_are_removed(tmp_path: Path) -> None:
    text = " ".join(p["text"] for p in load_pdf(paper(tmp_path)))
    assert HEADER not in text
    assert "arXiv" not in text and "a\nr\nX" not in text
    for page in load_pdf(paper(tmp_path)):
        assert not page["text"].splitlines()[-1].strip().isdigit()


def test_reference_list_is_removed(tmp_path: Path) -> None:
    last = load_pdf(paper(tmp_path))[-1]["text"]
    assert "found 44 bugs" in last
    assert "References" not in last and "other things" not in last


def test_table_is_written_row_by_row_with_its_caption(tmp_path: Path) -> None:
    page3 = load_pdf(paper(tmp_path))[2]["text"]
    table = page3.split("\n\n")[-1]
    assert table.splitlines() == [
        "Table 1: Bugs found by each agent.",
        "Table: Agent | Bugs",
        "Curious: Bugs 33",
        "Random: Bugs 7",
    ]


def test_table_to_text_handles_empty_cells() -> None:
    assert table_to_text([["Name", "A", "B"], ["x", None, "2"], ["", "1", "1"]]).splitlines() == [
        "Table: Name | A | B", "x: B 2", "A 1, B 1"]


def test_repeated_edge_lines_need_three_pages() -> None:
    pages = [["Header 1", "text a"], ["Header 2", "text b"]]
    assert repeated_edge_lines(pages) == set()
    pages.append(["Header 3", "text c"])
    assert repeated_edge_lines(pages) == {"header #"}


def test_strip_edges_keeps_body_lines() -> None:
    assert strip_edges(["Header", "body 1", "body 2", "7"], {"header"}) == ["body 1", "body 2"]


def test_references_only_count_in_the_second_half() -> None:
    pages = [["Intro", "References"], ["text"], ["more"], ["References", "[1] x", "Appendix A", "extra"]]
    assert drop_references(pages) == [["Intro", "References"], ["text"], ["more"], ["Appendix A", "extra"]]


def test_attach_captions_moves_the_caption_to_the_table() -> None:
    body, tables = attach_captions(["text", "Table 2: Results.", "more"], ["Table: A | B\nx: B 1"])
    assert body == ["text", "more"]
    assert tables == ["Table 2: Results.\nTable: A | B\nx: B 1"]


def test_scanned_page_is_read_with_ocr(tmp_path: Path) -> None:
    pytest.importorskip("rapidocr_onnxruntime")
    from PIL import Image, ImageDraw, ImageFont

    image = Image.new("RGB", (1700, 600), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=64)
    draw.text((80, 120), "Scanned page about curiosity agents", fill="black", font=font)
    draw.text((80, 300), "The agent found 42 bugs", fill="black", font=font)
    path = tmp_path / "scan.pdf"
    image.save(path, "PDF", resolution=150)

    pages = load_pdf(path)
    assert len(pages) == 1
    assert "curiosity" in pages[0]["text"].lower() and "42" in pages[0]["text"]


def test_load_pdfs_skips_broken_files_and_can_pick_names(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    paper(tmp_path, "a.pdf")
    paper(tmp_path, "b.pdf")
    (tmp_path / "broken.pdf").write_bytes(b"%PDF-1.4 not really")
    assert {p["source"] for p in load_pdfs(tmp_path)} == {"a.pdf", "b.pdf"}
    assert "could not read broken.pdf" in capsys.readouterr().out
    assert {p["source"] for p in load_pdfs(tmp_path, names=["b.pdf"])} == {"b.pdf"}
