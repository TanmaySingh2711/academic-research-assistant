// Assistant page: chat with your papers, in the style of ChatGPT, Claude and Gemini.
// Every chat belongs to one paper (or to all papers) and is saved on the server in chats/.
// SECURITY: all text from the server goes in with textContent (through App.el), never innerHTML.

const $ = (id) => document.getElementById(id);
const { el, icon, api, paperName } = App;

// Remember which paper dropdowns are open, only in this browser (a small convenience)
const EXPANDED_KEY = "research-assistant.open-papers";

const state = {
    status: null, // last answer of /status (null = server offline)
    chatId: null, // open chat, or null for a new chat
    chatPaper: null, // paper of the open chat (null = all papers)
    selectedPaper: null, // paper chosen for a new chat (null = all papers)
    busy: false, // waiting for an answer
    building: false, // the index is being built
    newUploads: [], // papers uploaded in this visit that are not indexed yet
    listsLoaded: false, // the sidebar lists animate in only the first time
    chats: [], // summaries of all saved chats, newest first
    expanded: loadExpanded(), // papers whose dropdown is open ("" = All papers)
};

function loadExpanded() {
    try {
        return new Set(JSON.parse(localStorage.getItem(EXPANDED_KEY)) || []);
    } catch {
        return new Set();
    }
}

function saveExpanded() {
    try {
        localStorage.setItem(EXPANDED_KEY, JSON.stringify([...state.expanded]));
    } catch {
        // storage can be blocked (private window); the sidebar still works
    }
}

function expandPaper(paper) {
    state.expanded.add(paper || "");
    saveExpanded();
}

const isIndexed = (paper) => Boolean(state.status && state.status.indexed_papers.includes(paper));
const currentPaper = () => (state.chatId ? state.chatPaper : state.selectedPaper);

// ---------- Status, papers, paper selector and notices ----------

