"""Chunking: split page text into small overlapping word-based chunks, keeping source + page."""


def split_into_chunks(text, chunk_size=100, overlap=20):
    """Split text into chunks of up to chunk_size words; neighbours share `overlap` words."""
    if chunk_size <= 0:
        raise ValueError(f"chunk_size must be > 0 (got {chunk_size})")
    if overlap < 0 or overlap >= chunk_size:
        raise ValueError(f"overlap must be >= 0 and < chunk_size (got overlap={overlap}, chunk_size={chunk_size})")

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


def chunk_pages(pages, chunk_size=100, overlap=20):
    """Chunk each page from load_pdfs separately and return a list of chunk dicts.

    Text is never joined across pages, so every chunk has one correct page number.
    """
    chunks = []
    chunk_id = 0  # unique across all chunks

    for page in pages:
        for text in split_into_chunks(page["text"], chunk_size, overlap):
            chunks.append({
                "chunk_id": chunk_id,
                "source": page["source"],
                "page": page["page"],
                "text": text,
                "word_count": len(text.split()),
            })
            chunk_id += 1

    return chunks
