// Dashboard logic: talks to the Flask JSON API and updates the page.
// SECURITY: all text from the server goes in with textContent (never innerHTML),
// so text from PDFs can never run as code in the page.

const MAX_UPLOAD_MB = 25; // same limit as MAX_CONTENT_LENGTH in app.py

// Short helper to find an element by id
const $ = (id) => document.getElementById(id);

// ---------- Helpers ----------

// Call the API and return the JSON body. Throws an Error with a simple message on failure.
async function api(url, options = {}) {
    let response;
    try {
        response = await fetch(url, options);
    } catch {
        // fetch only fails like this when the server cannot be reached at all
        throw new Error("Cannot reach the server. Is app.py running?");
    }

    let data = null;
    try {
        data = await response.json();
    } catch {
        // body was not JSON
    }

    if (!response.ok) {
        throw new Error((data && data.error) || `Request failed (status ${response.status}).`);
    }
    if (data === null) {
        throw new Error("The server sent an unexpected response.");
    }
    return data;
}

// Show or hide an error box
function showError(box, message) {
    box.textContent = message;
    box.hidden = false;
}

function clearError(box) {
    box.textContent = "";
    box.hidden = true;
}

// Disable a button and show its loading indicator (or undo it)
function setLoading(button, loadingEl, isLoading) {
    button.disabled = isLoading;
    loadingEl.hidden = !isLoading;
}

// Create an element with optional class and text (text is always set safely)
function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
}

// Set a status marker to "ok", "bad" or neutral (null)
function setMarker(marker, state) {
    marker.classList.remove("ok", "bad");
    if (state) marker.classList.add(state);
}

// "2026-10-14T01:37:53" -> local readable date and time
function formatTime(iso) {
    const date = new Date(iso);
    return isNaN(date) ? iso : date.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

// ---------- b) Status bar ----------

let indexReady = false;

async function loadStatus() {
    const errorBox = $("status-error");
    clearError(errorBox);
    try {
        const status = await api("/status");

        // Index
        indexReady = status.index_ready;
        $("index-status").textContent = status.index_ready
            ? `Ready (${status.chunks} chunks, built ${formatTime(status.built_at)})`
            : "Not built yet";
        setMarker($("index-marker"), status.index_ready ? "ok" : "bad");

        // Ollama
        $("ollama-status").textContent = status.ollama_running ? "Running" : "Not running";
        $("ollama-hint").hidden = status.ollama_running;
        setMarker($("ollama-marker"), status.ollama_running ? "ok" : "bad");

        // Papers in data/
        const pdfs = status.pdfs_in_data;
        $("papers-status").textContent = `${pdfs.length} paper${pdfs.length === 1 ? "" : "s"}`;
        setMarker($("papers-marker"), pdfs.length > 0 ? "ok" : "bad");
        const list = $("paper-list");
        list.replaceChildren(...pdfs.map((name) => el("li", "", name)));
    } catch (err) {
        indexReady = false;
        for (const id of ["index-status", "ollama-status", "papers-status"]) $(id).textContent = "Unknown";
        for (const id of ["index-marker", "ollama-marker", "papers-marker"]) setMarker($(id), null);
        showError(errorBox, err.message);
    }
    updateAskState();
}

// ---------- c) Step 1: Upload papers ----------

$("upload-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const input = $("file-input");
    const errorBox = $("upload-error");
    clearError(errorBox);

    const files = Array.from(input.files);
    if (files.length === 0) {
        showError(errorBox, "Choose at least one PDF file first.");
        return;
    }

    // Check the size here, because a too-large upload can make the dev server drop the connection
    const totalMb = files.reduce((sum, f) => sum + f.size, 0) / (1024 * 1024);
    if (totalMb > MAX_UPLOAD_MB) {
        showError(errorBox, `These files are ${totalMb.toFixed(1)} MB together. The limit is ${MAX_UPLOAD_MB} MB per upload.`);
        return;
    }

    const form = new FormData();
    files.forEach((file) => form.append("files", file)); // field name "files", as app.py expects

    setLoading($("upload-button"), $("upload-loading"), true);
    try {
        const data = await api("/upload", { method: "POST", body: form });

        $("upload-message").textContent = data.message;
        $("upload-saved").replaceChildren(...data.saved.map((name) => el("li", "saved", `Saved: ${name}`)));
        $("upload-skipped").replaceChildren(
            ...data.skipped.map((s) => el("li", "skipped", `Skipped: ${s.name} (${s.reason})`))
        );
        $("upload-note").hidden = data.saved.length === 0;
        $("upload-result").hidden = false;
        input.value = ""; // clear the file picker
        loadStatus(); // the paper list changed
    } catch (err) {
        showError(errorBox, err.message);
    } finally {
        setLoading($("upload-button"), $("upload-loading"), false);
    }
});

