// How it works page: switch between the 3 flowcharts and play their animation.

const tabs = [...document.querySelectorAll(".tab")];
const indicator = document.getElementById("tab-indicator");

// Number the parts of every flowchart, so they appear one after another (CSS uses --i)
document.querySelectorAll(".flow").forEach((flow) => {
    [...flow.children].forEach((child, i) => child.style.setProperty("--i", i));
});

// Move the cyan pill under the active tab
function moveIndicator(tab) {
    indicator.style.width = `${tab.offsetWidth}px`;
    indicator.style.transform = `translateX(${tab.offsetLeft}px)`;
}

// Start the "appear one by one" animation of the flowcharts in a panel
function play(panel) {
    panel.querySelectorAll(".flow").forEach((flow) => {
        flow.classList.remove("is-playing");
        void flow.offsetWidth; // restart the animation
        flow.classList.add("is-playing");
    });
}

function selectTab(tab, { updateHash = true } = {}) {
    for (const other of tabs) {
        const active = other === tab;
        other.classList.toggle("is-active", active);
        other.setAttribute("aria-selected", String(active));
        other.tabIndex = active ? 0 : -1;
        document.getElementById(other.getAttribute("aria-controls")).hidden = !active;
    }
    moveIndicator(tab);
    play(document.getElementById(tab.getAttribute("aria-controls")));
    if (updateHash) history.replaceState({}, "", `#${tab.dataset.hash}`);
}

tabs.forEach((tab, i) => {
    tab.addEventListener("click", () => selectTab(tab));
    // Left and right arrow keys move between tabs
    tab.addEventListener("keydown", (event) => {
        if (event.key !== "ArrowRight" && event.key !== "ArrowLeft") return;
        const next = tabs[(i + (event.key === "ArrowRight" ? 1 : tabs.length - 1)) % tabs.length];
        next.focus();
        selectTab(next);
    });
});

window.addEventListener("resize", () => moveIndicator(tabs.find((tab) => tab.classList.contains("is-active"))));

// Open the tab named in the address (#built, #inside, #user-flow), otherwise the first one
const startTab = tabs.find((tab) => `#${tab.dataset.hash}` === location.hash) || tabs[0];
selectTab(startTab, { updateHash: false });
