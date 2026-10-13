"""Quick check that all Objective 1 dependencies are installed and Ollama is reachable."""

import importlib
from importlib.metadata import version, PackageNotFoundError

# import name -> pip package name
LIBRARIES = {
    "pdfplumber": "pdfplumber",
    "sentence_transformers": "sentence-transformers",
    "faiss": "faiss-cpu",
    "ollama": "ollama",
    "flask": "flask",
}

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

# Check that the local Ollama server is running
print("\nChecking Ollama server...")
try:
    import ollama

    ollama.list()  # simple call that needs the server
    print("  Ollama server: reachable")
except Exception as e:
    print(f"  Ollama server: NOT reachable ({e.__class__.__name__})")