// ---------- d) Step 2: Build index ----------

$("build-button").addEventListener("click", async () => {
    const errorBox = $("build-error");
    const result = $("build-result");
    clearError(errorBox);
    result.hidden = true;

    setLoading($("build-button"), $("build-loading"), true);
    try {
        const data = await api("/process", { method: "POST" });
        const s = data.summary; // numbers are nested under "summary"
        result.textContent = `${data.message} Took ${s.seconds} seconds.`;
        result.hidden = false;
        $("upload-note").hidden = true; // new papers are searchable now
        await loadStatus();
    } catch (err) {
        showError(errorBox, err.message);
    } finally {
        setLoading($("build-button"), $("build-loading"), false);
    }
});

// ---------- e) Step 3: Ask a question ----------

let asking = false;

// Asking is only possible when the index is ready and no question is running
function updateAskState() {
    $("ask-button").disabled = !indexReady || asking;
    $("question").disabled = !indexReady;
    $("ask-disabled-note").hidden = indexReady;
}

// Enter submits, Shift+Enter makes a new line
$("question").addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
        event.preventDefault();
        $("ask-form").requestSubmit();
    }
});

$("ask-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const errorBox = $("ask-error");
    clearError(errorBox);

    const question = $("question").value.trim();
    if (!question) {
        showError(errorBox, "Please type a question.");
        return;
    }
    if (!indexReady || asking) return;

    const k = Number($("k-select").value);

    asking = true;
    updateAskState();
    $("ask-loading").hidden = false;
    try {
        const data = await api("/ask", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ question, k }),
        });
        showAnswer(data);
    } catch (err) {
        showError(errorBox, err.message);
    } finally {
        asking = false;
        $("ask-loading").hidden = true;
        updateAskState();
    }
});

// ---------- f) Answer and sources ----------

function showAnswer(data) {
    const answer = $("answer-text");
    answer.textContent = data.answer; // CSS white-space: pre-wrap keeps the line breaks
    answer.classList.toggle("not-found", data.not_found);

    const tokens = (n) => (n === null || n === undefined ? "?" : n);
    $("answer-meta").textContent =
        `K = ${data.k} | prompt tokens: ${tokens(data.prompt_tokens)} | ` +
        `answer tokens: ${tokens(data.answer_tokens)} | ${data.seconds} s`;

    // No sources when the answer was not found in the papers
    const hasSources = !data.not_found && data.sources.length > 0;
    $("sources-block").hidden = !hasSources;
    $("sources-list").replaceChildren(...(hasSources ? data.sources.map(buildSource) : []));

    $("answer-section").hidden = false;
    $("answer-section").scrollIntoView({ behavior: "smooth", block: "start" });
}

// One expandable source: "[Source N] filename, page P" + score, and the chunk text inside
function buildSource(source) {
    const details = el("details", "source");
    const summary = el("summary");
    summary.append(
        el("span", "", `[Source ${source.source_number}] ${source.source}, page ${source.page}`),
        el("span", "score", `score ${Number(source.score).toFixed(2)}`)
    );
    details.append(summary, el("p", "chunk-text", source.text));
    return details;
}

// ---------- Start ----------

loadStatus();
