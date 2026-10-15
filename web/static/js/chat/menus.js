// The small "..." menus, the "Are you sure?" box, renaming and deleting a chat.

import { loadChats, startNewChat } from "./chats.js";
import { renderPapers } from "./sidebar.js";
import { $, api, el, icon, state } from "./state.js";

let menuElement = null; // the open menu, if any
let menuAnchor = null; // the "..." button that opened it

export function closeMenu() {
    if (menuElement) menuElement.remove();
    if (menuAnchor) menuAnchor.setAttribute("aria-expanded", "false");
    menuElement = null;
    menuAnchor = null;
}

// A small round button with three dots that opens a menu
export function moreButton(label, focusKey, items) {
    const button = el("button", "icon-btn more-btn");
    button.type = "button";
    button.dataset.focus = focusKey;
    button.title = label;
    button.setAttribute("aria-label", label);
    button.setAttribute("aria-haspopup", "menu");
    button.setAttribute("aria-expanded", "false");
    button.append(icon("more", 15));
    button.addEventListener("click", (event) => {
        event.stopPropagation();
        openMenu(button, items());
    });
    return button;
}

// A small menu next to a "..." button. items: [{label, iconName, danger, action}]
// Arrow keys move between the items, Esc closes it and returns to the button.
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
    menu.addEventListener("keydown", (event) => {
        const buttons = [...menu.querySelectorAll("button")];
        const at = buttons.indexOf(document.activeElement);
        if (event.key === "ArrowDown" || event.key === "ArrowUp") {
            event.preventDefault();
            const step = event.key === "ArrowDown" ? 1 : -1;
            buttons[(at + step + buttons.length) % buttons.length].focus();
        } else if (event.key === "Escape" || event.key === "Tab") {
            event.preventDefault();
            // Focus the "..." button first: it is only shown while its row has focus or its menu is open
            anchor.focus();
            closeMenu();
        }
    });
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
export function confirmDialog({ title, message, confirmLabel }) {
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
export function startRename(chat, item) {
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

// Like ChatGPT: the chat disappears at once and the server deletes it in the background.
// If the server cannot delete it, the list is loaded again and an error is shown.
export async function deleteChat(chat) {
    const ok = await confirmDialog({
        title: "Delete this chat?",
        message: `The chat "${chat.title}" will be deleted. This cannot be undone.`,
        confirmLabel: "Delete chat",
    });
    if (!ok) return;

    state.chats = state.chats.filter((c) => c.id !== chat.id);
    if (state.chatId === chat.id) startNewChat(chat.paper);
    else renderPapers();

    try {
        await api(`/api/chats/${encodeURIComponent(chat.id)}`, { method: "DELETE" });
    } catch (err) {
        App.toast(`Could not delete the chat: ${err.message}`, "error");
        await loadChats();
    }
}
