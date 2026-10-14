// Assistant page: chat with your papers, in the style of ChatGPT, Claude and Gemini.
// Every chat belongs to one paper and is saved on the server in chats/.
// SECURITY: all text from the server goes in with textContent (through App.el), never innerHTML.

const $ = (id) => document.getElementById(id);
const { el, icon, api, paperName } = App;

// Remember which dropdowns are open, only in this browser (a small convenience)
const EXPANDED_KEY = "research-assistant.open-papers";
const ROOT_KEY = "__all__"; // the "All papers" dropdown that holds every paper

const state = {
    status: null, // last answer of /status (null = server offline)
    chatId: null, // open chat, or null for a new chat
    chatPaper: null, // paper of the open chat
    selectedPaper: null, // paper chosen for a new chat
    busy: false, // waiting for an answer
    building: false, // the index is being built (Build index, or after deleting a paper)
    newUploads: [], // papers uploaded in this visit that are not indexed yet
    listsLoaded: false, // the sidebar animates in only the first time
    chats: [], // summaries of all saved chats, newest first
    expanded: loadExpanded(), // dropdowns that are open: ROOT_KEY and paper filenames
};

function loadExpanded() {
    try {
        const saved = localStorage.getItem(EXPANDED_KEY);
        return new Set(saved ? JSON.parse(saved) : [ROOT_KEY]); // "All papers" starts open
    } catch {
        return new Set([ROOT_KEY]);
    }
}

function saveExpanded() {
    try {
        localStorage.setItem(EXPANDED_KEY, JSON.stringify([...state.expanded]));
    } catch {
        // storage can be blocked (private window); the sidebar still works
    }
}

// Open the dropdown of a paper (and "All papers" around it), so its chats are visible
function expandPaper(paper) {
    state.expanded.add(ROOT_KEY);
    if (paper) state.expanded.add(paper);
    saveExpanded();
}

const isIndexed = (paper) => Boolean(state.status && state.status.indexed_papers.includes(paper));
const firstIndexedPaper = () => (state.status && state.status.indexed_papers[0]) || null;
const currentPaper = () => (state.chatId ? state.chatPaper : state.selectedPaper);

// ---------- Status, papers, paper selector and notices ----------

async function refreshStatus() {
    state.status = await App.getStatus(true);
    // A new chat always needs a paper: keep the chosen one, or take the first indexed paper
    if (!isIndexed(state.selectedPaper)) state.selectedPaper = firstIndexedPaper();
    renderPapers();
    renderPaperSelect();
    renderNotice();
    renderEmptyState();
    updateComposer();
}

function unindexedPapers() {
    const s = state.status;
    return s ? s.pdfs_in_data.filter((paper) => !s.indexed_papers.includes(paper)) : [];
}

// ---------- Sidebar: every paper with its chats in a dropdown ----------

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

// "All papers" is one dropdown that holds every paper; each paper holds its own chats
function renderPapers() {
    const list = $("paper-list");
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
    const text = el("span", "side-item-text");
    text.append(el("span", "side-item-title", "All papers"),
        el("span", "side-item-sub", `${papers.length} paper${papers.length === 1 ? "" : "s"}`));
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
}

// A small round button with three dots that opens a menu
function moreButton(label, items) {
    const button = el("button", "icon-btn more-btn");
    button.type = "button";
    button.title = label;
    button.setAttribute("aria-label", label);
    button.setAttribute("aria-haspopup", "menu");
    button.append(icon("more", 15));
    button.addEventListener("click", (event) => {
        event.stopPropagation();
        openMenu(button, items());
    });
    return button;
}

