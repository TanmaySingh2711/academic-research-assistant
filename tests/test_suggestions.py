"""Test src/suggestions.py: turning the model's reply into clean questions (no LLM needed)."""

import sys

from src.suggestions import NUMBER_OF_QUESTIONS, build_messages, parse_questions

failures: list[str] = []


def check(ok, label):
    print(f"  {label:<55} {'OK' if ok else 'FAIL'}")
    if not ok:
        failures.append(label)


# A typical reply from a small model: an intro line, numbers, bullets, quotes and a duplicate
reply = """Here are 4 questions about the paper:
1. What reward does the cautious curiosity agent use?
2) How is the agent compared with human players?
- "Why does curiosity follow an inverted U-shaped curve?"
* What reward does the cautious curiosity agent use?
Q5: Which game is used to test the agent?
What else?
"""
questions = parse_questions(reply)
for q in questions:
    print(f"    {q}")

check(len(questions) == NUMBER_OF_QUESTIONS, f"keeps at most {NUMBER_OF_QUESTIONS} questions")
check(questions[0] == "What reward does the cautious curiosity agent use?", "removes the number '1.'")
check(questions[1] == "How is the agent compared with human players?", "removes the number '2)'")
check(questions[2] == "Why does curiosity follow an inverted U-shaped curve?", "removes '-' and the quotes")
check(questions[3] == "Which game is used to test the agent?", "removes 'Q5:' and skips the duplicate")
check(all(q.endswith("?") for q in questions), "every line is a question")
check(parse_questions("Sorry, I cannot help with that.") == [], "a reply without questions gives []")

messages = build_messages("Title. Abstract text.")
check([m["role"] for m in messages] == ["system", "user"], "build_messages returns system + user")
check("Title. Abstract text." in messages[1]["content"], "the start of the paper is in the prompt")

if failures:
    sys.exit(f"{len(failures)} check(s) failed: {failures}")
