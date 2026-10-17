#!/usr/bin/env bash
# One-time setup on macOS / Linux: venv, Python libraries, Ollama model, setup check.
# Usage: bash setup.sh

set -e
cd "$(dirname "$0")"

echo "============================================"
echo " Academic Research Assistant - setup"
echo "============================================"
echo

# ---- 1. Find Python 3.10, 3.11 or 3.12 ----
PY=""
for candidate in python3.12 python3.11 python3.10 python3 python; do
    if command -v "$candidate" >/dev/null 2>&1 &&
        "$candidate" -c 'import sys; sys.exit(0 if (3, 10) <= sys.version_info[:2] <= (3, 12) else 1)'; then
        PY="$candidate"
        break
    fi
done
if [ -z "$PY" ]; then
    echo "ERROR: Python 3.10, 3.11 or 3.12 was not found."
    echo "Install Python 3.12 from https://www.python.org/downloads/ and run this script again."
    exit 1
fi
echo "[1/4] Using Python: $PY ($("$PY" --version))"

# ---- 2. Create the virtual environment (only if it does not exist yet) ----
if [ -x venv/bin/python ]; then
    echo "[2/4] Virtual environment already exists: venv"
else
    echo "[2/4] Creating virtual environment: venv"
    "$PY" -m venv venv
fi

# ---- 3. Install the Python libraries ----
echo "[3/4] Installing Python libraries (the first time this downloads PyTorch and can take a while)..."
venv/bin/python -m pip install --upgrade pip
venv/bin/python -m pip install -r requirements.txt
# Put all Python cache files of this project in .cache/pycache (see scripts/configure_venv.py)
venv/bin/python scripts/configure_venv.py

# ---- 4. Ollama and the llama3.2:3b model ----
if command -v ollama >/dev/null 2>&1; then
    echo "[4/4] Downloading the model llama3.2:3b (about 2 GB, skipped if already downloaded)..."
    ollama pull llama3.2:3b
else
    echo
    echo "[4/4] Ollama is not installed."
    echo "Install it from https://ollama.com/download, then run: ollama pull llama3.2:3b"
    exit 1
fi

echo
echo "Checking the setup..."
if ! venv/bin/python scripts/verify_setup.py; then
    echo
    echo "ERROR: The setup check failed (a library or a search model is missing). Read the messages above."
    echo "On Linux, the OCR also needs the OpenGL library: sudo apt-get install libgl1"
    echo "Then run this script again."
    exit 1
fi

echo
echo "Setup complete. Start the app with:"
echo "  source venv/bin/activate"
echo "  python scripts/serve.py"
echo "Then open http://localhost:5000"
