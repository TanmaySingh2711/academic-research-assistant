"""Quick test for src/loader.py: load all PDFs in data/ and print a summary."""

from collections import defaultdict
from pathlib import Path

import pdfplumber

from src.loader import load_pdfs

DATA_DIR = "data"

pages = load_pdfs(DATA_DIR)

# Group loaded pages by source file
by_source = defaultdict(list)
for p in pages:
    by_source[p["source"]].append(p)

print("\n=== Summary per PDF ===")
for path in sorted(Path(DATA_DIR).glob("*.pdf")):
    # Open the PDF again only to count its total pages
    with pdfplumber.open(path) as pdf:
        total = len(pdf.pages)
    with_text = len(by_source[path.name])
    print(f"{path.name}")
    print(f"  total pages: {total} | pages with text: {with_text} | empty pages: {total - with_text}")

print(f"\nTotal pages loaded: {len(pages)}")

print("\n=== First 300 characters of page 1 of each PDF ===")
for source, source_pages in by_source.items():
    first = next((p for p in source_pages if p["page"] == 1), None)
    print(f"\n--- {source} (page 1) ---")
    print(first["text"][:300] if first else "(page 1 has no text)")