// One paper: a row that opens or closes its dropdown, "+" for a new chat, a menu, and its chats
function paperNode({ key, kind }, i) {
    const chats = state.chats.filter((chat) => chat.paper === key);
    const canChat = kind === "indexed";
    const name = paperName(key);
    const open = state.expanded.has(key);

    const node = el("li", "paper-node");
    node.classList.toggle("is-open", open);
    node.classList.toggle("is-current", currentPaper() === key);
    if (!state.listsLoaded) {
        node.classList.add("animate-in");
        node.style.animationDelay = `${(i + 1) * 40}ms`;
    }

    // Row: chevron, icon, name, and how many chats
    const toggle = el("button", "paper-toggle");
    toggle.type = "button";
    toggle.title = key;
    toggle.setAttribute("aria-expanded", String(open));
    const sub = kind === "new" ? "Not indexed yet"
        : kind === "removed" ? "Removed from data/"
            : `${chats.length} chat${chats.length === 1 ? "" : "s"}`;
    const text = el("span", "side-item-text");
    text.append(el("span", "side-item-title", name), el("span", "side-item-sub", sub));
    toggle.append(icon("chevron", 14), icon("file", 16), text);
    if (kind === "new") toggle.append(el("span", "badge badge-warn", "New"));
    toggle.addEventListener("click", () => toggleExpand(key, node, toggle));

    const add = el("button", "icon-btn paper-add");
    add.type = "button";
    add.disabled = !canChat;
    add.title = canChat ? `New chat about ${name}` : "Build the index first to chat about this paper";
    add.setAttribute("aria-label", add.title);
    add.append(icon("plus", 15));
    add.addEventListener("click", () => {
        startNewChat(key);
        closeSidebar();
    });

    const row = el("div", "paper-row");
    row.append(toggle, add);
    if (kind !== "removed") {
        row.append(moreButton(`More options for ${name}`, () => [
            { label: "Delete paper", iconName: "trash", danger: true, action: () => deletePaper(key) },
        ]));
    }

    // Dropdown: the chats of this paper, newest first, then "New chat"
    const items = el("ul", "paper-chats-list");
    for (const chat of chats) items.append(chatRow(chat));
    if (canChat) {
        const newChat = el("button", "side-item new-in-paper");
        newChat.type = "button";
        newChat.append(icon("plus", 14), el("span", "", "New chat"));
        newChat.addEventListener("click", () => {
            startNewChat(key);
            closeSidebar();
        });
        const item = el("li");
        item.append(newChat);
        items.append(item);
    } else if (!chats.length) {
        items.append(el("li", "side-empty", "Build the index to chat about this paper."));
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
    const text = el("span", "side-item-text");
    text.append(el("span", "side-item-title", chat.title),
        el("span", "side-item-sub", App.relativeTime(chat.updated_at)));
    button.append(icon("chat", 14), text);
    button.addEventListener("click", () => {
        openChat(chat.id);
        closeSidebar();
    });
    item.append(button, moreButton("More options for this chat", () => [
        { label: "Rename", iconName: "edit", action: () => startRename(chat, item) },
        { label: "Delete chat", iconName: "trash", danger: true, action: () => deleteChat(chat) },
    ]));
    return item;
}

// Open or close one dropdown (the CSS animates the height)
function toggleExpand(key, node, toggle) {
    const open = !state.expanded.has(key);
    if (open) state.expanded.add(key);
    else state.expanded.delete(key);
    saveExpanded();
    node.classList.toggle("is-open", open);
    toggle.setAttribute("aria-expanded", String(open));
}

// The "paper" dropdown at the top. An open chat keeps its paper, so the dropdown is locked.
function renderPaperSelect() {
    const select = $("paper-select");
    const s = state.status;
    const options = [];
    for (const paper of s ? s.pdfs_in_data : []) {
        const option = new Option(isIndexed(paper) ? paperName(paper) : `${paperName(paper)} (not indexed yet)`, paper);
        option.disabled = !isIndexed(paper);
        options.push(option);
    }
    // An old chat can be about a paper that was removed from data/ later
    const paper = currentPaper();
    if (paper && !options.some((o) => o.value === paper)) options.push(new Option(paperName(paper), paper));
    if (!options.length) {
        const empty = new Option("No papers yet", "");
        empty.disabled = true;
        options.push(empty);
    }

    select.replaceChildren(...options);
    select.value = paper || "";
    select.disabled = state.chatId !== null || !paper;
    $("paper-select-wrap").title = state.chatId
        ? "This chat is about this paper. Start a new chat to ask about another one."
        : "Which paper the assistant reads";
}

// One short message above the message box, for the most important problem
function renderNotice() {
    const box = $("notice");
    const s = state.status;
    let kind = "";
    let message = "";
    let action = null;

    if (!s) {
        kind = "is-bad";
        message = "Cannot reach the server. Is app.py running?";
    } else if (!s.ollama_running) {
        kind = "is-warn";
        message = "Ollama is not running. Start the Ollama app to get answers.";
    } else if (unindexedPapers().length) {
        const n = unindexedPapers().length;
        message = `${n} new paper${n === 1 ? " is" : "s are"} not searchable yet.`;
        action = ["Build index", buildIndex];
    } else if (!s.pdfs_in_data.length) {
        message = "Upload a PDF to get started.";
        action = ["Upload PDF", openFilePicker];
    }

    if (!message) {
        box.hidden = true;
        return;
    }
    box.className = `notice ${kind}`;
    const children = [icon(kind ? "alert" : "database", 16), el("span", "", message)];
    if (action) {
        const button = el("button", "btn btn-primary btn-small", action[0]);
        button.type = "button";
        button.disabled = state.building;
        button.addEventListener("click", action[1]);
        children.push(button);
    }
    box.replaceChildren(...children);
    box.hidden = false;
}

function renderEmptyState() {
    const empty = state.chatId === null && $("thread").children.length === 0;
    $("empty-state").hidden = !empty;
    if (!empty) return;

    const ready = Boolean(state.status && state.status.index_ready);
    $("setup-steps").hidden = ready;
    const paper = currentPaper();
    $("empty-scope").textContent = !ready || !paper
        ? "Upload a paper and build the index to start."
        : `Asking about ${paperName(paper)}. Type your own question, or pick one below.`;
    renderSuggestions(ready ? paper : null);
}

// ---------- Suggested questions for the selected paper ----------

const suggestionCache = new Map(); // paper -> questions, so each paper is asked for only once
let suggestionsShownFor = null; // paper whose questions are on screen now
let suggestionsLoadingFor = null; // paper whose questions are being written right now

// The local model reads the start of the paper and writes a few questions about it (see src/suggestions.py)
async function renderSuggestions(paper) {
    const box = $("suggest");
    const list = $("suggestions");
    if (!paper) {
        box.hidden = true;
        suggestionsShownFor = null;
        return;
    }
    if (paper === suggestionsShownFor || paper === suggestionsLoadingFor) return; // already there

    let questions = suggestionCache.get(paper);
    if (!questions) {
        // Grey placeholders while the model reads the paper (a few seconds the first time)
        box.hidden = false;
        suggestionsShownFor = null;
        suggestionsLoadingFor = paper;
        $("suggest-label").textContent = "Reading the paper to suggest questions...";
        list.replaceChildren(...Array.from({ length: 4 }, () => {
            const placeholder = el("div", "suggestion is-loading");
            placeholder.append(el("span", "skeleton"));
            return placeholder;
        }));
        try {
            questions = (await api(`/api/suggestions?paper=${encodeURIComponent(paper)}`)).questions;
            if (questions.length) suggestionCache.set(paper, questions);
        } catch {
            questions = []; // for example Ollama is not running: the user can still type a question
        }
        suggestionsLoadingFor = null;
        if (currentPaper() !== paper || $("empty-state").hidden) {
            renderEmptyState(); // the user switched paper or already asked something meanwhile
            return;
        }
    }

    if (!questions.length) {
        box.hidden = true;
        return;
    }
    $("suggest-label").textContent = "Suggested questions for this paper";
    list.replaceChildren(...questions.map((question, i) => {
        const button = el("button", "suggestion");
        button.type = "button";
        button.style.animationDelay = `${i * 70}ms`;
        button.append(icon("chat", 15), el("span", "", question));
        button.addEventListener("click", () => ask(question));
        return button;
    }));
    box.hidden = false;
    suggestionsShownFor = paper;
}

function updateComposer() {
    const ready = Boolean(state.status && state.status.index_ready);
    const paper = currentPaper();
    $("send-button").disabled = !$("question").value.trim() || !ready || !paper || state.busy;
    $("question").placeholder = !ready || !paper
        ? "Upload a paper and build the index first..."
        : "Ask about this paper...";
}

// ---------- Saved chats ----------

async function loadChats() {
    try {
        state.chats = await api("/api/chats"); // newest first
    } catch {
        // keep the last list when the server cannot be reached
    }
    renderPapers();
}

function markActiveChat() {
    document.querySelectorAll("#paper-list .chat-item").forEach((button) => {
        button.classList.toggle("is-active", button.dataset.chat === state.chatId);
    });
}

// ---------- Opening and starting chats ----------

// A new, empty chat about one paper (the first indexed paper if none is given)
function startNewChat(paper = null, { push = true } = {}) {
    if (state.busy) return;
    state.chatId = null;
    state.chatPaper = null;
    state.selectedPaper = isIndexed(paper) ? paper : isIndexed(state.selectedPaper) ? state.selectedPaper : firstIndexedPaper();
    expandPaper(state.selectedPaper); // show this paper's chats in the sidebar
    $("thread").replaceChildren();
    if (push) history.pushState({}, "", state.selectedPaper ? `/chat?paper=${encodeURIComponent(state.selectedPaper)}` : "/chat");
    renderPaperSelect();
    renderPapers();
    renderEmptyState();
    markActiveChat();
    updateComposer();
    $("question").focus();
}

async function openChat(chatId, { push = true } = {}) {
    if (state.busy) return;
    let chat;
    try {
        chat = await api(`/api/chats/${encodeURIComponent(chatId)}`);
    } catch (err) {
        App.toast(err.message, "error");
        startNewChat(null, { push });
        return;
    }
    state.chatId = chat.id;
    state.chatPaper = chat.paper;
    expandPaper(chat.paper);
    $("thread").replaceChildren();
    for (const message of chat.messages) {
        if (message.role === "user") addUserMessage(message.content);
        else addAssistantMessage(message);
    }
    if (push) history.pushState({}, "", `/chat?chat=${chat.id}`);
    renderPaperSelect();
    renderPapers();
    renderEmptyState();
    markActiveChat();
    updateComposer();
    scrollToBottom(true);
}

// ---------- Asking ----------

async function ask(question) {
    question = question.trim();
    if (!question || state.busy) return;
    if (!state.status || !state.status.index_ready || !currentPaper()) {
        App.toast("Upload a paper and build the index first.", "error");
        return;
    }

    state.busy = true;
    $("question").value = "";
    autoResize();
    updateComposer();
    $("empty-state").hidden = true;

    const userMessage = addUserMessage(question);
    const thinking = addThinking();
    try {
        const body = { question, k: Number($("k-select").value) };
        if (state.chatId) body.chat_id = state.chatId;
        else body.paper = state.selectedPaper;

        const data = await api("/ask", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
        });
        thinking.remove();

        const isNewChat = state.chatId === null;
        state.chatId = data.chat_id;
        state.chatPaper = data.paper;
        expandPaper(data.paper);
        if (isNewChat) history.pushState({}, "", `/chat?chat=${data.chat_id}`);
        renderPaperSelect();
        renderPapers();
        addAssistantMessage(data, { animate: true });
        loadChats();
    } catch (err) {
        thinking.remove();
        addErrorMessage(err.message, question, userMessage);
        if (err.status === 503 || err.status === undefined) refreshStatus();
    } finally {
        state.busy = false;
        updateComposer();
        $("question").focus();
    }
}

