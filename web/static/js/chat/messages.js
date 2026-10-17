// Messages in the chat: the user's questions, answers (written word by word while they stream
// in), errors, the sources under an answer, and safe formatting of the answer text.
// SECURITY: all text from the server goes in with textContent (through App.el), never innerHTML.

import { ask } from "./chats.js";
import { $, el, icon, paperName, plural } from "./state.js";

function avatar() {
    const box = el("div", "avatar");
    box.append(App.logo(18));
    return box;
}

export function addUserMessage(text) {
    const message = el("div", "msg msg-user");
    message.append(el("div", "bubble", text));
    $("thread").append(message);
    scrollToBottom(true);
    return message;
}

// m is a saved message (field "content") or a finished answer (field "answer")
export function addAssistantMessage(m) {
    const message = el("div", "msg msg-assistant");
    const body = el("div", "msg-body");
    message.append(avatar(), body);
    $("thread").append(message);
    fillAnswer(message, body, m);
}

function fillAnswer(message, body, m) {
    const text = m.answer ?? m.content;
    body.append(m.not_found ? notFoundBlock(text) : renderAnswer(text, (n) => openSource(message, n)));
    body.append(metaRow(text, m));
    if (!m.not_found && m.sources.length) body.append(sourcesBlock(m.sources));
    scrollToBottom();
}

// An answer that arrives piece by piece. First three dots with a short line about what is
// happening, then the words as the model writes them, then the formatted answer with sources.
export function addStreamingAnswer() {
    const message = el("div", "msg msg-assistant");
    const body = el("div", "msg-body");
    const row = el("div", "thinking");
    const dots = el("span", "dots");
    dots.append(el("i"), el("i"), el("i"));
    const status = el("span", "thinking-text", "Searching the paper...");
    row.append(dots, status);
    body.append(row);
    message.append(avatar(), body);
    const thread = $("thread");
    thread.append(message);
    // While the words stream in, screen readers wait and read the answer once it is complete
    thread.setAttribute("aria-busy", "true");
    const done = () => thread.removeAttribute("aria-busy");
    scrollToBottom(true);

    let box = null; // the plain text while it streams in
    let text = "";
    return {
        found(sources) {
            status.textContent = `Read ${plural(sources, "chunk")}. Writing the answer...`;
        },
        add(piece) {
            if (!box) {
                row.remove();
                box = el("div", "answer answer-typing");
                body.append(box);
            }
            text += piece;
            box.textContent = text;
            scrollToBottom();
        },
        finish(m) {
            row.remove();
            if (box) box.remove();
            fillAnswer(message, body, m);
            done();
        },
        // Stopped by the user: keep what was written so far
        stop() {
            row.remove();
            if (box) box.classList.replace("answer-typing", "answer-plain");
            if (!text) body.append(el("p", "answer-stopped", "Stopped before the answer started."));
            else body.append(el("div", "msg-meta", "Stopped"));
            done();
        },
        remove() {
            message.remove();
            done();
        },
    };
}

function notFoundBlock(text) {
    const box = el("div", "answer-notfound");
    const content = el("div");
    content.append(el("p", "", text),
        el("small", "", "Try other words, or start a new chat about a different paper."));
    box.append(icon("alert", 18), content);
    return box;
}

export function addErrorMessage(messageText, question, userMessage) {
    const message = el("div", "msg msg-assistant");
    const body = el("div", "msg-body");
    const box = el("div", "answer-error");
    box.setAttribute("role", "alert");
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
        el("span", "meta-item", plural(m.k, "chunk")),
        el("span", "meta-item", `${value(m.prompt_tokens)} tokens in`),
        el("span", "meta-item", `${value(m.answer_tokens)} out`),
        el("span", "meta-item", `${m.seconds} s`));
    if (m.stopped) row.append(el("span", "meta-item", "Stopped"));
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
            cite.setAttribute("aria-label", `Show source ${n}`);
            cite.addEventListener("click", () => onCite(n));
            parent.append(cite);
        }
    }
}

// Paragraphs, bullet lists and numbered lists
export function renderAnswer(text, onCite) {
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
        const bullet = line.match(/^[*\-•]\s+(.*)$/);
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

        // Relevance from the re-ranker: 0 (unrelated) to 1 (answers the question)
        const score = el("span", "score");
        score.title = "How well this chunk matches the question (0 to 1)";
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
        // A chunk from the middle of a section starts with "(Section: ...)" (see src/chunker.py);
        // show that as a small label above the text
        const section = source.text.match(/^\(Section: ([^)]*)\) /);
        card.append(summary);
        if (section) card.append(el("p", "chunk-section", `Section: ${section[1]}`));
        card.append(el("p", "chunk-text", section ? source.text.slice(section[0].length) : source.text));
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

// Keep the newest message in view, unless the user scrolled up to read
export function scrollToBottom(force = false) {
    const box = $("messages");
    const nearBottom = box.scrollHeight - box.scrollTop - box.clientHeight < 160;
    if (force || nearBottom) box.scrollTop = box.scrollHeight;
}
