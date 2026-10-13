"""Rebuild the index from the terminal: PDFs in data/ -> FAISS index in index/."""

from src.ingest import run_ingestion

summary = run_ingestion("data", "index")

print(f"PDFs:    {summary['pdfs']}")
print(f"Pages:   {summary['pages']}")
print(f"Chunks:  {summary['chunks']}")
print(f"Saved to index/ in {summary['seconds']} seconds")
