"""Check that the dashboard page and its static files are served (Flask test client)."""

import sys

from app import app

client = app.test_client()
failures: list[str] = []


def check(ok, label):
    """Print OK/FAIL for one check and remember failures."""
    print(f"  {label:<40} {'OK' if ok else 'FAIL'}")
    if not ok:
        failures.append(label)


page = client.get("/")
html = page.get_data(as_text=True)
print(f"GET /                  -> {page.status_code}")
check(page.status_code == 200, "GET / returns 200")

for title in ["Academic Research Assistant", "Upload papers", "Build index", "Ask a question", "Answer"]:
    check(title in html, f"page contains {title!r}")

for path in ["/static/style.css", "/static/app.js"]:
    response = client.get(path)
    print(f"GET {path:<18} -> {response.status_code} ({response.content_type}, {len(response.data)} bytes)")
    check(response.status_code == 200, f"{path} returns 200")
    response.close()

# The page must not load anything from the internet (works offline)
check("http://" not in html and "https://" not in html, "no external links")
# All JavaScript must live in static/app.js
scripts = html.split("<script")[1:]
check(len(scripts) == 1 and "src=" in scripts[0][:80], "no inline scripts")

if failures:
    sys.exit(f"{len(failures)} check(s) failed: {failures}")
