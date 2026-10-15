"""Check the setup: libraries installed, search models downloaded, Ollama and llama3.2:3b ready.

The two search models (embedding and re-ranker) are downloaded here the first time, so the
app itself never has to wait for a download and works offline afterwards.

Usage (setup.bat / setup.sh run this for you): python scripts/verify_setup.py
Exit code 1 if a library or a search model is missing (Ollama problems are only reported).
"""

import importlib
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

# The project folder is one level above scripts/; this makes "import src" work
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# import name -> pip package name
LIBRARIES = {
    "pdfplumber": "pdfplumber",
    "sentence_transformers": "sentence-transformers",
    "faiss": "faiss-cpu",
    "ollama": "ollama",
    "flask": "flask",
    "rapidocr_onnxruntime": "rapidocr-onnxruntime",
}


def main() -> int:
    problems = 0
    print("Checking libraries...")
    for import_name, package_name in LIBRARIES.items():
        try:
            importlib.import_module(import_name)
            try:
                ver = version(package_name)
            except PackageNotFoundError:
                ver = "OK"
            print(f"  {import_name:<22} {ver}")
        except ImportError as e:
            print(f"  {import_name:<22} NOT INSTALLED ({e})")
            problems += 1
    if problems:
        return 1

    print("\nChecking the search models (downloaded once, about 180 MB)...")
    from src.embedder import MODEL_NAME, load_model
    from src.reranker import MODEL_NAME as RERANKER_NAME
    from src.reranker import load_reranker

    for name, load in ((MODEL_NAME, load_model), (RERANKER_NAME, load_reranker)):
        try:
            load()
            print(f"  {name:<40} ready")
        except Exception as e:
            print(f"  {name:<40} NOT AVAILABLE ({e.__class__.__name__}: {e})")
            problems += 1

    print("\nChecking Ollama...")
    try:
        import ollama

        from src.generator import LLM_MODEL

        names = [model.model for model in ollama.list().models]
        print("  Ollama server:  reachable")
        found = any(name and name.split(":latest")[0] == LLM_MODEL for name in names)
        print(f"  {LLM_MODEL}:    {'downloaded' if found else f'NOT downloaded (run: ollama pull {LLM_MODEL})'}")
    except Exception as e:
        print(f"  Ollama server:  NOT reachable ({e.__class__.__name__}). Start the Ollama app to get answers.")

    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
