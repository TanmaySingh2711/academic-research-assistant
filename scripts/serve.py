"""Run the dashboard on http://localhost:5000 (started by run_dashboard.bat / run_dashboard.sh).

"localhost" can mean 127.0.0.1 (IPv4) or ::1 (IPv6), and browsers on Windows usually try
::1 first. If the server only listened on 127.0.0.1, every new connection would first wait
for ::1 to fail. So the server listens on both, and http://localhost:5000 opens at once.
Both addresses are only reachable from this computer.

The port is opened before the app is loaded (loading takes about half a second). The
launchers open the browser as soon as the port is open, so the browser starts while the app
loads; its first request simply waits in the port's queue until the app is ready.

Usage: python scripts/serve.py
"""

import os
import socket
import sys
import threading
from pathlib import Path

PORT = 5000


def open_port(family: socket.AddressFamily, host: str) -> socket.socket:
    sock = socket.socket(family, socket.SOCK_STREAM)
    if os.name != "nt":
        # Allows a quick restart after the server stopped. Not on Windows: there it would let
        # two programs use the same port at once.
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((host, PORT))
    sock.listen(128)
    return sock


def main() -> None:
    try:
        sockets = [("127.0.0.1", open_port(socket.AF_INET, "127.0.0.1"))]
    except OSError as e:
        sys.exit(f"Port {PORT} is already in use ({e}). Close the other program and start again.")
    try:
        sockets.append(("::1", open_port(socket.AF_INET6, "::1")))
    except OSError:
        pass  # IPv6 is turned off on this computer: 127.0.0.1 alone is enough

    # Now load the app (the slow part) while the port already accepts connections
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # makes "import app" work
    from werkzeug.serving import make_server

    from app import app

    servers = [make_server(host, PORT, app, threaded=True, fd=sock.fileno()) for host, sock in sockets]
    for _, sock in sockets:
        sock.close()  # the servers use their own copy of each socket

    print(f"Dashboard running on http://localhost:{PORT}")
    for server in servers[1:]:
        threading.Thread(target=server.serve_forever, daemon=True).start()
    servers[0].serve_forever()


if __name__ == "__main__":
    main()