// ---------- Messages ----------

function avatar() {
    const box = el("div", "avatar");
    box.append(App.logo(18));
    return box;
}

function addUserMessage(text) {
    const message = el("div", "msg msg-user");
    message.append(el("div", "bubble", text));
    $("thread").append(message);
    scrollToBottom(true);
    return message;
}

// Three bouncing dots, with a short line about what the app is doing
function addThinking() {
    const message = el("div", "msg msg-assistant");
    const body = el("div", "msg-body");
    const row = el("div", "thinking");
    const dots = el("span", "dots");
    dots.append(el("i"), el("i"), el("i"));
    const text = el("span", "thinking-text", "Searching your papers...");
    row.append(dots, text);
    body.append(row);
    message.append(avatar(), body);
    $("thread").append(message);
    scrollToBottom(true);

    const steps = ["Searching your papers...", "Reading the best matching chunks...", "Writing the answer..."];
    let step = 0;
    const timer = setInterval(() => {
        step = Math.min(step + 1, steps.length - 1);
        text.textContent = steps[step];
    }, 1400);
    return {
        remove() {
            clearInterval(timer);
            message.remove();
        },
    };
}

// m is an /ask answer (field "answer") or a saved message (field "content")
function addAssistantMessage(m, { animate = false } = {}) {
    const text = m.answer ?? m.content;
    const message = el("div", "msg msg-assistant");
    const body = el("div", "msg-body");
    message.append(avatar(), body);
    $("thread").append(message);

    const finish = () => {
        body.append(m.not_found ? notFoundBlock(text) : renderAnswer(text, (n) => openSource(message, n)));
        body.append(metaRow(text, m));
        if (!m.not_found && m.sources.length) body.append(sourcesBlock(m.sources));
        scrollToBottom();
    };

    if (animate && !m.not_found && !App.reducedMotion) typeOut(body, text, finish);
    else finish();
}

