"""Rebuild the index from the terminal: PDFs in data/ -> FAISS index in index/.

Usage (from the project folder): python scripts/build_index.py
"""

import sys
from pathlib import Path

# The project folder is one level above scripts/; this makes "import src" work
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.ingest import run_ingestion  # noqa: E402

summary = run_ingestion(ROOT / "data", ROOT / "index")

print(f"PDFs:    {summary['pdfs']}")
print(f"Pages:   {summary['pages']}")
print(f"Chunks:  {summary['chunks']}")
print(f"Saved to index/ in {summary['seconds']} seconds")
