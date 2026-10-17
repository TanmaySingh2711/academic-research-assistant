"""The Assistant page in a real browser (Edge or Chrome, the one already installed; nothing is downloaded).

Each test starts the real server on a free port, in temporary folders, with the fake LLM.
Skipped when Playwright or a browser is missing.
"""

import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

playwright_api = pytest.importorskip("playwright.sync_api")
expect = playwright_api.expect

import app as app_module  # noqa: E402
from tests.conftest import OTHER, PAPER, FakeLLM  # noqa: E402

pytestmark = pytest.mark.browser


@pytest.fixture(scope="session")
def browser() -> Iterator[Any]:
    with playwright_api.sync_playwright() as p:
        for channel in ("msedge", "chrome"):
            try:
                browser = p.chromium.launch(channel=channel)
                break
            except Exception:
                continue
        else:
            pytest.skip("Neither Edge nor Chrome is installed")
        yield browser
        browser.close()


@pytest.fixture
def server(project: dict[str, Path], fake_llm: FakeLLM, monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    """The real dashboard on a free port, serving the temporary folders."""
    from werkzeug.serving import make_server

    monkeypatch.setattr(app_module, "is_ollama_running", lambda: True)  # the fake LLM stands in for Ollama
    app = app_module.app
    old = {key: app.config[key] for key in ("PAPERS_DIR", "INDEX_DIR", "CHATS_DIR", "WARM_UP_MODEL")}
    app.config.update(PAPERS_DIR=project["papers"], INDEX_DIR=project["index"], CHATS_DIR=project["chats"],
                      WARM_UP_MODEL=False)
    app_module.load_index_into_memory()
    httpd = make_server("127.0.0.1", 0, app, threaded=True)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_port}"
    httpd.shutdown()
    app.config.update(old)
    app_module.load_index_into_memory()


@pytest.fixture
def page(browser: Any, server: str) -> Iterator[Any]:
    """A fresh browser tab on the Assistant page. Fails the test if the page logs an error."""
    context = browser.new_context(viewport={"width": 1280, "height": 860})
    tab = context.new_page()
    errors: list[str] = []
    tab.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)
    tab.on("pageerror", lambda error: errors.append(str(error)))
    tab.goto(f"{server}/chat")
    tab.bring_to_front()  # an active tab, so keyboard focus checks work
    expect(tab.locator(".paper-pick")).to_have_count(3)
    yield tab
    context.close()
    assert errors == []


def paper_row(page: Any, name: str) -> Any:
    return page.locator(".paper-children > .paper-node").filter(has=page.locator(".paper-pick", has_text=name))


def select(page: Any, paper: str) -> None:
    page.locator(".paper-pick", has_text=app_module_name(paper)).click()


def app_module_name(filename: str) -> str:
    """How the page shows a file name: no .pdf, underscores as spaces."""
    return filename.removesuffix(".pdf").replace("_", " ")


def ask(page: Any, question: str) -> None:
    page.fill("#question", question)
    page.keyboard.press("Enter")


def test_default_page(page: Any) -> None:
    expect(page.locator("#start-panel")).to_be_visible()
    expect(page.locator("#build-button")).to_be_disabled()
    expect(page.locator("#send-button")).to_be_disabled()
    expect(page.locator("#paper-count")).to_have_text("3")


def test_select_a_paper_and_ask(page: Any, fake_llm: FakeLLM) -> None:
    select(page, PAPER)
    expect(page.locator("#empty-scope")).to_contain_text("Asking about")
    expect(page.locator(".suggestion:not(.is-loading)")).to_have_count(3)
    expect(page.locator("#build-button")).to_be_disabled()

    ask(page, "What reward function does the agent use?")
    expect(page.locator(".msg-user .bubble")).to_have_text("What reward function does the agent use?")
    expect(page.locator(".source-card")).to_have_count(3)
    expect(page.locator(".msg-assistant .answer .cite")).to_have_count(1)
    expect(page.locator("#thread")).not_to_have_attribute("aria-busy", "true")  # read out once, when complete
    expect(page.get_by_role("main")).to_have_count(1)
    assert "?chat=" in page.url
    expect(paper_row(page, app_module_name(PAPER)).locator(".chat-item")).to_have_count(1)

    # Clicking the citation opens its source
    page.locator(".cite").first.click()
    expect(page.locator(".source-card[data-n='1']")).to_have_attribute("open", "")

    # A follow-up stays in the same chat
    ask(page, "How was it evaluated?")
    expect(page.locator(".msg-assistant .msg-meta")).to_have_count(2)
    expect(paper_row(page, app_module_name(PAPER)).locator(".chat-item")).to_have_count(1)
    assert "Earlier in this chat" in fake_llm.calls[-1][-1]["content"]


