"""Check that the 4 dashboard pages and their static files are served (Flask test client)."""

import re
import sys
from pathlib import Path

from app import app

app.config["WARM_UP_MODEL"] = False  # these checks only need the pages, not the embedding model
client = app.test_client()
failures: list[str] = []


def check(ok, label):
    """Print OK/FAIL for one check and remember failures."""
    print(f"  {label:<52} {'OK' if ok else 'FAIL'}")
    if not ok:
        failures.append(label)


PAGES = {
    "/": ["Ask your research papers", "What this project is", "From PDF to answer"],
    "/chat": ["New chat", "Upload PDF", "Build index", "What would you like to know?", "Chats"],
    "/how-it-works": ["How it was built", "How it works inside", "User flow"],
}

removed = client.get("/history")
check(removed.status_code == 404, "/history was removed (chats are in the assistant's sidebar)")

static_files = set()
for url, texts in PAGES.items():
    response = client.get(url)
    html = response.get_data(as_text=True)
    print(f"GET {url:<14} -> {response.status_code}")
    check(response.status_code == 200, f"{url} returns 200")
    for text in texts:
        check(text in html, f"{url} contains {text!r}")
    # The page must not load anything from the internet (works offline)
    check("http://" not in html and "https://" not in html, f"{url} has no external links")
    # All JavaScript lives in static/js/ (no inline scripts)
    scripts = re.findall(r"<script([^>]*)>", html)
    check(bool(scripts) and all("src=" in attrs for attrs in scripts), f"{url} has no inline scripts")
    static_files.update(re.findall(r'(?:href|src)="(/static/[^"]+)"', html))

for path in sorted(static_files):
    response = client.get(path)
    check(response.status_code == 200, f"{path} returns 200")
    response.close()

# Long dashes and emoji make text look machine-written, so the UI must not use them
bad_characters = re.compile("[\u2013\u2014]|[\U0001F300-\U0001FAFF\u2600-\u27bf]")
ui_files = [*Path("templates").glob("*.html"), *Path("static").rglob("*.css"), *Path("static").rglob("*.js")]
found = [str(f) for f in ui_files if bad_characters.search(f.read_text(encoding="utf-8"))]
check(not found, f"no long dashes or emoji in {len(ui_files)} UI files")

if failures:
    sys.exit(f"{len(failures)} check(s) failed: {failures}")
