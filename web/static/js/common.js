// Shared helpers for every page.
// This file is loaded in <head>: it marks the page as "JS on" right away (so the
// scroll animations can hide content before it is drawn) and waits for the page
// to load before it touches anything else.
// SECURITY: text from the server always goes in with textContent, never innerHTML,
// so text from PDFs can never run as code in the page.

document.documentElement.classList.add("js");

const App = (() => {
    const MAX_UPLOAD_MB = 25; // same limit as MAX_CONTENT_LENGTH in app.py
    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    // ---------- Server calls ----------

    // Call the JSON API. Throws an Error with a simple message when something fails.
    async function api(url, options = {}) {
        let response;
        try {
            response = await fetch(url, options);
        } catch {
            throw new Error("Cannot reach the server. Is app.py running?");
        }
        let data = null;
        try {
            data = await response.json();
        } catch {
            // the body was not JSON
        }
        if (!response.ok) {
            const err = new Error((data && data.error) || `Request failed (status ${response.status}).`);
            err.status = response.status;
            throw err;
        }
        if (data === null) throw new Error("The server sent an unexpected response.");
        return data;
    }

    // ---------- Building elements ----------

    // Create an element with an optional class and text (text is always set safely)
    function el(tag, className, text) {
        const node = document.createElement(tag);
        if (className) node.className = className;
        if (text !== undefined && text !== null) node.textContent = text;
        return node;
    }

    // Line icons, drawn as SVG shapes (same look as web/templates/_icons.html)
    const ICONS = {
        file: [["path", { d: "M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" }], ["path", { d: "M14 2v6h6M16 13H8M16 17H8M10 9H8" }]],
        chat: [["path", { d: "M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" }]],
        copy: [["rect", { x: 9, y: 9, width: 13, height: 13, rx: 2 }], ["path", { d: "M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" }]],
        check: [["path", { d: "M20 6 9 17l-5-5" }]],
        alert: [["circle", { cx: 12, cy: 12, r: 9 }], ["path", { d: "M12 8v4M12 16h.01" }]],
        refresh: [["path", { d: "M21 4v6h-6M3 20v-6h6" }], ["path", { d: "M5.5 9a8 8 0 0 1 13.2-3L21 10M3 14l2.3 4a8 8 0 0 0 13.2-3" }]],
        book: [["path", { d: "M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2zM22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z" }]],
        chevron: [["path", { d: "m6 9 6 6 6-6" }]],
        plus: [["path", { d: "M12 5v14M5 12h14" }]],
        upload: [["path", { d: "M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M17 8l-5-5-5 5M12 3v12" }]],
        database: [["ellipse", { cx: 12, cy: 5, rx: 9, ry: 3 }], ["path", { d: "M21 12c0 1.66-4 3-9 3s-9-1.34-9-3" }], ["path", { d: "M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5" }]],
        layers: [["path", { d: "M12 2 2 7l10 5 10-5z" }], ["path", { d: "m2 17 10 5 10-5M2 12l10 5 10-5" }]],
        more: [["circle", { cx: 5, cy: 12, r: 1.2 }], ["circle", { cx: 12, cy: 12, r: 1.2 }], ["circle", { cx: 19, cy: 12, r: 1.2 }]],
        trash: [["path", { d: "M3 6h18M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" }], ["path", { d: "m19 6-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6M10 11v6M14 11v6" }]],
        edit: [["path", { d: "M12 20h9" }], ["path", { d: "M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z" }]],
        stop: [["rect", { x: 6, y: 6, width: 12, height: 12, rx: 2, fill: "currentColor" }]],
    };

    function icon(name, size = 18) {
        const ns = "http://www.w3.org/2000/svg";
        const svg = document.createElementNS(ns, "svg");
        for (const [k, v] of Object.entries({
            class: `icon icon-${name}`, width: size, height: size, viewBox: "0 0 24 24", fill: "none",
            stroke: "currentColor", "stroke-width": 2, "stroke-linecap": "round", "stroke-linejoin": "round",
            "aria-hidden": "true",
        })) svg.setAttribute(k, v);
        for (const [tag, attrs] of ICONS[name] || []) {
            const shape = document.createElementNS(ns, tag);
            for (const [k, v] of Object.entries(attrs)) shape.setAttribute(k, v);
            svg.append(shape);
        }
        return svg;
    }

    // The app logo (page with lines and a search lens), used as the assistant avatar
    function logo(size = 20) {
        const ns = "http://www.w3.org/2000/svg";
        const svg = document.createElementNS(ns, "svg");
        svg.setAttribute("viewBox", "0 0 32 32");
        svg.setAttribute("width", size);
        svg.setAttribute("height", size);
        svg.setAttribute("fill", "none");
        svg.setAttribute("aria-hidden", "true");
        const shapes = [
            ["rect", { x: 5, y: 3, width: 18, height: 24, rx: 3, stroke: "currentColor", "stroke-width": 2 }],
            ["path", { d: "M9 9h10M9 13h10M9 17h5", stroke: "currentColor", "stroke-width": 2, "stroke-linecap": "round" }],
            ["circle", { cx: 22, cy: 21, r: 5, fill: "var(--bg)", stroke: "currentColor", "stroke-width": 2 }],
            ["path", { d: "m25.5 24.5 3 3", stroke: "currentColor", "stroke-width": 2.4, "stroke-linecap": "round" }],
        ];
        for (const [tag, attrs] of shapes) {
            const shape = document.createElementNS(ns, tag);
            for (const [k, v] of Object.entries(attrs)) shape.setAttribute(k, v);
            svg.append(shape);
        }
        return svg;
    }

    // ---------- Text helpers ----------

    // "Cautious_Curiosity_A_Novel_Approach.pdf" -> "Cautious Curiosity A Novel Approach"
    function paperName(filename) {
        if (!filename) return "All papers";
        return filename.replace(/\.pdf$/i, "").replace(/_/g, " ");
    }

    // "just now", "5 min ago", "3 h ago", "Oct 14"
    function relativeTime(iso) {
        const date = new Date(iso);
        if (isNaN(date)) return iso;
        const minutes = Math.round((Date.now() - date) / 60000);
        if (minutes < 1) return "just now";
        if (minutes < 60) return `${minutes} min ago`;
        if (minutes < 24 * 60) return `${Math.round(minutes / 60)} h ago`;
        return date.toLocaleDateString(undefined, { month: "short", day: "numeric" });
    }

    // ---------- Toast messages ----------

    function toast(message, type = "info") {
        const box = document.getElementById("toasts");
        if (!box) return;
        const item = el("div", `toast${type === "error" ? " is-error" : ""}`);
        item.append(icon(type === "error" ? "alert" : "check", 16), el("span", "", message));
        box.append(item);
        setTimeout(() => {
            item.classList.add("is-leaving");
            item.addEventListener("animationend", () => item.remove(), { once: true });
        }, type === "error" ? 6000 : 4000);
    }

    // ---------- Status (shared by the top bar and the pages) ----------

    let statusRequest = null;

    // Ask the server for the status once, and share the answer with everyone who asks.
    // Resolves to null when the server cannot be reached.
    function getStatus(refresh = false) {
        if (!statusRequest || refresh) {
            statusRequest = api("/status").catch(() => null).then((status) => {
                updateStatusPill(status);
                return status;
            });
        }
        return statusRequest;
    }

    function updateStatusPill(status) {
        const pill = document.getElementById("status-pill");
        if (!pill) return;
        const text = pill.querySelector(".status-text");
        pill.classList.remove("is-ok", "is-warn", "is-bad");

        if (!status) {
            pill.classList.add("is-bad");
            text.textContent = "Server offline";
            pill.title = "Cannot reach the server. Is app.py running?";
            return;
        }
        const index = status.index_ready ? `Index ready, ${status.chunks} chunks` : "Index not built yet";
        const ollama = status.ollama_running ? "Ollama running" : "Ollama not running";
        pill.title = `${index}. ${ollama}.`;

        if (status.index_ready && status.ollama_running) {
            pill.classList.add("is-ok");
            text.textContent = "Ready";
        } else {
            pill.classList.add("is-warn");
            text.textContent = !status.ollama_running ? "Ollama off" : "No index";
        }
    }

    // ---------- Scroll animations ----------

    // Elements with data-reveal fade in when they scroll into view
    function observeReveal(root = document) {
        const items = root.querySelectorAll("[data-reveal]:not(.is-visible)");
        if (!("IntersectionObserver" in window) || reducedMotion) {
            items.forEach((item) => item.classList.add("is-visible"));
            return;
        }
        const observer = new IntersectionObserver((entries) => {
            for (const entry of entries) {
                if (entry.isIntersecting) {
                    entry.target.classList.add("is-visible");
                    observer.unobserve(entry.target);
                }
            }
        }, { threshold: 0.12, rootMargin: "0px 0px -40px 0px" });
        items.forEach((item) => observer.observe(item));
    }

    document.addEventListener("DOMContentLoaded", () => {
        observeReveal();
        getStatus();
    });

    return {
        MAX_UPLOAD_MB, reducedMotion, api, el, icon, logo, paperName, relativeTime,
        toast, getStatus, observeReveal,
    };
})();
