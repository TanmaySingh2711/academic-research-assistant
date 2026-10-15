// Papers: upload PDFs, build the index, delete a paper.

import { loadChats, refreshStatus, startNewChat } from "./chats.js";
import { confirmDialog } from "./menus.js";
import { renderNotice, suggestionCache, updateBuildButton } from "./page.js";
import { renderPapers } from "./sidebar.js";
import { $, api, currentPaper, isIndexed, paperName, plural, saveExpanded, state } from "./state.js";

export function openFilePicker() {
    $("file-input").click();
}

export async function uploadFiles(fileList) {
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
            App.toast(`Uploaded ${plural(n, "paper")}. Click Build index to make ${n === 1 ? "it" : "them"} searchable.`);
        }
        await refreshStatus();
        // One new paper: open its page right away (it shows the Build index button)
        if (data.saved.length === 1 && state.chatId === null) startNewChat(data.saved[0]);
    } catch (err) {
        App.toast(err.message, "error");
    } finally {
        $("upload-button").disabled = false;
        $("attach-button").disabled = false;
        $("file-input").value = "";
    }
}

// Show or hide the "working on the index" line in the sidebar
function setBuilding(on, text = "Reading and indexing the new papers...") {
    state.building = on;
    updateBuildButton();
    $("build-prompt-button").disabled = on;
    $("build-progress-text").textContent = text;
    $("build-progress").hidden = !on;
    renderNotice();
}

// Build index reads and embeds only the papers that are new or changed (see src/ingest.py)
export async function buildIndex() {
    if (state.building) return;
    const waiting = state.status ? state.status.papers_to_index.length : 0;
    setBuilding(true, waiting === 1 ? "Reading and indexing the paper..." : `Reading and indexing ${plural(waiting, "paper")}...`);
    try {
        const data = await api("/process", { method: "POST" });
        App.toast(data.message);
        const uploaded = state.newUploads;
        state.newUploads = [];
        await refreshStatus();
        // Exactly one new paper: get a new chat ready for it
        if (uploaded.length === 1 && state.chatId === null && isIndexed(uploaded[0])) startNewChat(uploaded[0]);
    } catch (err) {
        App.toast(err.message, "error");
    } finally {
        setBuilding(false);
    }
}

// Deletes only this paper: its PDF, its chats and its chunks in the index. Other papers are
// not indexed again. Like a chat, it disappears from the page at once.
export async function deletePaper(paper) {
    if (state.building || state.busy) {
        App.toast("Please wait until the current task is finished.", "error");
        return;
    }
    const n = state.chats.filter((chat) => chat.paper === paper).length;
    const ok = await confirmDialog({
        title: "Delete this paper?",
        message: `${paperName(paper)} and its ${plural(n, "chat")} will be deleted. This cannot be undone.`,
        confirmLabel: "Delete paper",
    });
    if (!ok) return;

    // Remove it from the page right away
    const wasOpen = currentPaper() === paper;
    const without = (list) => (list || []).filter((p) => p !== paper);
    state.chats = state.chats.filter((chat) => chat.paper !== paper);
    if (state.status) {
        state.status = {
            ...state.status,
            pdfs_in_data: without(state.status.pdfs_in_data),
            indexed_papers: without(state.status.indexed_papers),
            papers_to_index: without(state.status.papers_to_index),
            unreadable_papers: without(state.status.unreadable_papers),
        };
    }
    suggestionCache.delete(paper);
    state.expanded.delete(paper);
    saveExpanded();
    state.newUploads = without(state.newUploads);
    if (wasOpen) startNewChat(null);
    else renderPapers();
    updateBuildButton();

    try {
        await api(`/api/papers/${encodeURIComponent(paper)}`, { method: "DELETE" });
    } catch (err) {
        App.toast(`Could not delete the paper: ${err.message}`, "error");
    }
    // Take the real state from the server (it puts the paper back if the delete failed)
    await refreshStatus();
    await loadChats();
}
