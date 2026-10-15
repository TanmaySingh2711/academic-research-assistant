"""Ingestion: PDFs -> pages -> chunks -> embeddings -> FAISS index saved to disk.

Build index only does the work that is needed: papers that are already in the index and did
not change keep their vectors, so adding one paper only embeds that paper. A full rebuild
happens when the index was made with other settings (model, chunk size, or an older version
of the PDF reading and chunking code, see PIPELINE_VERSION).
"""

import time
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np

from src.chunker import add_abbreviations, chunk_pages
from src.embedder import MODEL_NAME, embed_chunks
from src.loader import load_pdfs
from src.schema import Chunk
from src.vector_store import all_vectors, build_index, load_store, normalize_vectors, remove_paper, renumber, save_store

CHUNK_SIZE = 100
OVERLAP = 20
# Raise this number whenever loader.py or chunker.py change how chunks are made:
# an index built by an older version is then rebuilt by the next Build index.
PIPELINE_VERSION = 2


def file_signature(path: Path) -> dict[str, int]:
    """Size and change time of a file. If either differs, the paper was replaced (uploaded again)."""
    stat = path.stat()
    return {"size": stat.st_size, "mtime_ns": stat.st_mtime_ns}


def settings(chunk_size: int, overlap: int) -> dict[str, Any]:
    return {"model_name": MODEL_NAME, "chunk_size": chunk_size, "overlap": overlap,
            "pipeline_version": PIPELINE_VERSION}


def is_compatible(info: dict[str, Any], chunk_size: int = CHUNK_SIZE, overlap: int = OVERLAP) -> bool:
    """True if an index was built with the same settings as now, so papers can be added to it."""
    wanted = settings(chunk_size, overlap)
    return "papers" in info and all(info.get(key) == value for key, value in wanted.items())


def pdf_paths(data_dir: Path) -> dict[str, Path]:
    if not data_dir.exists():
        return {}
    return {p.name: p for p in sorted(data_dir.iterdir()) if p.suffix.lower() == ".pdf"}


def papers_needing_index(data_dir: str | Path, info: dict[str, Any] | None) -> list[str]:
    """PDFs in data_dir that are not in the index, or changed since they were indexed.

    With an index from other settings, every PDF needs to be indexed again."""
    pdfs = pdf_paths(Path(data_dir))
    if info is None or not is_compatible(info):
        return sorted(pdfs)
    indexed = info["papers"]
    return sorted(name for name, path in pdfs.items()
                  if name not in indexed or indexed[name]["file"] != file_signature(path))


def run_ingestion(data_dir: str | Path = "data", index_dir: str | Path = "index", full: bool = False,
                  chunk_size: int = CHUNK_SIZE, overlap: int = OVERLAP) -> dict[str, Any]:
    """Bring the index up to date with the PDFs in data_dir and save it. Returns a short summary.

    full=True rebuilds everything; otherwise only new and changed papers are read and embedded,
    and papers that are no longer in data_dir are removed from the index.
    """
    start = time.perf_counter()
    data_dir, index_dir = Path(data_dir), Path(index_dir)
    pdfs = pdf_paths(data_dir)
    if not pdfs:
        raise ValueError(f"No PDF files found in '{data_dir}'. Upload some PDFs first.")

    # Start from the saved index when it can be extended, otherwise from an empty one
    index: Any = None
    chunks: list[Chunk] = []
    papers: dict[str, Any] = {}
    if not full:
        try:
            index, chunks, info = load_store(index_dir)
            if is_compatible(info, chunk_size, overlap):
                papers = info["papers"]
            else:
                index, chunks = None, []
        except (FileNotFoundError, ValueError):
            index, chunks = None, []

    # Papers that were deleted from data_dir, or changed, leave the index first
    removed = [name for name in papers if name not in pdfs]
    changed = [name for name in papers if name in pdfs and papers[name]["file"] != file_signature(pdfs[name])]
    for name in removed + changed:
        if index is not None:
            index, chunks = remove_paper(index, chunks, name)
        del papers[name]

    to_index = sorted(name for name in pdfs if name not in papers)
    pages = load_pdfs(data_dir, names=to_index) if to_index else []
    new_chunks: list[Chunk] = chunk_pages(pages, chunk_size=chunk_size, overlap=overlap)
    add_abbreviations(new_chunks, pages)

    if not chunks and not new_chunks:
        # Never build an empty index (e.g. all PDFs are scanned images and OCR is not installed)
        raise ValueError("No text could be extracted from the PDFs (they may be scanned images). Nothing to index.")

    if new_chunks:
        vectors = normalize_vectors(embed_chunks(new_chunks))
        old = all_vectors(index) if index is not None else np.zeros((0, vectors.shape[1]), dtype=np.float32)
        index = build_index(np.vstack([old, vectors]))
    chunks = renumber(chunks + new_chunks)

    now = datetime.now().isoformat(timespec="seconds")
    for name in to_index:
        papers[name] = {
            "file": file_signature(pdfs[name]),
            "pages": sum(1 for page in pages if page["source"] == name),
            "chunks": sum(1 for chunk in new_chunks if chunk["source"] == name),
            "indexed_at": now,
        }
    save_store(index, chunks, index_dir, {**settings(chunk_size, overlap), "built_at": now, "papers": papers})

    return {
        "pdfs": len(pdfs),
        "indexed": to_index,
        "removed": removed,
        "pages": len(pages),
        "new_chunks": len(new_chunks),
        "chunks": len(chunks),
        "seconds": round(time.perf_counter() - start, 2),
    }
