"""Quick test for src/generator.py and src/rag_pipeline.py: ask 4 questions to the local LLM."""

import ollama

from src.rag_pipeline import answer_question
from src.retriever import check_model_matches
from src.vector_store import load_store

MODEL = "llama3.2:3b"

index, chunks, info = load_store("index")
check_model_matches(info)

QUESTIONS = [
    "What reward function does the cautious curiosity agent use?",
    "How can reinforcement learning be used for load testing of games?",
    "How does an AI agent behave more like a human player?",
    "What is the capital of France?",
]


def get_num_ctx(model):
    """Context window Ollama is really using, read from the loaded model (ollama ps). None if not loaded."""
    for m in ollama.ps().models:
        if m.model == model:
            return m.context_length
    return None


num_ctx = None
print("Note: the first call is slower because Ollama loads the model into memory.\n")

for number, question in enumerate(QUESTIONS, start=1):
    result = answer_question(question, index, chunks, k=3)

    if num_ctx is None:  # the model is loaded now, so ollama ps can report its context window
        num_ctx = get_num_ctx(MODEL)
        print(f"Context window (num_ctx) in use: {num_ctx if num_ctx else 'unknown'} tokens\n")

    print("=" * 80)
    print(f"Q{number}: {question}")
    print("=" * 80)
    print(result["answer"])
    print(f"\nnot_found: {result['not_found']}")
    print("sources:" if result["sources"] else "sources: (none)")
    for s in result["sources"]:
        print(f"  [Source {s['source_number']}] {s['source'][:30]}... page {s['page']} (score {s['score']})")
    used = f"{100 * result['prompt_tokens'] / num_ctx:.1f}%" if num_ctx and result["prompt_tokens"] else "unknown"
    print(f"prompt_tokens: {result['prompt_tokens']} ({used} of context window) | "
          f"answer_tokens: {result['answer_tokens']} | seconds: {result['seconds']}\n")
