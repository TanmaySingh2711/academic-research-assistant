"""Document loading: read PDFs page by page and keep filename + page number for sources.

Real papers contain text that is not part of the content and only confuses the search:
a running header and a page number on every page, a rotated arXiv stamp on the margin, and a
long reference list at the end. This module removes those, writes tables row by row so their
numbers stay next to their column names, and reads scanned pages with OCR (offline).
"""

import re
import threading
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any

import pdfplumber

from src.schema import Page

# A page with less text than this, but with an image, is treated as a scanned page
MIN_TEXT_CHARS = 20
# A line counts as a running header or footer when it is at the top or bottom of this share of pages
REPEATED_SHARE = 0.5
EDGE_LINES = 2  # how many lines at the top and at the bottom are checked for headers and footers
MAX_EDGE_WORDS = 15  # headers and footers are short; a longer line is content, even if it repeats

PAGE_NUMBER = re.compile(r"^(?:page\s*)?\d{1,4}(?:\s*(?:of|/)\s*\d{1,4})?$", re.IGNORECASE)
# "References", "7 References", "VII. REFERENCES", "Bibliography" on a line of its own
REFERENCES_HEADING = re.compile(
    r"^(?:\d{1,2}\.?\s*|[ivx]{1,5}\.\s*)?(?:references|bibliography|literature cited)$", re.IGNORECASE)
TABLE_CAPTION = re.compile(r"^table\s+[ivx\d]+\s*[.:]", re.IGNORECASE)  # "Table 1:", "TABLE II."
# Content after the references starts again at an appendix
APPENDIX_HEADING = re.compile(r"^(?:[a-z]\.?\s+)?(?:appendix|appendices)\b", re.IGNORECASE)

_ocr_engine: Any = None
_ocr_lock = threading.Lock()


def clean_text(text: str | None) -> str:
    """Clean raw text extracted from a PDF page."""
    if text is None:
        return ""

    # Ligatures and special forms become normal letters: the "fi" ligature -> "fi"
    text = unicodedata.normalize("NFKC", text)

    # "(cid:18)" is a glyph the PDF reader could not map to a letter (often a math symbol)
    text = re.sub(r"\(cid:\d+\)", " ", text)

    # Join words broken by a hyphen at the end of a line: "infor-\nmation" -> "information"
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)

    # Collapse repeated spaces/tabs into one space
    text = re.sub(r"[ \t]+", " ", text)

    # Remove spaces around line breaks
    text = re.sub(r" *\n *", "\n", text)

    # Collapse multiple blank lines into a single blank line
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


def table_to_text(rows: list[list[str | None]]) -> str:
    """Write a table row by row, each value next to its column name.

    | Game     | Playable |        "Table: Game | Playable
    | Sky Hop  | 91.5     |   ->    Sky Hop: Playable 91.5"
    """
    cells = [[" ".join((cell or "").split()) for cell in row] for row in rows]
    header, body = cells[0], cells[1:]
    lines = ["Table: " + " | ".join(header)]
    for row in body:
        values = [f"{name} {value}".strip() for name, value in zip(header[1:], row[1:]) if value]
        lines.append(f"{row[0]}: " + ", ".join(values) if row[0] else ", ".join(values))
    return "\n".join(lines)


def ocr_page(page: Any) -> str:
    """Read the text of a scanned page with RapidOCR (runs offline, the models come with the library)."""
    global _ocr_engine
    try:
        import numpy as np
        from rapidocr_onnxruntime import RapidOCR
    except ImportError:
        return ""  # OCR is optional: without it, scanned pages are skipped
    with _ocr_lock:
        if _ocr_engine is None:
            _ocr_engine = RapidOCR()
        image = page.to_image(resolution=200).original
        found, _ = _ocr_engine(np.array(image.convert("RGB")))
    # found: [[box corners, text, confidence], ...], sorted top to bottom by RapidOCR
    return "\n".join(text for _, text, confidence in (found or []) if float(confidence) >= 0.5)


def read_page(page: Any) -> tuple[list[str], list[str], bool]:
    """Return (lines of normal text, tables as text, read with OCR) for one pdfplumber page."""
    # Rotated characters (like the arXiv stamp on the margin) would come out one letter per line
    upright = page.filter(lambda obj: obj.get("object_type") != "char" or obj.get("upright", True))

    # Tables with lines around their cells: take them out of the normal text and write them row by row
    tables = []
    body = upright
    for table in upright.find_tables():
        rows = table.extract()
        if len(rows) >= 2 and max(len(row) for row in rows) >= 2:
            tables.append(table_to_text(rows))
            body = body.outside_bbox(table.bbox)

    # x_tolerance=1.5: smaller gap counts as a space (default 3 glued words together)
    # use_text_flow=True: follow the PDF's own reading order (keeps two columns apart)
    text = body.extract_text(x_tolerance=1.5, use_text_flow=True) or ""
    if len(text.strip()) < MIN_TEXT_CHARS and page.images:
        ocr_text = ocr_page(page)
        if ocr_text:
            return ocr_text.splitlines(), tables, True
    return text.splitlines(), tables, False


