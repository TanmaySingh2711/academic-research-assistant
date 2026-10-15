# Academic Research Assistant

[![CI](https://github.com/TanmaySingh2711/academic-research-assistant/actions/workflows/ci.yml/badge.svg)](https://github.com/TanmaySingh2711/academic-research-assistant/actions/workflows/ci.yml)

A fully local RAG (Retrieval-Augmented Generation) assistant that answers questions about research paper PDFs.
Every answer comes with its sources (paper filename and page number), so you can check it against the original text.
Everything runs on your own computer: no API keys, no paid services and no cloud.

## Features

- A 3-page dashboard in a black and cyan theme: Overview, Assistant and How it works
- Chat interface in the style of ChatGPT, Claude and Gemini: answers appear word by word as the model writes them, and a Stop button ends an answer early
- Follow-up questions: "how was it evaluated?" refers to the chat so far
- Upload PDFs with the clip button or by dropping them on the page, then build the search index with one click. Build index only reads the papers that are new or changed
- Scanned (image-only) pages are read with OCR, offline
- Every chat is about one paper, and a paper can have many chats
- Sidebar: "All papers" holds every paper, and every paper is a dropdown with its own chats
- Rename and delete chats, and delete papers. Deleting is instant and does only that: the paper's chats and chunks are removed, other papers are not indexed again
- Suggested questions for each paper: the local model reads the start of the paper and writes a few questions about it
- Sources for every answer: paper, page and a relevance score; click a citation number to open the exact chunk text
- Chat history saved on your computer and listed by paper in the assistant's sidebar
- Choose how many chunks the model reads (K = 1, 3 or 5)
- Says "I could not find this in the uploaded papers." when the papers do not contain the answer
- Shows prompt tokens, answer tokens and response time for each answer
- Flowcharts that show how the project was built, how it works inside and the user flow
- Works offline: plain HTML, CSS and JavaScript, no CDN or external fonts
- Measured quality: an evaluation set of 88 questions, run in CI (see "Evaluation")

## How it works

```
Ingestion (Build index, only for new or changed papers)
PDF files in data/
  -> text per page (pdfplumber; OCR for scanned pages)
  -> clean-up: running headers, page numbers, rotated arXiv stamps and the reference list are removed,
     tables are written row by row ("Sky Hop: Playable (GA) 91.5, ...")
  -> chunks of whole sentences, about 100 words, sharing their last sentence with the next chunk;
     each table gets its own chunk; a chunk in the middle of a section gets the section heading;
     abbreviations are explained ("Abbreviations: RL = Reinforcement Learning")
  -> embeddings (all-MiniLM-L6-v2, 384 numbers per chunk), normalized, added to FAISS (IndexFlatIP)
  -> saved to index/ (faiss.index, chunks.json, info.json with one entry per paper)

Question (Ask)
question (+ the previous question of the chat, for follow-ups)
  -> two searches over the chosen paper: FAISS (meaning) and BM25 (exact words)
  -> the two rankings are merged (reciprocal rank fusion)
  -> a cross-encoder re-ranks the best 20 chunks and keeps the top K
  -> prompt: rules + the last 2 questions and answers + numbered sources ([Source 1], ...) + question
  -> llama3.2:3b via Ollama (temperature 0.1, fixed seed), streamed word by word to the page
  -> answer + sources, saved in chats/
```

## Tech stack

| Part | Tool |
|---|---|
| Language | Python 3.12 (3.10 to 3.12 supported) |
| PDF text extraction | pdfplumber, RapidOCR (ONNX, offline) for scanned pages |
| Embeddings | sentence-transformers, model `all-MiniLM-L6-v2` |
| Keyword search | BM25, written in `src/bm25.py` |
| Re-ranking | sentence-transformers cross-encoder `cross-encoder/ms-marco-MiniLM-L6-v2` |
| Vector search | faiss-cpu (`IndexFlatIP`) |
| Local LLM | Ollama with `llama3.2:3b` |
| Web backend | Flask (answers streamed as NDJSON) |
| Dashboard | plain HTML, CSS and JavaScript modules |
| Tests | pytest, Playwright (with the Edge or Chrome you already have), coverage |

## Project structure

```
academic-research-assistant/
|-- app.py                  Flask backend: pages and the JSON API
|-- setup.bat / setup.sh    One-click setup (Windows / macOS and Linux)
|-- run_dashboard.bat       Start the dashboard on Windows (double-click)
|-- requirements.txt        Python libraries (pinned versions)
|-- requirements-dev.txt    Extra tools for development and CI (ruff, mypy, pytest, Playwright, coverage)
|-- pyproject.toml          Settings for ruff, mypy, pytest and coverage
|-- LICENSE                 All rights reserved
|-- data/                   Your PDFs go here (not included in the repo)
|-- index/                  Saved FAISS index and chunk metadata (generated, not in the repo)
|-- chats/                  Saved chat history (generated, not in the repo)
|-- .cache/                 All caches and generated files of the tools (not in the repo)
|-- .github/                CI workflow and the Ollama setup step it uses
|-- evaluation/
|   |-- corpus.py           4 synthetic papers laid out like real ones (headers, stamps, tables, references)
|   |-- questions.json      68 questions about them, each with its page and the facts the answer needs
|   |-- real_paper_questions.json  20 questions about one real paper (only runs if you have that paper)
|   `-- evaluate.py         Measures retrieval (Hit@K, MRR) and answers (correct, cited)
|-- scripts/
|   |-- run_dashboard.ps1   Launcher used by run_dashboard.bat
|   |-- serve.py            Runs the app on http://localhost:5000
|   |-- build_index.py      Build the index from the terminal (--full to rebuild everything)
|   |-- verify_setup.py     Checks the setup and downloads the two search models once
|   `-- configure_venv.py   Sends the project's Python cache files to .cache/pycache/
|-- src/
|   |-- schema.py           The shapes of the dictionaries (Page, Chunk, SearchResult, ...) for type hints
|   |-- loader.py           Read PDFs page by page, remove headers, stamps and references, tables, OCR
|   |-- chunker.py          Sentence chunks, table chunks, section headings, abbreviations
|   |-- embedder.py         Turn text into vectors with all-MiniLM-L6-v2
|   |-- vector_store.py     Normalize vectors, build, save and load the FAISS index, remove a paper
|   |-- ingest.py           Build index: only new and changed papers are read and embedded
|   |-- bm25.py             Keyword search
|   |-- reranker.py         Cross-encoder re-ranking
|   |-- retriever.py        Vector, keyword and hybrid search, re-ranking, follow-up questions
|   |-- prompt_builder.py   System prompt, earlier turns, numbered context and sources
|   |-- generator.py        Call Ollama (whole answer or word by word), token counts, "not found" check
|   |-- rag_pipeline.py     answer_question() and answer_question_stream(): retrieve -> prompt -> generate
|   |-- chat_store.py       Save and list chats (one JSON file per chat in chats/)
|   `-- suggestions.py      Suggested questions for a paper (saved in index/suggestions.json)
|-- templates/
|   |-- base.html           Shared layout: top bar and navigation
|   |-- overview.html       Page 1: what the project is
|   |-- chat.html           Page 2: the assistant (upload, build index, chat, chat history)
|   |-- how_it_works.html   Page 3: three flowcharts
|   `-- _icons.html         Line icons and the logo as inline SVG
|-- static/
|   |-- css/                base.css (shared), one file per page, and chat/ (one file per part of the Assistant)
|   |-- js/                 common.js (shared helpers), how.js, and chat/ (the Assistant, 8 small modules)
|   `-- img/logo.svg        App icon
`-- tests/                  pytest tests (see "Running the tests")
```

The Assistant page's JavaScript is split by job: `state.js` (shared state), `sidebar.js` (papers and chats),
`page.js` (status, Build index button, suggestions), `messages.js` (answers and sources), `chats.js`
(asking and streaming), `papers.js` (upload, build, delete), `menus.js` (menus and dialogs) and `main.js`
(events and start). They are standard ES modules, so no build tool is needed.

## Setup

### One-click setup

1. Install Python 3.10, 3.11 or 3.12, and Ollama from https://ollama.com/download
2. Run the setup script in the project folder:
   - Windows: double-click `setup.bat`
   - macOS / Linux: `bash setup.sh` (on Linux, OCR needs the OpenGL library: `sudo apt-get install libgl1`)

The script creates the venv, installs the libraries, sets Python to keep its cache files in `.cache/pycache/`, downloads `llama3.2:3b` (about 2 GB) and the two search models (about 110 MB), and checks the setup. You can run it again at any time; steps that are already done are skipped.

### Manual setup

1. Install Python 3.10, 3.11 or 3.12.

2. Create and activate a virtual environment in the project folder:

   Windows (PowerShell):
   ```
   py -3.12 -m venv venv
   venv\Scripts\activate
   ```
   macOS / Linux:
   ```
   python3 -m venv venv
   source venv/bin/activate
   ```

3. Install the Python libraries, and set Python to keep its cache files in `.cache/pycache/`:
   ```
   pip install -r requirements.txt
   python scripts/configure_venv.py
   ```

4. Install Ollama from the official site: https://ollama.com/download

5. Download the model (about 2 GB):
   ```
   ollama pull llama3.2:3b
   ```

6. Check the setup. This also downloads the embedding model and the re-ranker from Hugging Face once (no account or token needed); after that everything runs offline.
   ```
   python scripts/verify_setup.py
   ```

## How to run

**Windows, one click:** double-click `run_dashboard.bat`. The window opens in the center of the screen, the dashboard opens at http://localhost:5000 when the server is ready (about 3 seconds), and one press of **Esc** stops the server and closes the window (QuickEdit is turned off for this window, so clicking into it does not pause the server). If an older dashboard is still running on port 5000, the launcher restarts it so the newest code runs. It also starts Ollama if it is not running, and the search models and `llama3.2:3b` load in the background, so the first answer is fast too.

**Any OS, from a terminal:**

1. Start the app from the project folder (with the venv active):
   ```
   python scripts/serve.py
   ```
2. Open http://localhost:5000 in your browser.
3. Stop the server with Ctrl+C in the terminal.

`scripts/serve.py` listens on both 127.0.0.1 and ::1, because browsers on Windows try ::1 first for `localhost`; without it, `localhost` pages would wait for that to fail. For development with automatic reload, `python app.py` also works (debug mode, http://127.0.0.1:5000).

**Using the dashboard:**

| Page | URL | What you do there |
|---|---|---|
| Overview | `/` | Read what the project is, which models it uses and how a PDF becomes an answer |
| Assistant | `/chat` | Upload PDFs (clip button or drag and drop), click **Build index**, start a chat about a paper, ask, and manage papers and chats in the sidebar |
| How it works | `/how-it-works` | Three flowcharts: how it was built, how it works inside, and the user flow |

1. The Assistant page always opens on a default page (like a new chat in ChatGPT): upload one or more PDFs there, or pick a paper. Opening the dashboard fresh never reopens the last chat; a reload while it runs keeps the open chat.
2. A new paper opens its own page with a **Build index** button. Only new or changed papers are read, so adding one paper takes a few seconds no matter how many are already indexed.
3. Click a paper (or **+** next to it) to start a new chat about it. The assistant suggests a few questions about that paper (a few seconds the first time). Click one, or type your own question and press Enter. Follow-up questions can refer to the earlier answers.
4. The answer appears word by word; the square button stops it (the part already written is kept). Open the sources under the answer to check the exact text.
5. Use the **...** button next to a chat to rename or delete it, or next to a paper to delete the paper with all its chats. The menus also work with the keyboard (Tab, Enter, arrow keys, Esc).

To build the index from the terminal instead (for example after copying PDFs into `data/` by hand):
```
python scripts/build_index.py          # new and changed papers
python scripts/build_index.py --full   # every paper again
```

Uploading a PDF does not change the answers until you build the index. When a new version of the app reads PDFs or makes chunks differently, every paper shows as "needs indexing" again (and stays searchable until you click Build index).

## Evaluation

`evaluation/` holds a question set with known answers, so every change to the pipeline can be measured instead of guessed:

- `corpus.py` writes 4 synthetic papers (24 pages) that look like real ones to the PDF reader: a running header and a page number on every page, a rotated arXiv stamp, a results table drawn with lines and a reference list. Real papers cannot be put in the repo (they belong to their authors).
- `questions.json` has 68 questions: facts, numbers, paraphrases, table values, follow-ups ("And its recall?"), follow-ups that change the topic, and questions whose answer is not in the paper. Each lists the correct page and the facts a correct answer must contain.
- `real_paper_questions.json` has 20 questions about one real paper (Celemin, "Bayesian Optimization-based Search for Agent Control in Automated Game Testing", IEEE CoG 2024). It runs only if that PDF is on your computer.

Measures:

- **Hit@K**: share of questions where the chunk with the answer (correct page and the expected facts) is in the top K results
- **MRR**: mean reciprocal rank of that chunk (1 = always first)
- **Correct**: the answer contains every expected fact, or says "not found" when it should
- **Cited**: the answer cites a `[Source N]` from the correct page

```
python -m evaluation.evaluate                     # retrieval only (about a minute)
python -m evaluation.evaluate --answers           # also the answers (needs Ollama, a few minutes)
python -m evaluation.evaluate --method compare    # vector vs bm25 vs hybrid vs re-ranked
python -m evaluation.evaluate --answers --data data --questions evaluation/real_paper_questions.json
```

The index for the evaluation is built in `.cache/eval/`, so your own index is never touched.

**Results** (K = 3, CPU, llama3.2:3b). "Before" is the first version of this project (vector search, 100-word chunks, no PDF clean-up, no chat memory), measured with the same questions:

| | Synthetic papers, before | Synthetic papers, now | Real paper, before | Real paper, now |
|---|---|---|---|---|
| Hit@1 | 60.0% | **88.3%** | 44.4% | **83.3%** |
| Hit@3 | 88.3% | **98.3%** | 66.7% | **100%** |
| MRR | 0.754 | **0.931** | 0.599 | **0.907** |
| Correct answers | 86.8% | **97.1%** | 65.0% | **90 to 95%** |
| Cited the correct page | 81.7% | **90 to 92%** | 44.4% | **94.4%** |

The retrieval numbers are the same on every run. The answer numbers can move by one or two questions between runs (the model runs with a fixed seed, but Ollama is not fully deterministic), so they are given as a range where they moved.

What each change did (retrieval on the synthetic set unless noted):

| Change | Effect |
|---|---|
| Remove headers, page numbers, stamps and references; write tables row by row | answers 84.4% -> 87.5% |
| BM25 + FAISS (hybrid) | Hit@3 87.5% -> 92.9%, MRR 0.770 -> 0.820 |
| Cross-encoder re-ranking | Hit@1 64.3% -> 92.9%, MRR 0.770 -> 0.949 (paraphrased questions gain the most) |
| Sentence chunks and table chunks | Hit@3 94.6% -> 98.2% |
| Chat history in the prompt, previous question in the search | follow-up answers 4/8 -> 8/8 |
| History inside the user message instead of as chat turns | a small model answered "not found" after a topic change; now 4/4 |
| Abbreviations, at least one carried sentence, section headings in chunks | real paper: Hit@3 88.9% -> 100%, MRR 0.852 -> 0.907, answers 80% -> 90% |
| "Put [Source N] after every fact" in the prompt | real paper: cited the correct page 78% -> 94% |

Changes that were measured and **not** kept: a larger re-ranker (MiniLM-L12, same results, about 3 times slower), the bge-small embedding model (better alone, same after re-ranking), 200-word chunks (better on the real paper, worse on the synthetic set), 150-word chunks (worse on both) and putting the best chunk last in the prompt (fewer correct answers and citations).

Speed on a laptop CPU: search and re-ranking 0.35 to 0.45 s, the first words of the answer after about 0.6 s, a full answer in 1 to 1.5 s. Indexing a 4-page paper takes about 8 s (most of it loading the models).

## RAG concepts in this project

| Concept | Where it is implemented |
|---|---|
| LLM basics (tokens, context window, hallucination) | `src/generator.py`: `stream_answer()` and `generate_answer()` return prompt and answer token counts, use temperature 0.1 and a fixed seed; `src/prompt_builder.py`: `SYSTEM_PROMPT` and `NOT_FOUND_MESSAGE` guard against hallucination |
| RAG pipeline flow | `src/ingest.py`: `run_ingestion()` (indexing side); `src/rag_pipeline.py`: `answer_question_stream()` (question side) |
| Document loading | `src/loader.py`: `load_pdf()`, `read_page()`, `strip_edges()`, `drop_references()`, `table_to_text()`, `ocr_page()` |
| Chunking | `src/chunker.py`: `split_sentences()`, `chunk_sentences()`, `chunk_table()`, `add_abbreviations()` |
| Embeddings | `src/embedder.py`: `load_model()`, `embed_texts()`, `embed_chunks()` |
| Similarity search | `src/vector_store.py`: `normalize_vectors()`; `src/retriever.py`: `vector_scores()` (cosine similarity as the inner product of normalized vectors) |
| Keyword search and hybrid search | `src/bm25.py`: `BM25`; `src/retriever.py`: `fuse()` (reciprocal rank fusion) |
| Re-ranking | `src/reranker.py`: `rerank_scores()` |
| Vector database | `src/vector_store.py`: `build_index()` (FAISS `IndexFlatIP`), `remove_paper()`, `save_store()`, `load_store()` |
| Top-K retrieval | `src/retriever.py`: `retrieve(question, index, chunks, k, source, method, previous)` |
| Prompt construction | `src/prompt_builder.py`: `format_context()`, `format_history()`, `build_messages()`, `get_sources()` |
| Conversation memory | `src/chat_store.py`: `get_history()`; `src/rag_pipeline.py`: `find_chunks()` |
| Evaluation | `evaluation/evaluate.py`: Hit@K, MRR, answer correctness, citation correctness |

## Design decisions

- **pdfplumber with `x_tolerance=1.5` and `use_text_flow=True`**: the default settings glued words together (48% of the "words" in one paper were longer than 25 characters) and mixed the two columns line by line.
- **Rotated characters are dropped, short lines that repeat at the top or bottom of most pages are removed**: arXiv stamps came out one letter per line, and running headers matched questions about the paper's title on every page. Only lines of up to 15 words count, so repeated body text is never removed.
- **The reference list is removed** (from a "References" heading in the second half of the paper until an appendix): reference titles match many questions but never answer them.
- **Tables are written row by row with the column names** ("Sky Hop: Playable (GA) 91.5, Novelty 0.37") and get their own chunk with the caption: in plain extracted text the numbers lose their columns.
- **Chunking page by page, by whole sentences**: a chunk never spans two pages (one correct page number per chunk) and never cuts a sentence. Neighbouring chunks share their last sentence (at least one, even when it is longer than the 20-word overlap), so a chunk keeps what "it" refers to.
- **100-word chunks**: the embedding model reads at most 256 tokens. 150 and 200 words were tested (see "Evaluation") and were not better overall.
- **Hybrid search, then a cross-encoder**: vector search finds meaning, BM25 finds exact numbers and names; merging by rank (not by score) needs no tuning. The cross-encoder is too slow for every chunk but very good at choosing among 20.
- **Follow-ups search twice**: once with the question and once with "previous question + question"; every chunk keeps its better score. A follow-up gets its context, and a new topic is still found on its own.
- **Earlier turns go inside the user message**, clearly labelled, not as separate chat messages: given chat turns, llama3.2:3b answered "not found" for a new topic.
- **Temperature 0.1 and a fixed seed**: answers are factual and repeatable, so the evaluation gives the same numbers on every run.
- **Build index is incremental**: `info.json` stores each paper's size and change time. Unchanged papers keep their vectors; an index made with other settings (`PIPELINE_VERSION`) is rebuilt.
- **Normalized vectors + `IndexFlatIP`**: the inner product of two length-1 vectors is their cosine similarity. "Flat" means exact search, fast enough for thousands of chunks.
- **Streaming as NDJSON** (one JSON object per line): the page shows each word as it arrives. If the browser stops reading (Stop button), the server saves the part that was written.
- **"Not found" rule in the system prompt, detected only at the start of the answer**: the model has an allowed way to say it does not know, and partial answers keep their sources.
- **Uploads checked for `.pdf` and the `%PDF` header, names cleaned with `secure_filename`**: only real PDFs are saved, and file names cannot contain paths.
- **Dashboard inserts all server text with `textContent`**: text from PDFs can never run as code in the page.

## Known limitations

- **A 3B model still makes reading mistakes.** In the evaluation it sometimes missed one of two facts in a two-part question, or chose the wrong one of the 3 chunks even when the right chunk was there. Always check the sources.
- **Tables without lines** are read as plain text, so their numbers can lose their columns. Tables with lines around the cells are written row by row.
- **OCR quality depends on the scan.** Clean, printed pages work well; handwriting and very small text do not.
- **Local, single-user app.** It uses Flask's development server on localhost (127.0.0.1 and ::1), with no login. It is not meant to be put on the internet.
- **Upload limit of 25 MB per request** (all files in one upload together).
- **File names change on upload.** Spaces and special characters become underscores (`secure_filename`).

## Running the tests

The tests use pytest. Install the development tools once, then run them from the project folder with the venv active:

```
pip install -r requirements-dev.txt
python -m pytest                              # every test (1 to 2 minutes)
python -m pytest tests/test_chunker.py        # one file
python -m pytest -m "not browser and not ollama"   # skip the browser and real-LLM tests
```

| File | What it tests |
|---|---|
| `test_loader.py` | headers, page numbers, stamps and references removed; tables and captions; ligatures; OCR of a scanned page |
| `test_chunker.py` | sentences, overlap, long sentences, tables, section headings, abbreviations |
| `test_bm25.py`, `test_embedder.py`, `test_vector_store.py` | keyword scores; vectors; FAISS search, removing a paper, saving and loading |
| `test_ingest.py` | Build index embeds only new or changed papers, removes deleted ones, rebuilds an outdated index |
| `test_retriever.py` | every search method, the paper filter, re-ranking, follow-up questions |
| `test_prompt_builder.py`, `test_generator.py`, `test_rag_pipeline.py` | the exact prompt, Ollama errors, streaming, "not found" |
| `test_chat_store.py`, `test_suggestions.py` | saving, listing, renaming and deleting chats; suggested questions |
| `test_app.py` | every Flask route: upload, Build index, streaming answers, Stop, follow-ups, deleting papers, errors |
| `test_dashboard.py` | the pages and every file they load, offline, no inline scripts, no long dashes or emoji |
| `test_ui.py` | the Assistant in a real browser: asking, streaming, Stop, Build index, deleting, keyboard, small screens |
| `test_evaluation.py` | the evaluation set is valid and retrieval stays above Hit@3 95% and MRR 0.9 |

Notes:

- Every test runs in temporary folders, so it never changes your `data/`, `index/` or `chats/`.
- Most tests use a fake LLM, so they are fast and give the same result every time. Tests marked `ollama` use the real `llama3.2:3b` and are skipped when Ollama is not running.
- Tests marked `browser` use the Edge or Chrome that is already installed (Playwright does not download a browser) and are skipped when neither is there.

Coverage, lint and type check:

```
python -m coverage run -m pytest
python -m coverage report        # about 97% of src/ and app.py
ruff check .
mypy app.py src scripts evaluation tests
```

mypy is strict for the app code: every function in `app.py`, `src/`, `scripts/` and `evaluation/` must have type hints (`disallow_untyped_defs`). The dictionary shapes are defined once in `src/schema.py`.

## Continuous integration

Every push and pull request runs the workflow in `.github/workflows/ci.yml` on GitHub Actions:

| Check | What it does |
|---|---|
| Lint (ruff) | Code style, unused names and import order |
| Type check (mypy) | Strict static type check of all Python files |
| One-click setup (Windows, macOS, Linux) | Runs `setup.bat` or `setup.sh` on a clean machine, then checks that the venv works, that Python cache files go to `.cache/pycache/` and that no `__pycache__` folder is created |
| Tests (Windows, macOS, Linux) | Installs Ollama and `llama3.2:3b`, runs every pytest test (including the browser tests and the real-LLM tests) and fails if coverage drops below 90% |
| Answer quality | Runs the evaluation set with the real model and fails if Hit@3 drops below 95% or fewer than 90% of the answers are correct |

## Generated files

Everything that is generated again and again goes into one folder, `.cache/`:

```
.cache/
|-- pycache/    Python cache files for app.py, src/, tests/, scripts/ and evaluation/ (same layout as the project)
|-- ruff/       ruff cache
|-- mypy/       mypy cache
|-- pytest/     pytest cache
|-- coverage/   coverage data and the HTML report
`-- eval/       the index built by the evaluation
```

- Python normally creates a `__pycache__` folder next to every `.py` file. `scripts/configure_venv.py` (run by the setup scripts) installs a small helper into the venv that writes this project's cache files to `.cache/pycache/` instead, including the files pytest writes for the tests. Libraries keep their own caches inside `venv/`, so startup is just as fast.
- ruff, mypy, pytest and coverage write their caches to `.cache/` (set in `pyproject.toml`).
- CI fails if a `__pycache__` folder ever appears outside `venv/`.
- You can delete `.cache/` at any time; it is created again when needed.
- `index/` holds the generated search index, `data/` your PDFs and `chats/` your chats. All of these are ignored by git.

## Screenshots

![Dashboard](docs/screenshot.png)

Screenshot coming soon.

## License

Copyright (c) 2026 Tanmay Singh. All rights reserved. No one may use, copy, modify or distribute this project without written permission. See [LICENSE](LICENSE).
