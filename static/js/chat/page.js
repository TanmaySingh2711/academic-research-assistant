// The parts of the page that follow the status: the warning above the message box, the page
// before the first question, the Build index button, suggested questions and the message box.

import { ask } from "./chats.js";
import { $, api, currentPaper, el, icon, isIndexed, paperName, state } from "./state.js";

// A warning above the message box, only for real problems (server or Ollama)
export function renderNotice() {
    const box = $("notice");
    const s = state.status;
    let kind = "";
    let message = "";

    if (!s) {
        kind = "is-bad";
        message = "Cannot reach the server. Is app.py running?";
    } else if (!s.ollama_running) {
        kind = "is-warn";
        message = "Ollama is not running. Start the Ollama app to get answers.";
    }

    if (!message) {
        box.hidden = true;
        return;
    }
    box.className = `notice ${kind}`;
    box.replaceChildren(icon("alert", 16), el("span", "", message));
    box.hidden = false;
}

// The page before the first question. Three cases:
// no paper picked (default page: upload), a new paper (Build index), an indexed paper (suggestions)
export function renderEmptyState() {
    const empty = state.chatId === null && $("thread").children.length === 0;
    $("empty-state").hidden = !empty;
    if (!empty) return;

    const paper = currentPaper();
    const indexed = isIndexed(paper);
    const unreadable = Boolean(paper && state.status && (state.status.unreadable_papers || []).includes(paper));
    $("start-panel").hidden = Boolean(paper);
    $("build-prompt").hidden = !paper || indexed || unreadable;
    $("build-prompt-button").disabled = state.building;
    $("empty-scope").textContent = !paper
        ? "Upload a research paper, or pick one in the sidebar to start a chat."
        : indexed
            ? `Asking about ${paperName(paper)}. Type your own question, or pick one below.`
            : unreadable
                ? `No text could be read from ${paperName(paper)}. It may be an image-only PDF that OCR could not read.`
                : `${paperName(paper)} is not searchable yet. Build the index to ask about it.`;
    renderSuggestions(indexed ? paper : null);
}

// Build index follows the selected paper: active only when the selected paper is new
// (or changed since it was indexed). Greyed out on the default page (no paper selected)
// and when the selected paper is already indexed.
export function updateBuildButton() {
    const s = state.status;
    const waiting = s ? s.papers_to_index : [];
    const paper = currentPaper();
    const needed = Boolean(paper) && waiting.includes(paper);
    const button = $("build-button");
    button.disabled = state.building || !needed;
    button.title = state.building ? "Building the index..."
        : needed ? (isIndexed(paper) ? `Index ${paperName(paper)} again (it changed)` : `Index ${paperName(paper)}`)
            : paper ? "This paper is already indexed"
                : "Select a new paper to build its index";
}

// ---------- Suggested questions for the selected paper ----------

export const suggestionCache = new Map(); // paper -> questions, so each paper is asked for only once
let suggestionsShownFor = null; // paper whose questions are on screen now
let suggestionsLoadingFor = null; // paper whose questions are being written right now

// The local model reads the start of the paper and writes a few questions about it (see src/suggestions.py)
async function renderSuggestions(paper) {
    const box = $("suggest");
    const list = $("suggestions");
    // Suggestions are written by the local model, so skip them while Ollama is off
    if (!paper || (state.status && !state.status.ollama_running && !suggestionCache.has(paper))) {
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

// The send button turns into a Stop button while an answer is being written
export function updateComposer() {
    const paper = currentPaper();
    const canAsk = isIndexed(paper);
    const button = $("send-button");
    const streaming = Boolean(state.stream);
    button.classList.toggle("is-stop", streaming);
    button.replaceChildren(icon(streaming ? "stop" : "arrow-up", streaming ? 16 : 18));
    button.setAttribute("aria-label", streaming ? "Stop the answer" : "Send");
    button.title = streaming ? "Stop" : "Send";
    button.disabled = streaming ? false : !$("question").value.trim() || !canAsk || state.busy;
    $("question").placeholder = !paper
        ? "Pick a paper or upload one to ask a question..."
        : canAsk ? "Ask about this paper..." : "Build the index to ask about this paper...";
}