// Show the text letter by letter (about 1.5 seconds in total), then the formatted answer
function typeOut(container, text, done) {
    const box = el("div", "answer answer-typing");
    container.append(box);
    const step = Math.max(2, Math.ceil(text.length / 90));
    let shown = 0;
    function frame() {
        shown = Math.min(text.length, shown + step);
        box.textContent = text.slice(0, shown);
        scrollToBottom();
        if (shown < text.length) {
            requestAnimationFrame(frame);
        } else {
            box.remove();
            done();
        }
    }
    requestAnimationFrame(frame);
}

function notFoundBlock(text) {
    const box = el("div", "answer-notfound");
    const content = el("div");
    content.append(el("p", "", text),
        el("small", "", "Try other words, or start a new chat about a different paper."));
    box.append(icon("alert", 18), content);
    return box;
}

function addErrorMessage(messageText, question, userMessage) {
    const message = el("div", "msg msg-assistant");
    const body = el("div", "msg-body");
    const box = el("div", "answer-error");
    const retry = el("button", "btn btn-ghost btn-small");
    retry.type = "button";
    retry.append(icon("refresh", 14), document.createTextNode("Try again"));
    retry.addEventListener("click", () => {
        userMessage.remove();
        message.remove();
        ask(question);
    });
    box.append(icon("alert", 18), el("span", "", messageText), retry);
    body.append(box);
    message.append(avatar(), body);
    $("thread").append(message);
    scrollToBottom(true);
}

