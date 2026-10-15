"""src/chunker.py: sentences, chunks with overlap, tables, section headings and abbreviations."""

import pytest

from src.chunker import (
    add_abbreviations,
    chunk_pages,
    chunk_table,
    chunk_text,
    find_abbreviations,
    heading_of,
    split_into_chunks,
    split_sentences,
)
from src.schema import Page


def sentence(n: int, words: int = 10) -> str:
    return " ".join([f"S{n}"] + [f"w{n}x{i}" for i in range(words - 2)]) + " end."


def test_split_into_chunks_by_words_with_overlap() -> None:
    words = " ".join(str(i) for i in range(250))
    chunks = split_into_chunks(words, chunk_size=100, overlap=20)
    assert [len(c.split()) for c in chunks] == [100, 100, 90]
    assert chunks[0].split()[-20:] == chunks[1].split()[:20]
    assert split_into_chunks("") == []


@pytest.mark.parametrize("size, overlap", [(0, 0), (10, 10), (10, -1)])
def test_bad_sizes_are_refused(size: int, overlap: int) -> None:
    with pytest.raises(ValueError):
        chunk_text("text", size, overlap)


def test_split_sentences_keeps_abbreviations_together() -> None:
    text = "See Fig. 2 for details. Smith et al. showed this. It works, e.g. in games. II. METHOD We test."
    assert split_sentences(text) == [
        "See Fig. 2 for details.", "Smith et al. showed this.", "It works, e.g. in games.", "II. METHOD We test."]


def test_chunks_are_whole_sentences_with_overlap() -> None:
    text = " ".join(sentence(i) for i in range(25))  # 25 sentences of 10 words
    chunks = chunk_text(text, chunk_size=100, overlap=20)
    assert all(len(c.split()) <= 100 for c in chunks)
    assert all(c.endswith("end.") for c in chunks)  # never cut in the middle of a sentence
    for first, second in zip(chunks, chunks[1:]):
        assert split_sentences(first)[-2:] == split_sentences(second)[:2]  # the last 2 sentences are carried over


def test_at_least_one_sentence_is_carried_even_when_it_is_long() -> None:
    # 30-word sentences are longer than the 20-word overlap, but the last one is still carried
    chunks = chunk_text(" ".join(sentence(i, words=30) for i in range(8)), chunk_size=100, overlap=20)
    assert len(chunks) > 1
    for first, second in zip(chunks, chunks[1:]):
        assert split_sentences(first)[-1] == split_sentences(second)[0]


def test_a_very_long_sentence_is_cut_by_words() -> None:
    chunks = chunk_text("Intro sentence. Long " + " ".join(["word"] * 230) + ".", chunk_size=100, overlap=20)
    assert chunks[0] == "Intro sentence."
    assert all(len(c.split()) <= 100 for c in chunks)


def test_headings_are_recognized() -> None:
    assert heading_of("IV. METHOD As previously mentioned, it works") == "IV. METHOD"
    assert heading_of("II. RELATED WORK Recently, many works") == "II. RELATED WORK"
    assert heading_of("3 Results We show") == "3 Results"
    assert heading_of("Acquisition Function: The function is") == "Acquisition Function"
    assert heading_of("Search settings.") == "Search settings"
    assert heading_of("We used 64 levels.") is None
    assert heading_of("In 2020 we did this.") is None


def test_chunks_in_the_middle_of_a_section_get_its_heading() -> None:
    text = "Search settings. " + " ".join(sentence(i) for i in range(20))
    chunks = chunk_text(text, chunk_size=60, overlap=10)
    assert chunks[0].startswith("Search settings.")
    assert all(c.startswith("(Section: Search settings)") for c in chunks[1:])


def test_heading_glued_inside_a_sentence_is_found() -> None:
    text = ("Before (2) Acquisition Function: The function is optimized every step. "
            + " ".join(sentence(i) for i in range(12)))
    chunks = chunk_text(text, chunk_size=50, overlap=5)
    assert chunks[-1].startswith("(Section: Acquisition Function)")


def test_tables_get_chunks_of_their_own_with_the_column_line() -> None:
    rows = "\n".join(f"Row {i}: Value {i}, Other {i * 2}" for i in range(40))
    block = f"Table 1: Results.\nTable: Name | Value | Other\n{rows}"
    chunks = chunk_text(f"Some text before the table.\n\n{block}", chunk_size=60, overlap=10)
    assert chunks[0] == "Some text before the table."
    tables = chunks[1:]
    assert len(tables) > 1
    assert all(t.startswith("Table 1: Results.\nTable: Name | Value | Other\n") for t in tables)
    assert sum(t.count("Row ") for t in tables) == 40  # every row once
    assert chunk_table("Table: A | B\nx: B 1", 100) == ["Table: A | B\nx: B 1"]


def test_find_abbreviations() -> None:
    text = ("We use Reinforcement Learning (RL) and Gaussian Processes (GPs). The Lower Confidence Bound (LCB) "
            "is used. See (Fig) and (i) and Random Words (XYZ).")
    assert find_abbreviations(text) == {"RL": "Reinforcement Learning", "GP": "Gaussian Processes",
                                        "LCB": "Lower Confidence Bound"}


def test_abbreviations_are_added_to_chunks_that_only_use_the_short_form() -> None:
    pages: list[Page] = [{"source": "p.pdf", "page": 1, "text": "Reinforcement Learning (RL) is popular."},
             {"source": "p.pdf", "page": 2, "text": "RL needs many hours of training."}]
    chunks = chunk_pages(pages)
    add_abbreviations(chunks, pages)
    assert "Abbreviations" not in chunks[0]["text"]  # the long form is already there
    assert chunks[1]["text"].endswith("\nAbbreviations: RL = Reinforcement Learning")
    assert chunks[1]["word_count"] == len(chunks[1]["text"].split())


def test_chunk_pages_keeps_source_page_and_ids() -> None:
    pages: list[Page] = [{"source": "a.pdf", "page": 1, "text": "One. Two."},
                         {"source": "b.pdf", "page": 7, "text": "Three."}]
    chunks = chunk_pages(pages, first_id=5)
    assert [(c["chunk_id"], c["source"], c["page"], c["text"]) for c in chunks] == [
        (5, "a.pdf", 1, "One. Two."), (6, "b.pdf", 7, "Three.")]
