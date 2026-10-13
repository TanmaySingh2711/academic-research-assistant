"""Quick test for src/prompt_builder.py: show the exact messages that will be sent to the LLM."""

from src.prompt_builder import build_messages, get_sources
from src.retriever import retrieve
from src.vector_store import load_store

index, chunks, info = load_store("index")

QUESTIONS = [
    "What reward function does the cautious curiosity agent use?",
    "What is the capital of France?",
]

for number, question in enumerate(QUESTIONS, start=1):
    results = retrieve(question, index, chunks, k=3)
    messages = build_messages(question, results)
    user_content = messages[1]["content"]

    print("=" * 80)
    print(f"QUESTION {number}: {question}")
    print("=" * 80)
    print(f"--- system message (role={messages[0]['role']}) ---")
    print(messages[0]["content"])
    print(f"\n--- user message (role={messages[1]['role']}) ---")
    print(user_content)
    print("\n--- get_sources ---")
    for s in get_sources(results):
        print(f"  {s}")
    print(f"\nUser message size: {len(user_content)} characters, {len(user_content.split())} words\n")

print("=" * 80)
print("EDGE CASES")
print("=" * 80)
messages = build_messages("What is curiosity?", [])
print("--- user message with empty results ---")
print(messages[1]["content"])

try:
    build_messages("   ", [])
    print("\nEmpty question: no error (FAIL)")
except ValueError as e:
    print(f"\nEmpty question raises ValueError: {e}")
