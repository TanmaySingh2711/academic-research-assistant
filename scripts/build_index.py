"""Build the index from the terminal: PDFs in data/ -> FAISS index in index/.

Like the Build index button, it only reads and embeds papers that are new or changed.

Usage (from the project folder):
  python scripts/build_index.py          index new and changed papers
  python scripts/build_index.py --full   read and embed every paper again
"""

import argparse
import sys
from pathlib import Path

# The project folder is one level above scripts/; this makes "import src" work
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.ingest import run_ingestion  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the index from the PDFs in data/.")
    parser.add_argument("--full", action="store_true", help="read and embed every paper again")
    args = parser.parse_args()

    summary = run_ingestion(ROOT / "data", ROOT / "index", full=args.full)

    print(f"PDFs in data/:  {summary['pdfs']}")
    print(f"Indexed now:    {', '.join(summary['indexed']) or 'nothing (everything was already indexed)'}")
    if summary["removed"]:
        print(f"Removed:        {', '.join(summary['removed'])}")
    print(f"Pages read:     {summary['pages']}")
    print(f"Chunks in index: {summary['chunks']} ({summary['new_chunks']} new)")
    print(f"Saved to index/ in {summary['seconds']} seconds")


if __name__ == "__main__":
    main()
