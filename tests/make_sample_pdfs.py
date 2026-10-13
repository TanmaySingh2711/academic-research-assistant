"""Create 3 small sample PDFs for CI tests (standard library only, no PDF library needed).

The real research papers are not in the repo (they belong to their authors), so CI
uses these synthetic documents instead. Their topics match the test questions.

Usage: python -m tests.make_sample_pdfs [output_dir]   (default: data)
"""

import sys
import textwrap
from pathlib import Path

NOTE = "Synthetic sample text generated for automated tests. It is not a real research paper."

DOCUMENTS = {
    "sample_curiosity_agent.pdf": [
        "Sample paper A: A cautious curiosity agent for human-like game playing. " + NOTE + " "
        "Abstract. We describe a game-playing agent that is driven by curiosity. The agent receives an "
        "intrinsic reward when it reaches game states that it cannot yet predict well, and an extrinsic reward "
        "from the game score. The total reward function is the sum of the intrinsic curiosity reward and the "
        "extrinsic reward. To make the agent behave more like a human player, the curiosity reward follows an "
        "inverted U-shaped curve: the agent is most curious about states with a medium information gap, and less "
        "curious about states that are either fully known or completely unknown. In this way the agent explores "
        "the level without taking extreme risks, which human players also tend to avoid. We call this cautious "
        "curiosity.",
        "Evaluation. We compared the cautious curiosity agent with a random agent, a standard curiosity agent and "
        "an average human player in a simple platform game. Human judges watched short videos of each player and "
        "rated how human-like the behaviour looked. The cautious curiosity agent was rated more human-like than the "
        "other agents, while it still finished the level. It made some mistakes, hesitated before jumps and explored "
        "side areas, which the judges described as natural. The random agent did not finish the level within the "
        "time limit. These results suggest that a reward function based on a medium information gap can make an "
        "agent play more like an average human, not like an expert who rushes to the goal. Future work could test "
        "more games and larger groups of judges.",
    ],
    "sample_load_testing.pdf": [
        "Sample paper B: Reinforcement learning for load testing of video games. " + NOTE + " "
        "Abstract. Load testing checks whether a game keeps a stable frame rate when many objects, effects or "
        "players are on the screen. Manual load testing is slow, because human testers must play for hours to find "
        "the places where the game becomes slow. We train a reinforcement learning agent that plays the game and "
        "receives a reward when the number of frames per second drops. The reward function combines two parts: a "
        "game reward that keeps the agent playing well, and a performance reward that is high when rendering a "
        "frame takes longer than usual. By maximising this reward, the agent learns to visit the areas of the "
        "level where performance problems appear.",
        "Study. We injected artificial performance bugs into a racing game at known positions on the track. The "
        "agent found most of these positions after training, and it found them more often than a random agent and "
        "an agent that was trained only to win the race. Each low frame rate point found by the agent was stored "
        "with its position, so developers can reproduce the problem. The approach still needs a reward function "
        "that is adapted to each game, and training takes several hours on a normal computer. Even so, the results "
        "show that reinforcement learning can support load testing of video games and reduce the manual work of "
        "human testers.",
    ],
    "sample_bug_detection.pdf": [
        "Sample paper C: A platform for automated bug detection in 3D video games. " + NOTE + " "
        "Abstract. Bugs in 3D games break the experience of the player, but testing every interaction by hand is "
        "not practical. We present a platform that places an agent inside 3D environments that contain known bugs. "
        "The platform can inject several kinds of bugs: missing textures, objects that flicker or disappear, the "
        "camera clipping through walls, the player falling through the floor, and objects that stay frozen in the "
        "air. For each bug the platform produces a label mask that marks which pixels of the agent's view show the "
        "bug. These masks make it possible to train and evaluate models that detect bugs from images.",
        "Environments. The platform contains simple rooms and a larger maze, where the agent can move and look "
        "around freely. Researchers can add new bug types by writing a small script that changes the environment, "
        "and by choosing a colour for the bug in the label mask. The platform records the observations of the agent "
        "together with the masks, which gives a data set for learning. We hope the platform helps researchers "
        "compare methods for automated bug detection, for example models that learn what normal game frames look "
        "like and report frames that look unusual. The platform is meant for research and experiments, not for "
        "testing a finished commercial game.",
    ],
}


def escape(text):
    """Escape the characters that have a special meaning inside a PDF string."""
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def make_pdf(path, pages):
    """Write a minimal valid PDF with one text page per item in `pages`."""
    # Objects: 1 catalog, 2 page list, 3 font, then a page object and a content object per page
    page_ids = [4 + 2 * i for i in range(len(pages))]
    objects = {
        1: "<< /Type /Catalog /Pages 2 0 R >>",
        2: f"<< /Type /Pages /Kids [{' '.join(f'{p} 0 R' for p in page_ids)}] /Count {len(pages)} >>",
        3: "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    }
    for page_id, text in zip(page_ids, pages):
        lines = textwrap.wrap(text, width=95, break_on_hyphens=False)
        # 10 pt Helvetica, 14 pt line spacing, start near the top-left corner
        stream = "BT /F1 10 Tf 14 TL 50 742 Td\n" + "".join(f"({escape(line)}) Tj T*\n" for line in lines) + "ET"
        objects[page_id] = (
            "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Resources << /Font << /F1 3 0 R >> >> /Contents {page_id + 1} 0 R >>"
        )
        objects[page_id + 1] = f"<< /Length {len(stream)} >>\nstream\n{stream}\nendstream"

    # Write the objects and remember where each one starts (the xref table needs byte offsets)
    out = bytearray(b"%PDF-1.4\n")
    offsets = {}
    for number in sorted(objects):
        offsets[number] = len(out)
        out += f"{number} 0 obj\n{objects[number]}\nendobj\n".encode("ascii")

    xref_start = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode("ascii")
    for number in sorted(objects):
        out += f"{offsets[number]:010d} 00000 n \n".encode("ascii")
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_start}\n%%EOF\n".encode("ascii")

    Path(path).write_bytes(out)


def main():
    output_dir = Path(sys.argv[1] if len(sys.argv) > 1 else "data")
    output_dir.mkdir(parents=True, exist_ok=True)
    for name, pages in DOCUMENTS.items():
        make_pdf(output_dir / name, pages)
        print(f"Created {output_dir / name} ({len(pages)} pages)")


if __name__ == "__main__":
    main()