// Copy button plus the numbers: chunks read, tokens and time
function metaRow(text, m) {
    const row = el("div", "msg-meta");
    const copy = el("button", "icon-btn");
    copy.type = "button";
    copy.title = "Copy answer";
    copy.setAttribute("aria-label", "Copy answer");
    copy.append(icon("copy", 15));
    copy.addEventListener("click", async () => {
        try {
            await navigator.clipboard.writeText(text);
            copy.replaceChildren(icon("check", 15));
            setTimeout(() => copy.replaceChildren(icon("copy", 15)), 1500);
        } catch {
            App.toast("Could not copy the answer.", "error");
        }
    });
    const value = (n) => (n === null || n === undefined ? "?" : n);
    row.append(copy,
        el("span", "meta-item", `${m.k} chunk${m.k === 1 ? "" : "s"}`),
        el("span", "meta-item", `${value(m.prompt_tokens)} tokens in`),
        el("span", "meta-item", `${value(m.answer_tokens)} out`),
        el("span", "meta-item", `${m.seconds} s`));
    return row;
}

// ---------- Formatting the answer (safe: builds elements, no innerHTML) ----------

// Splits a line into plain text, **bold** text and [Source N] citations
const INLINE_PARTS = /(\*\*[^*]+\*\*|\[Source[^\]]*\])/gi;

