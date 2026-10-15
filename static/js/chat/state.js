// Shared state of the Assistant page and small helpers used by every module.

export const $ = (id) => document.getElementById(id);
// App comes from common.js (a classic script loaded before the modules)
export const { el, icon, api, paperName } = App;

// Remember which dropdowns are open, only in this browser (a small convenience)
// ("v2": the earlier version opened papers by itself, so its saved state is not reused)
const EXPANDED_KEY = "research-assistant.open-papers-v2";
export const ROOT_KEY = "__all__"; // the "All papers" dropdown that holds every paper
export const BOOT_KEY = "research-assistant.server-boot"; // see isFreshStart() in main.js

export const state = {
    status: null, // last answer of /status (null = server offline)
    chatId: null, // open chat, or null for a new chat
    chatPaper: null, // paper of the open chat
    selectedPaper: null, // paper chosen for a new chat
    busy: false, // waiting for an answer
    stream: null, // AbortController of the answer being written (Stop button)
    building: false, // Build index is running
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

export function saveExpanded() {
    try {
        localStorage.setItem(EXPANDED_KEY, JSON.stringify([...state.expanded]));
    } catch {
        // storage can be blocked (private window); the sidebar still works
    }
}

// Open the dropdown of a paper (and "All papers" around it), so its chats are visible
export function expandPaper(paper) {
    state.expanded.add(ROOT_KEY);
    if (paper) state.expanded.add(paper);
    saveExpanded();
}

export const isIndexed = (paper) => Boolean(state.status && state.status.indexed_papers.includes(paper));
export const inData = (paper) => Boolean(paper && state.status && state.status.pdfs_in_data.includes(paper));
export const currentPaper = () => (state.chatId ? state.chatPaper : state.selectedPaper);
export const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;