def test_stop_button(page: Any, fake_llm: FakeLLM) -> None:
    fake_llm.delay = 0.3  # slow words, so there is time to press Stop
    select(page, OTHER)
    ask(page, "How is the reward function built?")
    send = page.locator("#send-button")
    expect(send).to_have_class("send-btn is-stop")
    expect(page.locator(".answer-typing")).to_be_visible()
    expect(page.locator("#thread")).to_have_attribute("aria-busy", "true")  # screen readers wait meanwhile
    send.click()
    expect(page.locator(".msg-assistant .msg-meta")).to_have_text("Stopped")
    expect(send).not_to_have_class("send-btn is-stop")
    expect(page.locator("#thread")).not_to_have_attribute("aria-busy", "true")
    # The part that was written is saved, and the page continues in that chat
    expect(paper_row(page, app_module_name(OTHER)).locator(".chat-item")).to_have_count(1)


def test_new_paper_needs_build_index(page: Any, project: dict[str, Path]) -> None:
    new_pdf = project["papers"].parent / "My_New_Paper.pdf"
    new_pdf.write_bytes((project["papers"] / PAPER).read_bytes())
    page.set_input_files("#file-input", str(new_pdf))
    expect(page.locator(".paper-pick")).to_have_count(4)
    expect(page.locator("#build-prompt")).to_be_visible()  # the new paper's page opens by itself
    expect(page.locator("#build-button")).to_be_enabled()
    expect(page.locator("#send-button")).to_be_disabled()

    page.click("#build-prompt-button")
    expect(page.locator(".toast").last).to_contain_text("Indexed 1 paper")
    expect(page.locator("#build-button")).to_be_disabled()
    expect(page.locator("#empty-scope")).to_contain_text("Asking about")


def test_delete_chat_and_paper_at_once(page: Any) -> None:
    select(page, PAPER)
    ask(page, "What reward function does the agent use?")
    row = paper_row(page, app_module_name(PAPER))
    expect(row.locator(".chat-item")).to_have_count(1)

    row.locator(".chat-row").hover()  # the "..." button shows on hover, like in ChatGPT
    row.locator(".chat-row .more-btn").click()
    page.get_by_role("menuitem", name="Delete chat").click()
    page.click("#confirm-ok")
    expect(row.locator(".chat-item")).to_have_count(0, timeout=300)  # gone at once, like ChatGPT

    row.locator(".paper-row").hover()
    row.locator(".paper-row .more-btn").click()
    page.get_by_role("menuitem", name="Delete paper").click()
    started = time.perf_counter()
    page.click("#confirm-ok")
    expect(page.locator(".paper-pick")).to_have_count(2, timeout=300)
    assert time.perf_counter() - started < 1.0
    expect(page.locator("#start-panel")).to_be_visible()


def test_menu_works_with_the_keyboard(page: Any) -> None:
    # Tab to the paper: its "..." button appears (focus-within) and is the next Tab stop
    paper_row(page, app_module_name(PAPER)).locator(".paper-add").focus()
    page.keyboard.press("Tab")
    button = paper_row(page, app_module_name(PAPER)).locator(".paper-row .more-btn")
    expect(button).to_be_focused()
    page.keyboard.press("Enter")
    expect(button).to_have_attribute("aria-expanded", "true")
    expect(page.get_by_role("menuitem", name="Delete paper")).to_be_focused()
    page.keyboard.press("Escape")
    expect(page.locator(".menu")).to_have_count(0)
    expect(button).to_be_focused()


def test_small_screen_sidebar(page: Any) -> None:
    page.set_viewport_size({"width": 390, "height": 800})
    menu = page.locator("#menu-button")
    menu.click()
    expect(page.locator("#chat-layout")).to_have_class("chat-layout sidebar-open")
    expect(menu).to_have_attribute("aria-expanded", "true")
    page.keyboard.press("Escape")
    expect(page.locator("#chat-layout")).to_have_class("chat-layout")
    scroll_width = page.evaluate("document.documentElement.scrollWidth")
    assert scroll_width <= 390  # no sideways scrolling
