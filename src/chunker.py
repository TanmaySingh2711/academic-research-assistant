"""Chunking: split page text into small overlapping chunks, keeping source + page.

Chunks are built from whole sentences, so a fact is not cut in half at a chunk border.
Neighbouring chunks share their last sentence(s) (about `overlap` words), so a fact near a
border appears complete in at least one chunk. A table gets chunks of its own, with its
caption and column names, so its numbers keep their meaning.
"""

import re

from src.schema import Chunk, Page

# A sentence ends with . ! or ? followed by a space and an upper-case letter, digit, bracket or quote.
# "e.g. the" and "Fig. 2" are not split, because the next character is lower-case or the word is short.
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\[(\"'])")
_ABBREVIATION = re.compile(r"(?:\b(?:fig|eq|ref|sec|tab|no|vs|al|et|i\.e|e\.g|cf)\.|\b[A-Z]\.|\b[IVX]{1,4}\.)$",
                           re.IGNORECASE)


def split_into_chunks(text: str, chunk_size: int = 100, overlap: int = 20) -> list[str]:
    """Split text into chunks of up to chunk_size words; neighbours share `overlap` words.

    Used for one very long sentence (no sentence borders to cut at)."""
    check_sizes(chunk_size, overlap)
    words = text.split()
    if not words:
        return []

    step = chunk_size - overlap  # how far the window moves each time
    chunks = []
    for start in range(0, len(words), step):
        chunks.append(" ".join(words[start:start + chunk_size]))
        # Stop once this chunk reaches the end, so no tiny duplicate chunk is added
        if start + chunk_size >= len(words):
            break

    return chunks


def check_sizes(chunk_size: int, overlap: int) -> None:
    if chunk_size <= 0:
        raise ValueError(f"chunk_size must be > 0 (got {chunk_size})")
    if overlap < 0 or overlap >= chunk_size:
        raise ValueError(f"overlap must be >= 0 and < chunk_size (got overlap={overlap}, chunk_size={chunk_size})")


def split_sentences(text: str) -> list[str]:
    """Split prose into sentences."""
    parts = _SENTENCE_END.split(" ".join(text.split()))
    sentences: list[str] = []
    for part in parts:
        # Glue back a split after an abbreviation such as "Fig." or "et al."
        if sentences and _ABBREVIATION.search(sentences[-1]):
            sentences[-1] += " " + part
        else:
            sentences.append(part)
    return [s for s in sentences if s]


# Section headings, as papers write them:
#   "IV. METHOD"  (Roman number and capitals)          "3 Results" / "3.2 Data set"  (number and title)
#   "Acquisition Function: The function ..."  (a few words and a colon, then the text)
#   "Search settings. We used ..."  (a short phrase as its own sentence)
_NUMBERED_HEADING = re.compile(r"^((?:[IVX]{1,4}\.|\d{1,2}(?:\.\d{1,2})*\.?)\s+[A-Z][A-Za-z-]*(?:\s+[A-Za-z-]+){0,5}?)"
                               r"(?=\s+[A-Z][a-z]+[\s,]|$)")
_RUN_IN_HEADING = re.compile(r"^([A-Z][\w-]*(?:\s+[\w-]+){0,6}):\s")
# The same heading in the middle of a "sentence" (PDFs often glue it to an equation before it):
# Title Case words, a colon, then a capital letter, e.g. "... (2) Acquisition Function: The ..."
_INNER_HEADING = re.compile(r"(?<![\w,;:])\s([A-Z][a-z]+(?:[ -](?:[A-Z][\w-]*|based|on|of|for|and|the|in|with)){1,6})"
                            r":\s+(?=[A-Z])")


def heading_of(sentence: str) -> str | None:
    """The section heading a sentence starts with, or None."""
    words = sentence.split()
    if 1 <= len(words) <= 4 and sentence.endswith(".") and sentence[0].isupper() \
            and not any(ch.isdigit() for ch in sentence):
        return sentence.rstrip(".")
    for pattern in (_NUMBERED_HEADING, _RUN_IN_HEADING):
        match = pattern.match(sentence)
        if match and len(match.group(1).split()) <= 8:
            return match.group(1)
    return None


def chunk_sentences(sentences: list[str], chunk_size: int, overlap: int) -> list[str]:
    """Group sentences into chunks of at most chunk_size words.

    A chunk that starts in the middle of a section gets the section heading in front, like
    "(Section: Acquisition Function) This function is known as ...", so a chunk that says
    "this function" still tells the search and the LLM which function it is about.
    """
    headings: list[str | None] = []  # the section each sentence belongs to
    current_heading = None
    for sentence in sentences:
        current_heading = heading_of(sentence) or current_heading
        headings.append(current_heading)
        inner = _INNER_HEADING.findall(sentence)
        if inner:  # applies to the sentences after this one
            current_heading = inner[-1]

    def finish(first: int, last: int) -> str:
        text = " ".join(sentences[first:last + 1])
        heading = headings[first]
        if heading and not text.startswith(heading):
            text = f"(Section: {heading}) {text}"
        return text

    chunks: list[str] = []
    start = 0  # first sentence of the chunk being built
    count = 0  # words in it
    for i, sentence in enumerate(sentences):
        words = len(sentence.split())
        if words > chunk_size:  # a single very long sentence: cut it by words
            if i > start:
                chunks.append(finish(start, i - 1))
            chunks.extend(split_into_chunks(sentence, chunk_size, overlap))
            start, count = i + 1, 0
            continue
        if i > start and count + words > chunk_size:
            chunks.append(finish(start, i - 1))
            # Start the next chunk with the last sentences of this one, up to `overlap` words.
            # At least the last sentence is carried (unless it is very long): papers write
            # long sentences, and without it a chunk loses what "it" refers to.
            new_start, carried = i, 0
            while new_start - 1 >= start:
                previous = len(sentences[new_start - 1].split())
                too_long = carried + previous > overlap
                if too_long and (carried or previous > chunk_size // 2):
                    break
                new_start -= 1
                carried += previous
            start, count = new_start, carried
        count += words
    if start < len(sentences):
        chunks.append(finish(start, len(sentences) - 1))
    return chunks


def chunk_table(block: str, chunk_size: int) -> list[str]:
    """A table block (caption, "Table:" line with the columns, one line per row) as chunks.

    A long table is split between rows, and every part repeats the caption and column line."""
    lines = block.splitlines()
    head_end = next((i + 1 for i, line in enumerate(lines) if line.startswith("Table:")), 1)
    head, rows = lines[:head_end], lines[head_end:]
    chunks: list[str] = []
    part: list[str] = []
    for row in rows:
        if part and len(" ".join(head + part + [row]).split()) > chunk_size:
            chunks.append("\n".join(head + part))
            part = []
        part.append(row)
    chunks.append("\n".join(head + part))
    return chunks


def is_table(block: str) -> bool:
    return any(line.startswith("Table:") for line in block.splitlines()[:2])


def chunk_text(text: str, chunk_size: int = 100, overlap: int = 20) -> list[str]:
    """Chunks of one page: the prose by sentences, every table separately."""
    check_sizes(chunk_size, overlap)
    chunks: list[str] = []
    for block in text.split("\n\n"):  # the loader puts a blank line between the text and each table
        if not block.strip():
            continue
        if is_table(block):
            chunks.extend(chunk_table(block, chunk_size))
        else:
            chunks.extend(chunk_sentences(split_sentences(block), chunk_size, overlap))
    return chunks


_DEFINITION = re.compile(r"\(([A-Z][A-Za-z]{1,7})\)")  # "(RL)", "(GPs)", "(CoM)"


def find_abbreviations(text: str) -> dict[str, str]:
    """Abbreviations defined in a paper, like "Reinforcement Learning (RL)" -> {"RL": "Reinforcement Learning"}.

    The words just before the brackets are taken as the long form when their first letters
    spell the abbreviation (a simple version of the Schwartz-Hearst method)."""
    found: dict[str, str] = {}
    for match in _DEFINITION.finditer(text):
        short = match.group(1)
        letters = short[:-1] if short.endswith("s") and len(short) > 2 else short  # "GPs" -> "GP"
        if sum(1 for c in letters if c.isupper()) < 2:
            continue  # "(i)" or "(Fig)" are not abbreviations
        wanted = [c.lower() for c in letters if c.isupper()]
        words = re.findall(r"[A-Za-z][\w']*", text[max(0, match.start() - 120):match.start()])
        candidate = words[-len(wanted):]
        if len(candidate) == len(wanted) and [w[0].lower() for w in candidate] == wanted:
            found.setdefault(letters, " ".join(candidate))
    return found


def add_abbreviations(chunks: list[Chunk], pages: list[Page]) -> None:
    """Add a line like "Abbreviations: RL = Reinforcement Learning" to every chunk that uses an
    abbreviation without its long form. Papers define an abbreviation once and use only the short
    form afterwards, so without this a question about "reinforcement learning" misses chunks that
    only say "RL" (and the other way round)."""
    by_paper: dict[str, dict[str, str]] = {}
    for source in {page["source"] for page in pages}:
        by_paper[source] = find_abbreviations(" ".join(p["text"] for p in pages if p["source"] == source))
    for chunk in chunks:
        notes = [f"{short} = {long}" for short, long in by_paper.get(chunk["source"], {}).items()
                 if re.search(rf"\b{short}s?\b", chunk["text"]) and long.lower() not in chunk["text"].lower()]
        if notes:
            chunk["text"] += "\nAbbreviations: " + "; ".join(notes)
            chunk["word_count"] = len(chunk["text"].split())


def chunk_pages(pages: list[Page], chunk_size: int = 100, overlap: int = 20, first_id: int = 0) -> list[Chunk]:
    """Chunk each page from load_pdfs separately and return a list of chunk dicts.

    Text is never joined across pages, so every chunk has one correct page number.
    """
    chunks: list[Chunk] = []
    chunk_id = first_id  # unique across all chunks

    for page in pages:
        for text in chunk_text(page["text"], chunk_size, overlap):
            chunks.append({
                "chunk_id": chunk_id,
                "source": page["source"],
                "page": page["page"],
                "text": text,
                "word_count": len(text.split()),
            })
            chunk_id += 1

    return chunks