function appendInline(parent, line, onCite) {
    for (const part of line.split(INLINE_PARTS)) {
        if (!part) continue;
        if (part.length > 4 && part.startsWith("**") && part.endsWith("**")) {
            parent.append(el("strong", "", part.slice(2, -2)));
            continue;
        }
        const numbers = /^\[source/i.test(part) ? [...part.matchAll(/source\s*(\d+)/gi)].map((m) => m[1]) : [];
        if (!numbers.length) {
            parent.append(document.createTextNode(part));
            continue;
        }
        for (const n of numbers) {
            const cite = el("button", "cite", n);
            cite.type = "button";
            cite.title = `Show source ${n}`;
            cite.addEventListener("click", () => onCite(n));
            parent.append(cite);
        }
    }
}

// Paragraphs, bullet lists and numbered lists
function renderAnswer(text, onCite) {
    const root = el("div", "answer");
    let list = null;
    let paragraph = null;
    for (const raw of text.split("\n")) {
        const line = raw.trim();
        if (!line) {
            list = null;
            paragraph = null;
            continue;
        }
        const bullet = line.match(/^[*\-\u2022]\s+(.*)$/);
        const numbered = line.match(/^\d+[.)]\s+(.*)$/);
        if (bullet || numbered) {
            const tag = bullet ? "UL" : "OL";
            if (!list || list.tagName !== tag) {
                list = el(tag.toLowerCase());
                root.append(list);
            }
            const item = el("li");
            appendInline(item, (bullet || numbered)[1], onCite);
            list.append(item);
            paragraph = null;
            continue;
        }
        list = null;
        if (!paragraph) {
            paragraph = el("p");
            root.append(paragraph);
        } else {
            paragraph.append(el("br"));
        }
        appendInline(paragraph, line, onCite);
    }
    return root;
}

// ---------- Sources ----------

function sourcesBlock(sources) {
    const wrap = el("div", "sources");
    const head = el("div", "sources-head");
    const title = el("strong");
    title.append(icon("book", 14), document.createTextNode(`Sources (${sources.length})`));
    head.append(title, el("span", "", "Small local models can cite the wrong number. Open a source to check the exact text."));

    const list = el("div", "source-list");
    for (const source of sources) {
        const card = el("details", "source-card");
        card.dataset.n = source.source_number;

        const score = el("span", "score");
        const bar = el("span", "score-bar");
        const fill = el("i");
        fill.style.width = `${Math.max(0, Math.min(1, source.score)) * 100}%`;
        bar.append(fill);
        score.append(bar, document.createTextNode(Number(source.score).toFixed(2)));

        const name = el("span", "source-title", paperName(source.source));
        name.title = source.source;

        const summary = el("summary");
        summary.append(el("span", "source-num", source.source_number), name,
            el("span", "source-page", `page ${source.page}`), score, icon("chevron", 16));
        card.append(summary, el("p", "chunk-text", source.text));
        list.append(card);
    }
    wrap.append(head, list);
    return wrap;
}

// Clicking a citation opens that source card and makes it glow for a moment
function openSource(message, n) {
    const card = message.querySelector(`.source-card[data-n="${n}"]`);
    if (!card) {
        App.toast(`Source ${n} is not in the list. The model cited a number that does not exist.`, "error");
        return;
    }
    card.open = true;
    card.classList.remove("is-flash");
    void card.offsetWidth; // restart the glow
    card.classList.add("is-flash");
    card.scrollIntoView({ behavior: App.reducedMotion ? "auto" : "smooth", block: "nearest" });
    setTimeout(() => card.classList.remove("is-flash"), 1200);
}

// ---------- Upload and build index ----------

function openFilePicker() {
    $("file-input").click();
}

async function uploadFiles(fileList) {
    const files = [...fileList];
    const pdfs = files.filter((file) => file.name.toLowerCase().endsWith(".pdf"));
    if (pdfs.length < files.length) App.toast("Only PDF files can be uploaded.", "error");
    if (!pdfs.length) return;

    const totalMb = pdfs.reduce((sum, file) => sum + file.size, 0) / (1024 * 1024);
    if (totalMb > App.MAX_UPLOAD_MB) {
        App.toast(`These files are ${totalMb.toFixed(1)} MB together. The limit is ${App.MAX_UPLOAD_MB} MB per upload.`, "error");
        return;
    }

    const form = new FormData();
    pdfs.forEach((file) => form.append("files", file)); // field name "files", as app.py expects

    $("upload-button").disabled = true;
    $("attach-button").disabled = true;
    try {
        const data = await api("/upload", { method: "POST", body: form });
        for (const skipped of data.skipped) App.toast(`Skipped ${skipped.name}: ${skipped.reason}`, "error");
        if (data.saved.length) {
            state.newUploads = [...new Set([...state.newUploads, ...data.saved])];
            const n = data.saved.length;
            App.toast(`Uploaded ${n} paper${n === 1 ? "" : "s"}. Click Build index to make ${n === 1 ? "it" : "them"} searchable.`);
        }
        await refreshStatus();
    } catch (err) {
        App.toast(err.message, "error");
    } finally {
        $("upload-button").disabled = false;
        $("attach-button").disabled = false;
        $("file-input").value = "";
    }
}

