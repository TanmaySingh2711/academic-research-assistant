#!/usr/bin/env bash
# Start the dashboard on macOS / Linux (on Windows, double-click run_dashboard.bat instead).
# Usage: bash run_dashboard.sh
#
# It starts Ollama if it is not running, starts the server on http://localhost:5000, opens the
# browser as soon as the server answers, and one press of Esc stops everything again
# (Ctrl+C does nothing, so the dashboard is never stopped by accident).

cd "$(dirname "$0")" || exit 1
ROOT="$(pwd)"
PORT=5000
URL="http://localhost:$PORT"
PY="$ROOT/venv/bin/python"
[ -x "$PY" ] || PY="$ROOT/venv/Scripts/python.exe"  # Git Bash on Windows
SERVER="$ROOT/scripts/serve.py"  # full path, so this project's server can be recognised later

echo "=============================================="
echo " Academic Research Assistant"
echo "=============================================="

if [ ! -x "$PY" ]; then
    echo "The virtual environment was not found. Run setup.sh first."
    exit 1
fi

SERVER_PID=""
OLLAMA_PID=""
WARM_PID=""

# The keyboard: keys are read one by one without being shown, and Ctrl+C (and Ctrl+Z) only
# send a character instead of stopping the script. The old settings come back at the end.
OLD_TERMINAL=""
if [ -t 0 ]; then
    OLD_TERMINAL=$(stty -g)
    stty -echo -icanon -isig min 0 time 1  # a read waits at most 0.1 s
fi

# Whatever ends the script (Esc, closing the terminal, an error), stop what it started
stop_everything() {
    [ -n "$SERVER_PID" ] && kill "$SERVER_PID" 2>/dev/null
    [ -n "$OLLAMA_PID" ] && kill "$OLLAMA_PID" 2>/dev/null
    [ -n "$WARM_PID" ] && kill "$WARM_PID" 2>/dev/null
    wait 2>/dev/null
    [ -n "$OLD_TERMINAL" ] && stty "$OLD_TERMINAL"
}
trap stop_everything EXIT
trap '' INT  # Ctrl+C never stops the dashboard: only Esc does
trap 'echo; echo "Stopping the server..."; exit 0' TERM HUP

# True if a program on this computer listens on the port (an instant check)
port_open() {
    (exec 3<>"/dev/tcp/127.0.0.1/$1") 2>/dev/null
}

# ---------- 1. Make sure port 5000 is free ----------
if port_open "$PORT"; then
    old=""
    if command -v lsof >/dev/null 2>&1; then
        for pid in $(lsof -ti "tcp:$PORT" -sTCP:LISTEN 2>/dev/null); do
            # Only an older run of THIS dashboard is stopped, never another program
            if ps -o command= -p "$pid" 2>/dev/null | grep -qF "$SERVER"; then old="$pid"; fi
        done
    fi
    if [ -n "$old" ]; then
        echo "Restarting the dashboard that was already running..."
        kill "$old" 2>/dev/null
        for _ in $(seq 1 50); do port_open "$PORT" || break; sleep 0.1; done
    fi
    if port_open "$PORT"; then
        echo "Port $PORT is used by another program. Close it, then start the dashboard again."
        exit 1
    fi
fi

# ---------- 2. Start Ollama if it is not running ----------
if ! port_open 11434; then
    if command -v ollama >/dev/null 2>&1; then
        echo "Starting Ollama..."
        ollama serve >/dev/null 2>&1 &
        OLLAMA_PID=$!
    else
        echo "Ollama was not found. You can upload papers, but answers need Ollama (run setup.sh)."
    fi
fi

# ---------- 3. Start the server right away ----------
# Hugging Face offline mode when both search models are already downloaded: no online checks
export PYTHONIOENCODING=utf-8
HF_HUB="${HF_HOME:-$HOME/.cache/huggingface}/hub"
if [ -d "$HF_HUB/models--sentence-transformers--all-MiniLM-L6-v2" ] &&
    [ -d "$HF_HUB/models--cross-encoder--ms-marco-MiniLM-L6-v2" ]; then
    export HF_HUB_OFFLINE=1
fi

echo "Starting the server..."
echo "Dashboard: $URL"
echo "Press Esc to stop the server."
echo
"$PY" "$SERVER" &
SERVER_PID=$!

open_browser() {
    [ -n "$NO_BROWSER" ] && return  # set NO_BROWSER=1 to start without opening a browser (used by CI)
    if [ "$(uname)" = "Darwin" ]; then
        open "$URL"
    elif command -v xdg-open >/dev/null 2>&1; then
        xdg-open "$URL" >/dev/null 2>&1 &
    else
        echo "Open $URL in your browser."
    fi
}

# ---------- 4. Wait: open the browser when ready, warm up the LLM, stop on Esc ----------
opened=""
while kill -0 "$SERVER_PID" 2>/dev/null; do
    if [ -z "$opened" ] && port_open "$PORT"; then
        open_browser
        opened=1
    fi

    # Load llama3.2 into memory in the background, so the first answer is fast
    if [ -z "$WARM_PID" ] && port_open 11434 && command -v curl >/dev/null 2>&1; then
        curl -s -o /dev/null -m 600 -d '{"model": "llama3.2:3b"}' http://127.0.0.1:11434/api/generate &
        WARM_PID=$!
    fi

    if [ -z "$opened" ] || [ -z "$OLD_TERMINAL" ]; then
        sleep 0.05  # checking often until the dashboard is open (or there is no keyboard)
        continue
    fi
    # Everything typed since the last check, read at once. Esc alone is one byte; an arrow key
    # sends Esc followed by more bytes, so it does not count as Esc.
    keys=$(dd bs=16 count=1 2>/dev/null)
    if [ "$keys" = $'\e' ]; then
        echo
        echo "Stopping the server..."
        exit 0
    fi
done

echo
echo "The server stopped unexpectedly. Read the messages above."
exit 1
