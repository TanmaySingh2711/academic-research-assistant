"""The dashboard pages and their files: served, offline, no inline scripts, no machine-looking text."""

import re
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parent.parent
PAGES = {
    "/": ["Ask your research papers", "What this project is", "From PDF to answer"],
    "/chat": ["Papers", "Upload PDF", "Build index", "What would you like to know?", "confirm-dialog"],
    "/how-it-works": ["How it was built", "How it works inside", "User flow"],
}


@pytest.fixture
def client(app_client: Any) -> Any:
    return app_client


@pytest.mark.parametrize("url", PAGES)
def test_page_is_served_offline(client: Any, url: str) -> None:
    response = client.get(url)
    html = response.get_data(as_text=True)
    assert response.status_code == 200
    for text in PAGES[url]:
        assert text in html
    assert "http://" not in html and "https://" not in html  # nothing is loaded from the internet
    scripts = re.findall(r"<script([^>]*)>", html)
    assert scripts and all("src=" in attrs for attrs in scripts)  # all JavaScript lives in static/js/


def test_every_linked_file_and_module_exists(client: Any) -> None:
    files = set()
    for url in PAGES:
        files.update(re.findall(r'(?:href|src)="(/static/[^"]+)"', client.get(url).get_data(as_text=True)))
    # ES modules import each other: follow those imports too
    for module in (ROOT / "static" / "js" / "chat").glob("*.js"):
        for target in re.findall(r'from "\./([\w-]+\.js)"', module.read_text(encoding="utf-8")):
            files.add(f"/static/js/chat/{target}")
    assert "/static/js/chat/main.js" in files and "/static/css/chat/composer.css" in files
    for path in sorted(files):
        response = client.get(path)
        assert response.status_code == 200, path
        response.close()


def test_history_page_was_removed(client: Any) -> None:
    assert client.get("/history").status_code == 404


def test_no_long_dashes_or_emoji_in_the_ui() -> None:
    # Long dashes and emoji make text look machine-written, so the UI must not use them
    bad = re.compile("[–—]|[\U0001F300-\U0001FAFF☀-➿]")
    files = [*(ROOT / "templates").glob("*.html"), *(ROOT / "static").rglob("*.css"), *(ROOT / "static").rglob("*.js")]
    assert len(files) > 15
    assert [str(f) for f in files if bad.search(f.read_text(encoding="utf-8"))] == []