// Show or hide the "working on the index" line in the sidebar
function setBuilding(on, text = "Building the index, about 15 seconds...") {
    state.building = on;
    $("build-button").disabled = on;
    $("build-progress-text").textContent = text;
    $("build-progress").hidden = !on;
    renderNotice();
}

async function buildIndex() {
    if (state.building) return;
    setBuilding(true);
    try {
        const data = await api("/process", { method: "POST" });
        const s = data.summary; // the numbers are nested under "summary"
        App.toast(`Index ready: ${s.pdfs} papers, ${s.chunks} chunks, in ${s.seconds} s.`);
        const uploaded = state.newUploads;
        state.newUploads = [];
        await refreshStatus();
        // Exactly one new paper: get a new chat ready for it
        if (uploaded.length === 1 && state.chatId === null && isIndexed(uploaded[0])) {
            startNewChat(uploaded[0]);
        }
    } catch (err) {
        App.toast(err.message, "error");
    } finally {
        setBuilding(false);
    }
}

// ---------- Menu, confirm box, rename and delete ----------

let menuElement = null; // the open menu, if any
let menuAnchor = null; // the "..." button that opened it

function closeMenu() {
    if (menuElement) menuElement.remove();
    if (menuAnchor) menuAnchor.setAttribute("aria-expanded", "false");
    menuElement = null;
    menuAnchor = null;
}

// A small menu next to a "..." button. items: [{label, iconName, danger, action}]
function openMenu(anchor, items) {
    const sameButton = menuAnchor === anchor;
    closeMenu();
    if (sameButton) return; // a second click on the same button closes the menu

    const menu = el("div", "menu");
    menu.setAttribute("role", "menu");
    for (const item of items) {
        const button = el("button", `menu-item${item.danger ? " is-danger" : ""}`);
        button.type = "button";
        button.setAttribute("role", "menuitem");
        button.append(icon(item.iconName, 15), el("span", "", item.label));
        button.addEventListener("click", () => {
            closeMenu();
            item.action();
        });
        menu.append(button);
    }
    document.body.append(menu);

    // Place it to the right of the button, and keep it inside the window
    const box = anchor.getBoundingClientRect();
    menu.style.left = `${Math.max(8, Math.min(box.right + 6, window.innerWidth - menu.offsetWidth - 8))}px`;
    menu.style.top = `${Math.max(8, Math.min(box.top, window.innerHeight - menu.offsetHeight - 8))}px`;
    menuElement = menu;
    menuAnchor = anchor;
    anchor.setAttribute("aria-expanded", "true");
    menu.querySelector("button").focus();
}

// "Are you sure?" box. Resolves to true when the user clicks the red button.
function confirmDialog({ title, message, confirmLabel }) {
    const dialog = $("confirm-dialog");
    $("confirm-title").textContent = title;
    $("confirm-message").textContent = message;
    $("confirm-ok").textContent = confirmLabel;
    dialog.returnValue = "";
    dialog.showModal();
    return new Promise((resolve) => {
        dialog.addEventListener("close", () => resolve(dialog.returnValue === "ok"), { once: true });
    });
}

// Rename a chat right in the sidebar: Enter saves, Esc cancels
function startRename(chat, item) {
    const input = el("input", "rename-input");
    input.value = chat.title;
    input.maxLength = 60;
    input.setAttribute("aria-label", "Chat name");
    item.classList.add("is-renaming");
    item.append(input);
    input.focus();
    input.select();

    let finished = false;
    const finish = async (save) => {
        if (finished) return;
        finished = true;
        const title = input.value.trim();
        if (save && title && title !== chat.title) {
            try {
                await api(`/api/chats/${encodeURIComponent(chat.id)}`, {
                    method: "PATCH",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ title }),
                });
                App.toast("Chat renamed.");
            } catch (err) {
                App.toast(err.message, "error");
            }
        }
        await loadChats(); // draws the sidebar again with the new name
    };
    input.addEventListener("keydown", (event) => {
        if (event.key === "Enter") {
            event.preventDefault();
            finish(true);
        } else if (event.key === "Escape") {
            event.preventDefault();
            finish(false);
        }
    });
    input.addEventListener("blur", () => finish(true));
}

