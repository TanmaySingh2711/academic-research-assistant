// Sidebar: "All papers" holds every paper, and every paper holds its own chats in a dropdown.

import { openChat, startNewChat } from "./chats.js";
import { deleteChat, moreButton, startRename } from "./menus.js";
import { deletePaper } from "./papers.js";
import { $, ROOT_KEY, currentPaper, el, expandPaper, icon, isIndexed, paperName, plural, saveExpanded, state } from "./state.js";

// Papers for the sidebar. Papers that were removed from data/ by hand but still have chats
// are kept at the end, so those chats can still be read or deleted.
function sidebarPapers() {
    const s = state.status;
    const inData = s ? s.pdfs_in_data : [];
    const papers = inData.map((paper) => ({ key: paper, kind: isIndexed(paper) ? "indexed" : "new" }));
    for (const chat of state.chats) {
        if (chat.paper && !inData.includes(chat.paper) && !papers.some((p) => p.key === chat.paper)) {
            papers.push({ key: chat.paper, kind: "removed" });
        }
    }
    return papers;
}

// The sidebar is drawn again after every status update. The button that has the keyboard
// focus is found again by its data-focus key afterwards, so keyboard users do not lose their place.
export function renderPapers() {
    const list = $("paper-list");
    const focused = list.contains(document.activeElement) ? document.activeElement.dataset.focus : null;
    const s = state.status;
    $("paper-count").textContent = s ? s.pdfs_in_data.length : 0;

    const papers = sidebarPapers();
    if (!papers.length) {
        list.replaceChildren(el("li", "side-empty", s ? "No papers yet. Upload a PDF to start." : "Server offline."));
        return;
    }

    const open = state.expanded.has(ROOT_KEY);
    const root = el("li", "paper-node paper-root");
    root.classList.toggle("is-open", open);
    if (!state.listsLoaded) root.classList.add("animate-in");

    const toggle = el("button", "paper-toggle");
    toggle.type = "button";
    toggle.setAttribute("aria-expanded", String(open));
    toggle.dataset.focus = "root";
    const text = el("span", "side-item-text");
    text.append(el("span", "side-item-title", "All papers"), el("span", "side-item-sub", plural(papers.length, "paper")));
    toggle.append(icon("chevron", 14), icon("layers", 16), text);
    toggle.addEventListener("click", () => toggleExpand(ROOT_KEY, root, toggle));
    const row = el("div", "paper-row");
    row.append(toggle);

    const children = el("ul", "paper-chats-list paper-children");
    papers.forEach((paper, i) => children.append(paperNode(paper, i)));
    const dropdown = el("div", "paper-chats");
    dropdown.append(children);
    root.append(row, dropdown);

    list.replaceChildren(root);
    state.listsLoaded = true;
    markActiveChat();
    if (focused) list.querySelector(`[data-focus="${CSS.escape(focused)}"]`)?.focus({ preventScroll: true });
}

