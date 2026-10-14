"""Run the dashboard on http://localhost:5000 (started by run_dashboard.bat).

"localhost" can mean 127.0.0.1 (IPv4) or ::1 (IPv6), and browsers on Windows usually try
::1 first. If the server only listened on 127.0.0.1, every new connection would first wait
for ::1 to fail. So the server listens on both, and http://localhost:5000 opens at once.
Both addresses are only reachable from this computer.

Usage: python scripts/serve.py
"""

import sys
import threading
from pathlib import Path

from werkzeug.serving import make_server

# Make "import app" work when this file is started from the project folder
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import app  # noqa: E402

PORT = 5000


def main():
    servers = [make_server("127.0.0.1", PORT, app, threaded=True)]
    try:
        servers.append(make_server("::1", PORT, app, threaded=True))
    except OSError:
        pass  # IPv6 is turned off on this computer: 127.0.0.1 alone is enough

    print(f"Dashboard running on http://localhost:{PORT}")
    for server in servers[1:]:
        threading.Thread(target=server.serve_forever, daemon=True).start()
    servers[0].serve_forever()


if __name__ == "__main__":
    main()