def repeated_edge_lines(pages: list[list[str]]) -> set[str]:
    """Lines (digits ignored) found at the top or bottom of at least half of the pages."""
    if len(pages) < 3:
        return set()
    counts: Counter[str] = Counter()
    for lines in pages:
        lines = [line.strip() for line in lines if line.strip()]
        edges = lines[:EDGE_LINES] + lines[-EDGE_LINES:]
        counts.update({edge_key(line) for line in edges if len(line.split()) <= MAX_EDGE_WORDS})
    return {key for key, n in counts.items() if n >= max(3, REPEATED_SHARE * len(pages))}


def edge_key(line: str) -> str:
    # "Page 3 of 12" and "Page 4 of 12" are the same footer
    return re.sub(r"\d+", "#", line.strip().lower())


def strip_edges(lines: list[str], repeated: set[str]) -> list[str]:
    """Remove running headers, footers and page numbers from the top and bottom of a page."""
    lines = [line for line in lines if line.strip()]

    def is_noise(line: str) -> bool:
        return edge_key(line) in repeated or PAGE_NUMBER.match(line.strip()) is not None

    for _ in range(EDGE_LINES):
        if lines and is_noise(lines[0]):
            lines.pop(0)
        if lines and is_noise(lines[-1]):
            lines.pop()
    return lines


def drop_references(pages: list[list[str]]) -> list[list[str]]:
    """Remove the reference list: from a "References" heading in the second half of the paper
    until the end, or until an appendix starts. The references only list other papers' titles,
    which match many questions without answering them."""
    start_page = len(pages) // 2
    inside = False
    result = []
    for number, lines in enumerate(pages):
        kept = []
        for line in lines:
            if not inside and number >= start_page and REFERENCES_HEADING.match(line.strip()):
                inside = True
            elif inside and APPENDIX_HEADING.match(line.strip()):
                inside = False
            if not inside:
                kept.append(line)
        result.append(kept)
    return result


def attach_captions(body: list[str], tables: list[str]) -> tuple[list[str], list[str]]:
    """Move a caption line like "Table 1: Results for each game." from the text to its table,
    so the table chunk says what the numbers are about. Tables and captions are matched in order."""
    captions = [i for i, line in enumerate(body) if TABLE_CAPTION.match(line.strip())]
    moved = dict(zip(range(len(tables)), captions))
    tables = [f"{body[moved[t]].strip()}\n{table}" if t in moved else table for t, table in enumerate(tables)]
    body = [line for i, line in enumerate(body) if i not in moved.values()]
    return body, tables


def load_pdf(path: str | Path) -> list[Page]:
    """Load one PDF and return a list of pages: {"source", "page", "text"}.

    Pages with no text after cleaning are skipped (but counted).
    """
    path = Path(path)
    with pdfplumber.open(path) as pdf:
        read = [read_page(page) for page in pdf.pages]
    total_pages = len(read)

    repeated = repeated_edge_lines([lines for lines, _, _ in read])
    bodies = drop_references([strip_edges(lines, repeated) for lines, _, _ in read])

    pages: list[Page] = []
    ocr_pages = 0
    for number, (body, (_, tables, used_ocr)) in enumerate(zip(bodies, read), start=1):
        ocr_pages += used_ocr
        body, tables = attach_captions(body, tables)
        # Blank lines separate the text and each table, so the chunker can keep a table together
        text = clean_text("\n\n".join(["\n".join(body)] + tables))
        if text:
            pages.append({"source": path.name, "page": number, "text": text})

    # No text on any page -> probably a scanned (image-only) PDF and OCR is not installed
    if total_pages > 0 and not pages:
        print(f"WARNING: {path.name}: no text found, it may be a scanned (image) PDF")
    elif len(pages) < total_pages:
        print(f"NOTE: {path.name}: skipped {total_pages - len(pages)} empty page(s) out of {total_pages}")
    if ocr_pages:
        print(f"NOTE: {path.name}: read {ocr_pages} scanned page(s) with OCR")

    return pages


def load_pdfs(data_dir: str | Path = "data", names: list[str] | None = None) -> list[Page]:
    """Load all PDFs in data_dir (sorted by name), or only `names`, as one combined list of pages."""
    pdf_paths = sorted(p for p in Path(data_dir).iterdir() if p.suffix.lower() == ".pdf")
    if names is not None:
        pdf_paths = [p for p in pdf_paths if p.name in names]

    all_pages: list[Page] = []
    for path in pdf_paths:
        try:
            all_pages.extend(load_pdf(path))
        except Exception as e:
            # One bad PDF should not stop the others
            print(f"WARNING: could not read {path.name}: {e}")

    return all_pages
