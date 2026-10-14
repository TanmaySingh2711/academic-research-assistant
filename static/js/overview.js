// Overview page: fill in the live numbers (papers and chunks) with a count-up animation.

// Count from 0 up to the target number in about 0.9 seconds
function countUp(element, target) {
    if (App.reducedMotion || target === 0) {
        element.textContent = target;
        return;
    }
    const start = performance.now();
    const duration = 900;
    function frame(now) {
        const progress = Math.min(1, (now - start) / duration);
        const eased = 1 - Math.pow(1 - progress, 3); // fast start, slow end
        element.textContent = Math.round(target * eased);
        if (progress < 1) requestAnimationFrame(frame);
    }
    requestAnimationFrame(frame);
}

App.getStatus().then((status) => {
    const papers = document.getElementById("stat-papers");
    const chunks = document.getElementById("stat-chunks");
    if (!status) {
        papers.textContent = "?";
        chunks.textContent = "?";
        return;
    }
    countUp(papers, status.indexed_papers.length);
    countUp(chunks, status.chunks);
});
