// Chats: the status, the saved chats, starting and opening a chat, and asking a question.
// An answer streams in word by word (the server sends one JSON event per line) and can be stopped.

import { addAssistantMessage, addErrorMessage, addStreamingAnswer, addUserMessage, scrollToBottom } from "./messages.js";
import { renderEmptyState, renderNotice, updateBuildButton, updateComposer } from "./page.js";
import { markActiveChat, renderPapers } from "./sidebar.js";
import { $, api, currentPaper, expandPaper, inData, isIndexed, state } from "./state.js";

export async function refreshStatus() {
    state.status = await App.getStatus(true);
    // A paper that was deleted cannot stay selected
    if (state.status && state.selectedPaper && !inData(state.selectedPaper)) state.selectedPaper = null;
    renderPapers();
    renderNotice();
    updateBuildButton();
    renderEmptyState();
    updateComposer();
}

export async function loadChats() {
    try {
        state.chats = await api("/api/chats"); // newest first
    } catch {
        // keep the last list when the server cannot be reached
    }
    renderPapers();
}

// A new, empty chat about one paper. Without a paper: the default page (upload or pick a paper).
export function startNewChat(paper = null, { push = true } = {}) {
    if (state.busy) return;
    state.chatId = null;
    state.chatPaper = null;
    state.selectedPaper = inData(paper) ? paper : null;
    $("thread").replaceChildren();
    if (push) history.pushState({}, "", state.selectedPaper ? `/chat?paper=${encodeURIComponent(state.selectedPaper)}` : "/chat");
    renderPapers();
    updateBuildButton();
    renderEmptyState();
    markActiveChat();
    updateComposer();
    $("question").focus();
}

export async function openChat(chatId, { push = true } = {}) {
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
    renderPapers();
    updateBuildButton();
    renderEmptyState();
    markActiveChat();
    updateComposer();
    scrollToBottom(true);
}

// The open chat becomes the chat the server saved (a new chat gets its id here)
function adoptChat(chatId, paper) {
    const isNewChat = state.chatId === null;
    state.chatId = chatId;
    state.chatPaper = paper;
    expandPaper(paper);
    if (isNewChat) history.pushState({}, "", `/chat?chat=${chatId}`);
    renderPapers();
}

// Read a streamed response: one JSON object per line
async function* readEvents(response) {
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        let end;
        while ((end = buffer.indexOf("\n")) >= 0) {
            const line = buffer.slice(0, end).trim();
            buffer = buffer.slice(end + 1);
            if (line) yield JSON.parse(line);
        }
    }
    if (buffer.trim()) yield JSON.parse(buffer);
}

function requestError(message, status) {
    const err = new Error(message);
    err.status = status;
    return err;
}

export async function ask(question) {
    question = question.trim();
    if (!question || state.busy) return;
    if (!isIndexed(currentPaper())) {
        App.toast(currentPaper() ? "Build the index first to ask about this paper." : "Pick a paper first.", "error");
        return;
    }

    const controller = new AbortController();
    state.busy = true;
    state.stream = controller;
    $("question").value = "";
    autoResize();
    updateComposer();
    $("empty-state").hidden = true;

    const userMessage = addUserMessage(question);
    const answer = addStreamingAnswer();
    let started = null; // the "start" event: chat id and paper
    try {
        const body = { question, k: Number($("k-select").value), stream: true };
        if (state.chatId) body.chat_id = state.chatId;
        else body.paper = state.selectedPaper;

        const response = await fetch("/ask", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
            signal: controller.signal,
        });
        if (!response.ok) {
            const data = await response.json().catch(() => null);
            throw requestError((data && data.error) || `Request failed (status ${response.status}).`, response.status);
        }

        let finished = false;
        for await (const event of readEvents(response)) {
            if (event.type === "start") {
                started = event;
                answer.found(event.sources);
            } else if (event.type === "token") {
                answer.add(event.text);
            } else if (event.type === "done") {
                answer.finish(event.result);
                adoptChat(event.result.chat_id, event.result.paper);
                finished = true;
            } else if (event.type === "error") {
                throw requestError(event.error, event.status);
            }
        }
        if (!finished) throw requestError("The answer stopped early. Please try again.");
        loadChats();
    } catch (err) {
        if (controller.signal.aborted) {
            answer.stop();
            // The server saves what was written before Stop; continue in that chat if it was saved
            setTimeout(async () => {
                await loadChats();
                if (started && state.chatId === null && state.chats.some((chat) => chat.id === started.chat_id)) {
                    adoptChat(started.chat_id, started.paper);
                }
            }, 500);
        } else {
            answer.remove();
            addErrorMessage(err.message, question, userMessage);
            if (err.status === 503 || err.status === undefined) refreshStatus();
        }
    } finally {
        state.busy = false;
        state.stream = null;
        updateComposer();
        $("question").focus();
    }
}

export function stopAnswer() {
    if (state.stream) state.stream.abort();
}

// The message box grows with the text, up to 200 px
export function autoResize() {
    const textarea = $("question");
    textarea.style.height = "auto";
    textarea.style.height = `${Math.min(textarea.scrollHeight, 200)}px`;
}
