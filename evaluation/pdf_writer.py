"""Write simple PDFs with the standard library only (no PDF library needed).

Used by the tests and by the evaluation corpus. Besides plain text pages it can add the things
that make real papers hard to read: a running header on every page, a page number at the bottom,
a rotated arXiv-style stamp on the left margin, and a table drawn with lines.

A page is either a string, or a dict {"text": "...", "table": [["header", ...], ["cell", ...], ...]}.
"""

import textwrap
from pathlib import Path
from typing import Any

PAGE_WIDTH, PAGE_HEIGHT = 612, 792
LEFT = 60
LINE_HEIGHT = 14


def escape(text: str) -> str:
    """Escape the characters that have a special meaning inside a PDF string."""
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def text_at(x: float, y: float, text: str, size: int = 10) -> str:
    """PDF commands that write one line of text with its left end at (x, y)."""
    return f"BT /F1 {size} Tf 1 0 0 1 {x} {y} Tm ({escape(text)}) Tj ET\n"


def table_commands(rows: list[list[str]], top: float) -> str:
    """Draw a table with a line around every cell, starting at the y position `top`."""
    columns = len(rows[0])
    width = (PAGE_WIDTH - 2 * LEFT) / columns
    height = 18
    out = "0.5 w\n"
    for r, row in enumerate(rows):
        y = top - (r + 1) * height
        for c, cell in enumerate(row):
            x = LEFT + c * width
            out += f"{x:.1f} {y:.1f} {width:.1f} {height} re S\n"  # cell border
            out += text_at(round(x + 4, 1), round(y + 5, 1), cell, size=9)
    return out


def page_commands(page: str | dict, number: int, header: str | None, page_numbers: bool,
                  watermark: str | None) -> str:
    """All drawing commands of one page."""
    content: dict[str, Any] = page if isinstance(page, dict) else {"text": page}
    out = ""
    if header:
        out += text_at(LEFT, PAGE_HEIGHT - 40, header, size=8)
    y = PAGE_HEIGHT - 70
    # Paragraphs are separated by a blank line in the text
    for paragraph in content["text"].split("\n\n"):
        for line in textwrap.wrap(paragraph, width=95, break_on_hyphens=False):
            out += text_at(LEFT, y, line)
            y -= LINE_HEIGHT
        y -= LINE_HEIGHT // 2
    if content.get("table"):
        out += table_commands(content["table"], y - 6)
    if page_numbers:
        out += text_at(PAGE_WIDTH / 2 - 3, 30, str(number), size=9)
    if watermark:
        # Rotated 90 degrees on the left margin, like the arXiv stamp on preprints
        out += f"BT /F1 14 Tf 0 1 -1 0 30 220 Tm ({escape(watermark)}) Tj ET\n"
    return out


def make_pdf(path: str | Path, pages: list, header: str | None = None, page_numbers: bool = False,
             watermark: str | None = None) -> None:
    """Write a valid PDF with one page per item in `pages`. The watermark is drawn on page 1 only."""
    # Objects: 1 catalog, 2 page list, 3 font, then a page object and a content object per page
    page_ids = [4 + 2 * i for i in range(len(pages))]
    objects = {
        1: "<< /Type /Catalog /Pages 2 0 R >>",
        2: f"<< /Type /Pages /Kids [{' '.join(f'{p} 0 R' for p in page_ids)}] /Count {len(pages)} >>",
        3: "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    }
    for number, (page_id, page) in enumerate(zip(page_ids, pages), start=1):
        stream = page_commands(page, number, header, page_numbers, watermark if number == 1 else None)
        objects[page_id] = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {PAGE_WIDTH} {PAGE_HEIGHT}] "
            f"/Resources << /Font << /F1 3 0 R >> >> /Contents {page_id + 1} 0 R >>"
        )
        objects[page_id + 1] = f"<< /Length {len(stream)} >>\nstream\n{stream}\nendstream"

    # Write the objects and remember where each one starts (the xref table needs byte offsets)
    out = bytearray(b"%PDF-1.4\n")
    offsets = {}
    for number in sorted(objects):
        offsets[number] = len(out)
        out += f"{number} 0 obj\n{objects[number]}\nendobj\n".encode("latin-1")

    xref_start = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode("ascii")
    for number in sorted(objects):
        out += f"{offsets[number]:010d} 00000 n \n".encode("ascii")
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_start}\n%%EOF\n".encode("ascii")

    Path(path).write_bytes(out)
