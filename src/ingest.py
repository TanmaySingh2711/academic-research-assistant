"""Ingestion: PDFs -> pages -> chunks -> embeddings -> FAISS index saved to disk."""

import time
from pathlib import Path

from src.chunker import chunk_pages
from src.embedder import MODEL_NAME, embed_chunks
from src.loader import load_pdfs
from src.vector_store import build_index, save_store

CHUNK_SIZE = 100
OVERLAP = 20


def run_ingestion(data_dir="data", index_dir="index"):
    """Build and save the index from all PDFs in data_dir. Returns a short summary."""
    start = time.perf_counter()

    data_path = Path(data_dir)
    pdf_count = sum(1 for p in data_path.iterdir() if p.suffix.lower() == ".pdf") if data_path.exists() else 0
    if pdf_count == 0:
        raise ValueError(f"No PDF files found in '{data_dir}'. Upload some PDFs first.")

    pages = load_pdfs(data_dir)
    chunks = chunk_pages(pages, chunk_size=CHUNK_SIZE, overlap=OVERLAP)
    # Never build an empty index (e.g. all PDFs are scanned images with no text)
    if not chunks:
        raise ValueError("No text could be extracted from the PDFs (they may be scanned images). Nothing to index.")

    vectors = embed_chunks(chunks)
    index = build_index(vectors)
    save_store(index, chunks, index_dir, model_name=MODEL_NAME, chunk_size=CHUNK_SIZE, overlap=OVERLAP)

    return {
        "pdfs": pdf_count,
        "pages": len(pages),
        "chunks": len(chunks),
        "seconds": round(time.perf_counter() - start, 2),
    }
