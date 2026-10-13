"""Document loading: read PDFs page by page and keep filename + page number for sources."""

import re
from pathlib import Path

import pdfplumber


def clean_text(text):
    """Clean raw text extracted from a PDF page."""
    if text is None:
        return ""

    # Join words broken by a hyphen at the end of a line: "infor-\nmation" -> "information"
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)

    # Collapse repeated spaces/tabs into one space
    text = re.sub(r"[ \t]+", " ", text)

    # Remove spaces around line breaks
    text = re.sub(r" *\n *", "\n", text)

    # Collapse multiple blank lines into a single blank line
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


def load_pdf(path):
    """Load one PDF and return a list of pages: {"source", "page", "text"}.

    Pages with no text after cleaning are skipped (but counted).
    """
    path = Path(path)
    pages = []
    empty_pages = 0

    with pdfplumber.open(path) as pdf:
        total_pages = len(pdf.pages)
        for page_number, page in enumerate(pdf.pages, start=1):
            # x_tolerance=1.5: smaller gap counts as a space (default 3 glued words together)
            # use_text_flow=True: follow the PDF's own reading order (keeps two columns apart)
            text = clean_text(page.extract_text(x_tolerance=1.5, use_text_flow=True))
            if not text:
                empty_pages += 1
                continue
            pages.append({"source": path.name, "page": page_number, "text": text})

    # No text on any page -> probably a scanned (image-only) PDF
    if total_pages > 0 and not pages:
        print(f"WARNING: {path.name}: no text found, it may be a scanned (image) PDF")
    elif empty_pages:
        print(f"NOTE: {path.name}: skipped {empty_pages} empty page(s) out of {total_pages}")

    return pages


def load_pdfs(data_dir="data"):
    """Load all PDFs in data_dir (sorted by name) and return one combined list of pages."""
    pdf_paths = sorted(p for p in Path(data_dir).iterdir() if p.suffix.lower() == ".pdf")

    all_pages = []
    for path in pdf_paths:
        try:
            all_pages.extend(load_pdf(path))
        except Exception as e:
            # One bad PDF should not stop the others
            print(f"WARNING: could not read {path.name}: {e}")

    return all_pages
