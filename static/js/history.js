// History page: show every saved chat, grouped by paper, with a search box.
// SECURITY: all text goes in with textContent (through App.el), never innerHTML.

const { el, icon, api, paperName } = App;

let allChats = [];
let indexedPapers = [];

// Put the matching part of the text in a <mark> (built safely, no innerHTML)
function highlight(text, query) {
    const span = el("span");
    const at = query ? text.toLowerCase().indexOf(query) : -1;
    if (at < 0) {
        span.textContent = text;
        return span;
    }
    span.append(document.createTextNode(text.slice(0, at)),
        el("mark", "", text.slice(at, at + query.length)),
        document.createTextNode(text.slice(at + query.length)));
    return span;
}

function chatRow(chat, query) {
    const link = el("a", "chat-row");
    link.href = `/chat?chat=${encodeURIComponent(chat.id)}`;
    const info = el("div", "chat-info");
    const title = el("strong");
    title.append(highlight(chat.title, query));
    const preview = el("p");
    preview.append(highlight(chat.preview || "No answer yet.", query));
    const questions = `${chat.questions} question${chat.questions === 1 ? "" : "s"}`;
    info.append(title, preview, el("small", "", `${questions}, ${App.formatTime(chat.updated_at)}`));
    const open = el("span", "chat-open");
    open.append(icon("arrow", 16));
    link.append(icon("chat", 16), info, open);
    const item = el("li");
    item.append(link);
    return item;
}

function render() {
    const query = document.getElementById("search").value.trim().toLowerCase();
    const matches = (chat) => !query
        || chat.title.toLowerCase().includes(query)
        || chat.preview.toLowerCase().includes(query)
        || paperName(chat.paper).toLowerCase().includes(query);
    const chats = allChats.filter(matches);

    // Group by paper. Indexed papers without chats get a group too, with a "New chat" button.
    const groups = new Map();
    if (!query) for (const paper of indexedPapers) groups.set(paper, []);
    for (const chat of chats) {
        const key = chat.paper || "";
        if (!groups.has(key)) groups.set(key, []);
        groups.get(key).push(chat);
    }

    const container = document.getElementById("groups");
    const cards = [];
    let i = 0;
    for (const [paper, list] of groups) {
        const card = el("section", "group card");
        card.style.animationDelay = `${i++ * 60}ms`;

        const head = el("div", "group-head");
        const box = el("div", "icon-box");
        box.append(icon(paper ? "file" : "layers", 18));
        const title = el("div", "group-title");
        const name = el("h2", "", paperName(paper || null));
        name.title = paper || "Chats that searched all papers";
        title.append(name, el("span", "", `${list.length} chat${list.length === 1 ? "" : "s"}`));
        const start = el("a", "btn btn-ghost btn-small");
        start.href = paper ? `/chat?paper=${encodeURIComponent(paper)}` : "/chat";
        start.title = `New chat about ${paperName(paper || null)}`;
        start.append(icon("plus", 14), document.createTextNode("New chat"));
        head.append(box, title, start);
        card.append(head);

        if (list.length) {
            const ul = el("ul", "chat-list");
            list.forEach((chat) => ul.append(chatRow(chat, query)));
            card.append(ul);
        } else {
            card.append(el("p", "group-empty", "No chats about this paper yet."));
        }
        cards.push(card);
    }

    container.replaceChildren(...cards);
    if (!cards.length && query) container.append(el("p", "group-empty", `No chats match "${query}".`));
    document.getElementById("empty").hidden = cards.length > 0 || Boolean(query);

    const summary = document.getElementById("summary");
    const papersWithChats = new Set(allChats.map((chat) => chat.paper || "")).size;
    const questionCount = allChats.reduce((sum, chat) => sum + chat.questions, 0);
    summary.replaceChildren(...[[allChats.length, "chats"], [questionCount, "questions"], [papersWithChats, "papers with chats"]]
        .map(([n, label]) => {
            const chip = el("span", "chip");
            chip.append(el("strong", "", n), document.createTextNode(label));
            return chip;
        }));
}

(async function init() {
    const [chats, status] = await Promise.all([api("/api/chats").catch((err) => {
        App.toast(err.message, "error");
        return [];
    }), App.getStatus()]);
    allChats = chats;
    indexedPapers = status ? status.indexed_papers : [];
    render();
    document.getElementById("search").addEventListener("input", render);
})();