// One paper: a row that opens or closes its dropdown, "+" for a new chat, a menu, and its chats
function paperNode({ key, kind }, i) {
    const chats = state.chats.filter((chat) => chat.paper === key);
    const canChat = kind === "indexed";
    const canPick = kind !== "removed"; // a new paper can be picked too: its page offers Build index
    const name = paperName(key);
    const open = state.expanded.has(key);

    const node = el("li", "paper-node");
    node.classList.toggle("is-open", open);
    node.classList.toggle("is-current", currentPaper() === key);
    if (!state.listsLoaded) {
        node.classList.add("animate-in");
        node.style.animationDelay = `${(i + 1) * 40}ms`;
    }

    // Chevron: only opens or closes the dropdown with this paper's chats
    const chevron = el("button", "icon-btn paper-chevron");
    chevron.type = "button";
    chevron.title = open ? "Hide chats" : "Show chats";
    chevron.setAttribute("aria-label", `Show or hide the chats of ${name}`);
    chevron.setAttribute("aria-expanded", String(open));
    chevron.dataset.focus = `chevron:${key}`;
    chevron.append(icon("chevron", 14));
    chevron.addEventListener("click", () => toggleExpand(key, node, chevron));

    // The paper itself: click it to select it, like a project in ChatGPT, Claude or Gemini
    const pick = el("button", "paper-toggle paper-pick");
    pick.type = "button";
    pick.dataset.focus = `pick:${key}`;
    pick.title = canChat ? `Ask about ${name}` : canPick ? `${name}: open it to build the index` : key;
    if (currentPaper() === key) pick.setAttribute("aria-current", "true");
    const sub = kind === "new" ? "Not indexed yet" : kind === "removed" ? "Removed from data/" : plural(chats.length, "chat");
    const text = el("span", "side-item-text");
    text.append(el("span", "side-item-title", name), el("span", "side-item-sub", sub));
    pick.append(icon("file", 16), text);
    if (kind === "new") pick.append(el("span", "badge badge-warn", "New"));
    pick.addEventListener("click", () => selectPaper(key, kind, chats.length));

    const add = el("button", "icon-btn paper-add");
    add.type = "button";
    add.disabled = !canPick;
    add.dataset.focus = `add:${key}`;
    add.title = canPick ? `New chat about ${name}` : "This paper was removed";
    add.setAttribute("aria-label", add.title);
    add.append(icon("plus", 15));
    add.addEventListener("click", () => {
        startNewChat(key);
        closeSidebar();
    });

    const row = el("div", "paper-row");
    row.append(chevron, pick, add);
    if (kind !== "removed") {
        row.append(moreButton(`More options for ${name}`, `more:${key}`, () => [
            { label: "Delete paper", iconName: "trash", danger: true, action: () => deletePaper(key) },
        ]));
    }

    // Dropdown: the chats of this paper, newest first (the "+" in the row starts a new one)
    const items = el("ul", "paper-chats-list");
    for (const chat of chats) items.append(chatRow(chat));
    if (!chats.length) {
        items.append(el("li", "side-empty", canChat ? "No chats yet. Click + to start one."
            : "Build the index to chat about this paper."));
    }

    const dropdown = el("div", "paper-chats");
    dropdown.append(items);
    node.append(row, dropdown);
    return node;
}

// One chat inside a paper: open it, or use its menu to rename or delete it
function chatRow(chat) {
    const item = el("li", "chat-row");
    const button = el("button", "side-item chat-item");
    button.type = "button";
    button.dataset.chat = chat.id;
    button.dataset.focus = `chat:${chat.id}`;
    const text = el("span", "side-item-text");
    text.append(el("span", "side-item-title", chat.title), el("span", "side-item-sub", App.relativeTime(chat.updated_at)));
    button.append(icon("chat", 14), text);
    button.addEventListener("click", () => {
        openChat(chat.id);
        closeSidebar();
    });
    item.append(button, moreButton("More options for this chat", `chat-more:${chat.id}`, () => [
        { label: "Rename", iconName: "edit", action: () => startRename(chat, item) },
        { label: "Delete chat", iconName: "trash", danger: true, action: () => deleteChat(chat) },
    ]));
    return item;
}

// Open or close one dropdown (the CSS animates the height)
function toggleExpand(key, node, button) {
    const open = !state.expanded.has(key);
    if (open) state.expanded.add(key);
    else state.expanded.delete(key);
    saveExpanded();
    node.classList.toggle("is-open", open);
    button.setAttribute("aria-expanded", String(open));
    if (key !== ROOT_KEY) button.title = open ? "Hide chats" : "Show chats";
}

// Clicking a paper selects it: a new chat about it, with questions suggested for it.
// A new paper (not indexed yet) opens a page with a Build index button.
// If the paper already has chats, its dropdown opens so they are easy to find.
function selectPaper(key, kind, chatCount) {
    if (kind === "removed") {
        App.toast("This paper was removed.", "error");
        return;
    }
    if (chatCount) expandPaper(key);
    startNewChat(key);
    closeSidebar();
}

export function markActiveChat() {
    document.querySelectorAll("#paper-list .chat-item").forEach((button) => {
        const active = button.dataset.chat === state.chatId;
        button.classList.toggle("is-active", active);
        if (active) button.setAttribute("aria-current", "true");
        else button.removeAttribute("aria-current");
    });
}

export function closeSidebar() {
    $("chat-layout").classList.remove("sidebar-open");
}
