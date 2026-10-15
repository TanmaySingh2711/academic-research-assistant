"""The shapes of the dictionaries that move through the pipeline (used for type hints only)."""

from typing import TypedDict


class Page(TypedDict):
    """One PDF page after reading and cleaning (src/loader.py)."""
    source: str  # PDF file name
    page: int  # page number, starting at 1
    text: str


class Chunk(TypedDict):
    """A small piece of one page (src/chunker.py). Row i of the FAISS index belongs to chunks[i]."""
    chunk_id: int
    source: str
    page: int
    text: str
    word_count: int


class SearchResult(TypedDict):
    """A chunk found for a question, with its score (src/retriever.py)."""
    rank: int
    score: float
    chunk_id: int
    source: str
    page: int
    text: str


class Source(TypedDict):
    """A source shown under an answer. source_number is the N in [Source N]."""
    source_number: int
    source: str
    page: int
    score: float
    text: str


class Turn(TypedDict):
    """One earlier question and answer of the same chat."""
    question: str
    answer: str


class Message(TypedDict):
    """A chat message for the LLM."""
    role: str  # "system", "user" or "assistant"
    content: str
