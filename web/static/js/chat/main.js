// Assistant page: chat with your papers, in the style of ChatGPT, Claude and Gemini.
// Every chat belongs to one paper and is saved on the server in chats/.
// This file connects the buttons to the other modules and starts the page:
//   state.js    shared state and helpers       sidebar.js  papers and their chats
//   page.js     status-driven parts of the page  messages.js questions, answers, sources
//   chats.js    opening chats and asking        papers.js   upload, Build index, delete paper
//   menus.js    "..." menus, confirm box, rename and delete chat

import { ask, autoResize, loadChats, openChat, refreshStatus, startNewChat, stopAnswer } from "./chats.js";
import { closeMenu } from "./menus.js";
import { updateComposer } from "./page.js";
import { buildIndex, openFilePicker, uploadFiles } from "./papers.js";
import { closeSidebar } from "./sidebar.js";
import { $, BOOT_KEY, state } from "./state.js";

// ---------- Events ----------

// The send button sends, or stops the answer while it is being written
$("composer").addEventListener("submit", (event) => {
    event.preventDefault();
    if (state.stream) stopAnswer();
    else ask($("question").value);
});

$("question").addEventListener("keydown", (event) => {
    // Enter sends, Shift+Enter makes a new line
    if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
        event.preventDefault();
        ask($("question").value);
    }
});

$("question").addEventListener("input", () => {
    autoResize();
    updateComposer();
});

$("sidebar").addEventListener("scroll", closeMenu);
$("upload-button").addEventListener("click", openFilePicker);
$("upload-card").addEventListener("click", openFilePicker);
$("build-prompt-button").addEventListener("click", buildIndex);
$("attach-button").addEventListener("click", openFilePicker);
$("build-button").addEventListener("click", buildIndex);
$("file-input").addEventListener("change", (event) => uploadFiles(event.target.files));
$("menu-button").addEventListener("click", () => {
    const open = $("chat-layout").classList.toggle("sidebar-open");
    $("menu-button").setAttribute("aria-expanded", String(open));
});
$("sidebar-backdrop").addEventListener("click", closeSidebar);

document.addEventListener("mousedown", (event) => {
    const menu = document.querySelector(".menu");
    if (menu && !menu.contains(event.target) && !event.target.closest(".more-btn")) closeMenu();
});
document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
        closeMenu();
        closeSidebar();
    }
});
window.addEventListener("resize", closeMenu);

// Drag and drop PDFs anywhere on the chat area
let dragDepth = 0;
const hasFiles = (event) => Array.from(event.dataTransfer?.types || []).includes("Files");
$("chat-main").addEventListener("dragenter", (event) => {
    if (!hasFiles(event)) return;
    event.preventDefault();
    dragDepth += 1;
    $("drop-overlay").hidden = false;
});
$("chat-main").addEventListener("dragover", (event) => {
    if (hasFiles(event)) event.preventDefault();
});
$("chat-main").addEventListener("dragleave", () => {
    dragDepth = Math.max(0, dragDepth - 1);
    if (dragDepth === 0) $("drop-overlay").hidden = true;
});
$("chat-main").addEventListener("drop", (event) => {
    if (!hasFiles(event)) return;
    event.preventDefault();
    dragDepth = 0;
    $("drop-overlay").hidden = true;
    uploadFiles(event.dataTransfer.files);
});

// Back and forward buttons of the browser
window.addEventListener("popstate", () => {
    const params = new URLSearchParams(location.search);
    if (params.get("chat")) openChat(params.get("chat"), { push: false });
    else startNewChat(params.get("paper"), { push: false });
});

// Coming back to the tab (for example after starting Ollama) updates the status
window.addEventListener("focus", () => {
    if (!state.busy && !state.building) refreshStatus();
});

// ---------- Start ----------

// Was the dashboard just opened fresh? The server gets a new boot_id every time it starts
// (run_dashboard.bat restarts it). This tab remembers the boot_id it saw last.
function isFreshStart() {
    const boot = state.status && state.status.boot_id;
    let seen = null;
    try {
        seen = sessionStorage.getItem(BOOT_KEY);
        if (boot) sessionStorage.setItem(BOOT_KEY, boot);
    } catch {
        // storage can be blocked; then every load counts as fresh
    }
    return !boot || seen !== boot;
}

(async function init() {
    const params = new URLSearchParams(location.search);
    await refreshStatus();
    loadChats();
    // A fresh start always begins on the default page, even if the browser reopens the
    // address of an old chat. A reload while the dashboard is running keeps the chat.
    if (isFreshStart()) {
        history.replaceState({}, "", "/chat");
        startNewChat(null, { push: false });
    } else if (params.get("chat")) {
        await openChat(params.get("chat"), { push: false });
    } else {
        startNewChat(params.get("paper"), { push: false });
    }
})();