async function deleteChat(chat) {
    const ok = await confirmDialog({
        title: "Delete this chat?",
        message: `The chat "${chat.title}" will be deleted. This cannot be undone.`,
        confirmLabel: "Delete chat",
    });
    if (!ok) return;
    try {
        await api(`/api/chats/${encodeURIComponent(chat.id)}`, { method: "DELETE" });
        App.toast("Chat deleted.");
    } catch (err) {
        App.toast(err.message, "error");
        return;
    }
    if (state.chatId === chat.id) startNewChat(chat.paper);
    await loadChats();
}

// Deletes the PDF and all its chats on the server, which then rebuilds the index without it
async function deletePaper(paper) {
    if (state.building || state.busy) {
        App.toast("Please wait until the current task is finished.", "error");
        return;
    }
    const n = state.chats.filter((chat) => chat.paper === paper).length;
    const ok = await confirmDialog({
        title: "Delete this paper?",
        message: `${paperName(paper)} and its ${n} chat${n === 1 ? "" : "s"} will be deleted, `
            + "and the index is rebuilt without it. This cannot be undone.",
        confirmLabel: "Delete paper",
    });
    if (!ok) return;

    const wasOpen = currentPaper() === paper;
    setBuilding(true, "Deleting the paper and updating the index...");
    try {
        const data = await api(`/api/papers/${encodeURIComponent(paper)}`, { method: "DELETE" });
        App.toast(data.message);
        suggestionCache.delete(paper);
        state.expanded.delete(paper);
        saveExpanded();
        state.newUploads = state.newUploads.filter((p) => p !== paper);
        await refreshStatus();
        await loadChats();
        if (wasOpen) startNewChat(null);
    } catch (err) {
        App.toast(err.message, "error");
    } finally {
        setBuilding(false);
    }
}

document.addEventListener("mousedown", (event) => {
    if (menuElement && !menuElement.contains(event.target) && !menuAnchor.contains(event.target)) closeMenu();
});
document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") closeMenu();
});
window.addEventListener("resize", closeMenu);

// ---------- Small helpers ----------

// Keep the newest message in view, unless the user scrolled up to read
function scrollToBottom(force = false) {
    const box = $("messages");
    const nearBottom = box.scrollHeight - box.scrollTop - box.clientHeight < 160;
    if (force || nearBottom) box.scrollTop = box.scrollHeight;
}

// The message box grows with the text, up to 200 px
function autoResize() {
    const textarea = $("question");
    textarea.style.height = "auto";
    textarea.style.height = `${Math.min(textarea.scrollHeight, 200)}px`;
}

function closeSidebar() {
    $("chat-layout").classList.remove("sidebar-open");
}

// ---------- Events ----------

$("composer").addEventListener("submit", (event) => {
    event.preventDefault();
    ask($("question").value);
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

$("paper-select").addEventListener("change", (event) => {
    if (state.chatId || !event.target.value) return;
    state.selectedPaper = event.target.value;
    expandPaper(state.selectedPaper);
    history.replaceState({}, "", `/chat?paper=${encodeURIComponent(state.selectedPaper)}`);
    renderPapers();
    renderEmptyState();
    updateComposer();
});

$("sidebar").addEventListener("scroll", closeMenu);
$("upload-button").addEventListener("click", openFilePicker);
$("attach-button").addEventListener("click", openFilePicker);
$("build-button").addEventListener("click", buildIndex);
$("file-input").addEventListener("change", (event) => uploadFiles(event.target.files));
$("menu-button").addEventListener("click", () => $("chat-layout").classList.toggle("sidebar-open"));
$("sidebar-backdrop").addEventListener("click", closeSidebar);

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

(async function init() {
    const params = new URLSearchParams(location.search);
    await refreshStatus();
    loadChats();
    if (params.get("chat")) await openChat(params.get("chat"), { push: false });
    else startNewChat(params.get("paper"), { push: false });
})();