async function refreshStatus() {
    state.status = await App.getStatus(true);
    if (state.selectedPaper && !isIndexed(state.selectedPaper)) state.selectedPaper = null;
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

// The paper list, with "All papers" first. Papers that were removed from data/ but still
// have chats are kept at the end, so those chats can still be opened.
function sidebarPapers() {
    const s = state.status;
    const inData = s ? s.pdfs_in_data : [];
    const papers = [];
    const hasAllChats = state.chats.some((chat) => !chat.paper);
    if ((s && s.index_ready) || hasAllChats) papers.push({ key: "", kind: "all" });
    for (const paper of inData) papers.push({ key: paper, kind: isIndexed(paper) ? "indexed" : "new" });
    for (const chat of state.chats) {
        if (chat.paper && !inData.includes(chat.paper) && !papers.some((p) => p.key === chat.paper)) {
            papers.push({ key: chat.paper, kind: "removed" });
        }
    }
    return papers;
}

function renderPapers() {
    const list = $("paper-list");
    const s = state.status;
    $("paper-count").textContent = s ? s.pdfs_in_data.length : 0;

    const papers = sidebarPapers();
    if (!papers.length) {
        list.replaceChildren(el("li", "side-empty", s ? "No papers yet. Upload a PDF to start." : "Server offline."));
        return;
    }
    list.replaceChildren(...papers.map((paper, i) => paperNode(paper, i)));
    state.listsLoaded = true;
    markActiveChat();
}

// One paper: a row that opens or closes its dropdown, a "+" for a new chat, and its chats
function paperNode({ key, kind }, i) {
    const chats = state.chats.filter((chat) => (chat.paper || "") === key);
    const canChat = kind === "indexed" || (kind === "all" && Boolean(state.status && state.status.index_ready));
    const name = kind === "all" ? "All papers" : paperName(key);
    const open = state.expanded.has(key);

    const node = el("li", "paper-node");
    node.classList.toggle("is-open", open);
    node.classList.toggle("is-current", (currentPaper() || "") === key);
    if (!state.listsLoaded) {
        node.classList.add("animate-in");
        node.style.animationDelay = `${i * 40}ms`;
    }

    // Row: chevron, icon, name, and how many chats
    const toggle = el("button", "paper-toggle");
    toggle.type = "button";
    toggle.title = kind === "all" ? "Chats that search every paper" : key;
    toggle.setAttribute("aria-expanded", String(open));
    const sub = kind === "new" ? "Not indexed yet"
        : kind === "removed" ? "Removed from data/"
            : `${chats.length} chat${chats.length === 1 ? "" : "s"}`;
    const text = el("span", "side-item-text");
    text.append(el("span", "side-item-title", name), el("span", "side-item-sub", sub));
    toggle.append(icon("chevron", 14), icon(kind === "all" ? "layers" : "file", 16), text);
    if (kind === "new") toggle.append(el("span", "badge badge-warn", "New"));
    toggle.addEventListener("click", () => toggleExpand(key, node, toggle));

    const add = el("button", "icon-btn paper-add");
    add.type = "button";
    add.disabled = !canChat;
    add.title = canChat ? `New chat about ${name}` : "Build the index first to chat about this paper";
    add.setAttribute("aria-label", add.title);
    add.append(icon("plus", 15));
    add.addEventListener("click", () => {
        startNewChat(key || null);
        closeSidebar();
    });

    const row = el("div", "paper-row");
    row.append(toggle, add);

    // Dropdown: the chats of this paper, newest first, then "New chat"
    const items = el("ul", "paper-chats-list");
    for (const chat of chats) {
        const button = el("button", "side-item chat-item");
        button.type = "button";
        button.dataset.chat = chat.id;
        const chatText = el("span", "side-item-text");
        chatText.append(el("span", "side-item-title", chat.title),
            el("span", "side-item-sub", App.relativeTime(chat.updated_at)));
        button.append(icon("chat", 14), chatText);
        button.addEventListener("click", () => {
            openChat(chat.id);
            closeSidebar();
        });
        const item = el("li");
        item.append(button);
        items.append(item);
    }
    if (canChat) {
        const newChat = el("button", "side-item new-in-paper");
        newChat.type = "button";
        newChat.append(icon("plus", 14), el("span", "", "New chat"));
        newChat.addEventListener("click", () => {
            startNewChat(key || null);
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
    const options = [new Option("All papers", "")];
    for (const paper of s ? s.pdfs_in_data : []) {
        const option = new Option(isIndexed(paper) ? paperName(paper) : `${paperName(paper)} (not indexed yet)`, paper);
        option.disabled = !isIndexed(paper);
        options.push(option);
    }
    // An old chat can be about a paper that was removed from data/ later
    const paper = currentPaper();
    if (paper && !options.some((o) => o.value === paper)) options.push(new Option(paperName(paper), paper));

    select.replaceChildren(...options);
    select.value = paper || "";
    select.disabled = state.chatId !== null;
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
    $("empty-scope").textContent = !ready
        ? "Upload a paper and build the index to start."
        : paper
            ? `Asking about ${paperName(paper)}. Type your own question, or pick one below.`
            : "Asking about all your papers. Pick one paper at the top to see suggested questions about it.";
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
    $("send-button").disabled = !$("question").value.trim() || !ready || state.busy;
    $("question").placeholder = !ready
        ? "Upload a paper and build the index first..."
        : paper ? "Ask about this paper..." : "Ask about your papers...";
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

function startNewChat(paper = null, { push = true } = {}) {
    if (state.busy) return;
    state.chatId = null;
    state.chatPaper = null;
    state.selectedPaper = paper && isIndexed(paper) ? paper : null;
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
    if (!state.status || !state.status.index_ready) {
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

async function buildIndex() {
    if (state.building) return;
    state.building = true;
    $("build-button").disabled = true;
    $("build-progress").hidden = false;
    renderNotice();
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
        state.building = false;
        $("build-button").disabled = false;
        $("build-progress").hidden = true;
        renderNotice();
    }
}

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
    if (state.chatId) return;
    state.selectedPaper = event.target.value || null;
    history.replaceState({}, "", state.selectedPaper ? `/chat?paper=${encodeURIComponent(state.selectedPaper)}` : "/chat");
    renderPapers();
    renderEmptyState();
    updateComposer();
});

$("new-chat").addEventListener("click", () => {
    startNewChat(null);
    closeSidebar();
});
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
