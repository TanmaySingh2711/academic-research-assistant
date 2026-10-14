# Academic Research Assistant

[![CI](https://github.com/TanmaySingh2711/academic-research-assistant/actions/workflows/ci.yml/badge.svg)](https://github.com/TanmaySingh2711/academic-research-assistant/actions/workflows/ci.yml)

A fully local RAG (Retrieval-Augmented Generation) assistant that answers questions about research paper PDFs.
Every answer comes with its sources (paper filename and page number), so you can check it against the original text.
Everything runs on your own computer: no API keys, no paid services and no cloud.

## Features

- A 3-page dashboard in a black and cyan theme: Overview, Assistant and How it works
- Chat interface in the style of ChatGPT, Claude and Gemini: message bubbles, a typing effect, Enter to send
- Upload PDFs with the clip button or by dropping them on the page, then build the search index with one click
- Every chat is about one paper, and a paper can have many chats
- Sidebar: "All papers" holds every paper, and every paper is a dropdown with its own chats
- Rename and delete chats, and delete papers (the paper's chats are deleted too and the index is rebuilt)
- Suggested questions for each paper: the local model reads the start of the paper and writes a few questions about it
- Sources for every answer: paper, page and similarity score; click a citation number to open the exact chunk text
- Chat history saved on your computer and listed by paper in the assistant's sidebar
- Choose how many chunks the model reads (K = 1, 3 or 5)
- Says "I could not find this in the uploaded papers." when the papers do not contain the answer
- Shows prompt tokens, answer tokens and response time for each answer
- Flowcharts that show how the project was built, how it works inside and the user flow
- Works offline: plain HTML, CSS and JavaScript, no CDN or external fonts

## How it works

```
Ingestion (Build index)
PDF files in data/
  -> text per page (pdfplumber), keeping filename and page number
  -> chunks of 100 words with 20 words overlap, page by page
  -> embeddings (all-MiniLM-L6-v2, 384 numbers per chunk)
  -> normalized and stored in FAISS (IndexFlatIP = cosine similarity)
  -> saved to index/ (faiss.index, chunks.json, info.json)

Question (Ask)
question
  -> embedding with the same model, normalized
  -> FAISS search for the top-K most similar chunks
  -> prompt: rules + numbered sources ([Source 1], [Source 2], ...) + question
  -> llama3.2:3b via Ollama (temperature 0.1)
  -> answer + sources shown in the dashboard
```

## Tech stack

| Part | Tool |
|---|---|
| Language | Python 3.12 (3.10 to 3.12 supported) |
| PDF text extraction | pdfplumber |
| Embeddings | sentence-transformers, model `all-MiniLM-L6-v2` |
| Vector search | faiss-cpu (`IndexFlatIP`) |
| Local LLM | Ollama with `llama3.2:3b` |
| Web backend | Flask |
| Dashboard | plain HTML, CSS and vanilla JavaScript |

## Project structure

```
academic-research-assistant/
|-- app.py                  Flask backend: routes /, /upload, /process, /ask, /status
|-- setup.bat / setup.sh    One-click setup (Windows / macOS and Linux)
|-- run_dashboard.bat       Start the dashboard on Windows (double-click)
|-- requirements.txt        Python libraries (pinned versions)
|-- requirements-dev.txt    Extra tools for development and CI (ruff, mypy)
|-- pyproject.toml          Settings for ruff and mypy
|-- LICENSE                 All rights reserved
|-- data/                   Your PDFs go here (not included in the repo)
|-- index/                  Saved FAISS index and chunk metadata (generated, not in the repo)
|-- .cache/                 All tool caches (generated, not in the repo)
|-- .github/                CI workflow and the Ollama setup step it uses
|-- scripts/
|   |-- run_dashboard.ps1   Launcher used by run_dashboard.bat
|   |-- serve.py            Runs the app on http://localhost:5000
|   |-- build_index.py      Rebuild the index from the terminal
|   `-- configure_venv.py   Sends the project's Python cache files to .cache/pycache/
|-- src/
|   |-- loader.py           Read PDFs page by page and clean the text
|   |-- chunker.py          Split pages into overlapping word chunks
|   |-- embedder.py         Turn text into vectors with all-MiniLM-L6-v2
|   |-- vector_store.py     Normalize vectors, build, save and load the FAISS index
|   |-- ingest.py           Full ingestion: load -> chunk -> embed -> index -> save
|   |-- retriever.py        Embed a question and find the top-K chunks
|   |-- prompt_builder.py   System prompt, numbered context and sources
|   |-- generator.py        Call Ollama, token counts, "not found" check
|   |-- rag_pipeline.py     answer_question(): retrieve -> prompt -> generate
|   |-- chat_store.py       Save and list chats (one JSON file per chat in chats/)
|   `-- suggestions.py      Suggested questions for a paper (saved in index/suggestions.json)
|-- chats/                  Saved chat history (generated, not in the repo)
|-- templates/
|   |-- base.html           Shared layout: top bar and navigation
|   |-- overview.html       Page 1: what the project is
|   |-- chat.html           Page 2: the assistant (upload, build index, chat, chat history)
|   |-- how_it_works.html   Page 3: three flowcharts
|   `-- _icons.html         Line icons and the logo as inline SVG
|-- static/
|   |-- css/                One shared stylesheet (base.css) plus one per page
|   |-- js/                 common.js (shared helpers), chat.js and how.js
|   `-- img/logo.svg        App icon
`-- tests/
    |-- verify_setup.py     Check that libraries are installed and Ollama is reachable
    |-- make_sample_pdfs.py Create 3 synthetic sample PDFs (used by CI)
    `-- test_*.py           One test script per step of the pipeline (see "Running the tests")
```

## Setup

### One-click setup

1. Install Python 3.10, 3.11 or 3.12, and Ollama from https://ollama.com/download
2. Run the setup script in the project folder:
   - Windows: double-click `setup.bat`
   - macOS / Linux: `bash setup.sh`

The script creates the venv, installs the libraries, sets Python to keep its cache files in `.cache/pycache/`, downloads `llama3.2:3b` (about 2 GB) and checks the setup. You can run it again at any time; steps that are already done are skipped.

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

6. Optional: check the setup.
   ```
   python -m tests.verify_setup
   ```

The first time the app embeds text, sentence-transformers downloads `all-MiniLM-L6-v2` (about 90 MB) from Hugging Face. No account or token is needed. After that everything runs offline.

## How to run

**Windows, one click:** double-click `run_dashboard.bat`. The window opens in the center of the screen, the dashboard opens at http://localhost:5000 when the server is ready (about 3 seconds), and **Esc** stops the server and closes the window. If an older dashboard is still running on port 5000, the launcher restarts it so the newest code runs. It also starts Ollama if it is not running, and the embedding model and `llama3.2:3b` load in the background, so the first answer is fast too.

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
2. Click **Build index** (on the page of a new paper, or in the sidebar). For 3 papers this took about 13 to 19 seconds on a CPU.
3. In the sidebar, click **+** next to a paper to start a new chat about it. The assistant suggests a few questions about that paper (a few seconds the first time). Click one, or type your own question and press Enter.
4. Open the sources under the answer to check the exact text. Each chat is saved in the sidebar, under its paper.
5. Use the **...** button next to a chat to rename or delete it, or next to a paper to delete the paper with all its chats.

To rebuild the index from the terminal instead (for example after copying PDFs into `data/` by hand):
```
python scripts/build_index.py
```

Uploading a PDF does not change the answers until you build the index again.

## RAG concepts in this project

| Concept | Where it is implemented |
|---|---|
| LLM basics (tokens, context window, hallucination) | `src/generator.py`: `generate_answer()` returns prompt and answer token counts, uses temperature 0.1; `src/prompt_builder.py`: `SYSTEM_PROMPT` and `NOT_FOUND_MESSAGE` guard against hallucination; `tests/test_generator.py` reads the context window (`num_ctx`) from Ollama and shows how much of it each prompt uses |
| RAG pipeline flow | `src/ingest.py`: `run_ingestion()` (indexing side); `src/rag_pipeline.py`: `answer_question()` (question side) |
| Document loading | `src/loader.py`: `load_pdfs()`, `load_pdf()`, `clean_text()` |
| Chunking | `src/chunker.py`: `split_into_chunks()`, `chunk_pages()` |
| Embeddings | `src/embedder.py`: `load_model()`, `embed_texts()`, `embed_chunks()` |
| Similarity search | `src/vector_store.py`: `normalize_vectors()`; `src/retriever.py`: `embed_query()` (cosine similarity as the inner product of normalized vectors) |
| Vector database | `src/vector_store.py`: `build_index()` (FAISS `IndexFlatIP`), `save_store()`, `load_store()` |
| Top-K retrieval | `src/retriever.py`: `retrieve(question, index, chunks, k)` |
| Prompt construction | `src/prompt_builder.py`: `format_context()`, `build_messages()`, `get_sources()` |

## Design decisions

- **pdfplumber with `x_tolerance=1.5` and `use_text_flow=True`**: the default settings glued words together (48% of the "words" in one paper were longer than 25 characters) and mixed the two columns line by line.
- **Chunking page by page**: a chunk never spans two pages, so every chunk has one correct page number for the sources.
- **100-word chunks with 20 words overlap**: the embedding model reads at most 256 tokens and silently cuts off the rest. With 150/30 words, 29 of 206 chunks were over the limit (largest 538 tokens). With 100/20, only 7 of 302 are over (largest 368 tokens): 6 reference-list chunks and 1 results table.
- **Overlap between chunks**: a sentence cut at a chunk boundary still appears whole in the neighbouring chunk.
- **Normalized vectors + `IndexFlatIP`**: the inner product of two length-1 vectors is their cosine similarity. "Flat" means exact search against every vector, which is fast enough for a few hundred chunks (about 6 to 15 ms per question including the question embedding).
- **Same embedding model for chunks and questions, checked at startup**: `info.json` stores the model name and `check_model_matches()` refuses an index built with a different model.
- **Temperature 0.1**: answers should be factual and repeatable, not creative.
- **"Not found" rule in the system prompt**: gives the model an allowed way to say it does not know, instead of answering from its own memory.
- **Reminder line after the question**: in testing, without it the model left out `[Source N]` citations in 2 of 3 answers. Small models follow the most recent instruction best.
- **"Not found" detected only at the start of the answer**: the model sometimes gives a partial answer and then adds the not-found sentence. Checking only the start keeps the sources for those partial answers.
- **Uploads checked for `.pdf` and the `%PDF` header, names cleaned with `secure_filename`**: only real PDFs are saved, and file names cannot contain paths or unsafe characters.
- **Building the index is a separate step**: uploading several papers does not trigger several slow rebuilds.
- **Dashboard inserts all server text with `textContent`**: text from PDFs can never run as code in the page.

## What I tested and observed

Test set: 3 research papers (27 pages, 302 chunks). Everything ran on a CPU (no GPU).

**Retrieval** (K = 3, cosine similarity scores):

| Question | Top result | Top 3 scores | Right paper first? |
|---|---|---|---|
| What reward function does the cautious curiosity agent use? | Cautious Curiosity, page 3 | 0.86, 0.80, 0.77 | Yes (all 3 from it) |
| How can reinforcement learning be used for load testing of games? | Load testing paper, page 2 | 0.80, 0.76, 0.74 | Yes (all 3 from it) |
| What kinds of bugs can the World of Bugs platform detect? | World of Bugs, page 1 | 0.64, 0.63, 0.62 | Yes (all 3 from it) |
| How does an AI agent behave more like a human player? (paraphrase) | Cautious Curiosity, page 1 | 0.73, 0.71, 0.67 | Yes (all 3 from it) |
| What is the capital of France? (off-topic) | page header / watermark / chart labels | 0.21, 0.15, 0.13 | Nothing relevant, as expected |

- Real questions scored 0.62 to 0.86. The off-topic question scored 0.21 or lower, and its "matches" were noise.
- Retrieval (question embedding + FAISS search) took about 6 to 15 ms per question.
- With K = 5 instead of 3, the two extra chunks scored a little lower (0.72 and 0.71) and were still from the right paper.
- Embedding demo: "An agent learns to play a video game using rewards." vs "Reinforcement learning trains a game-playing agent." scored 0.81, vs "Automated tools can find bugs in 3D games." 0.33, vs "How to bake a chocolate cake at home." -0.02.

**Generation** (llama3.2:3b, K = 3):

- Prompts used about 630 to 680 tokens, about 16% of the 4096-token context window Ollama uses for this model.
- The first answer after loading the model took about 6 to 8 seconds; later answers took about 1.3 to 2.2 seconds.
- The off-topic question was answered with exactly "I could not find this in the uploaded papers." and no sources. The model did not answer "Paris".
- For the reward function question, the retrieved chunks stop right before the exact formula. The model did not invent a formula; it said the exact details are not in the context.
- No answer contained facts that were missing from the retrieved chunks, but citations were not always correct (see the limitations).

**Index size**: `faiss.index` 453 KB and `chunks.json` 228 KB for 302 chunks. Embedding all 302 chunks took about 8 seconds on the CPU.

## Known limitations

- **Citations from a 3B model are not always right.** It sometimes cites the wrong source number (for example `[Source 1]` for a fact from Source 3), and it once described related work (Devlin et al. 2016, mentioned inside a paper) as if it were the paper's own method. Always check the expanded chunks.
- **No memory between questions.** A chat looks like ChatGPT, but each question is answered on its own from the papers. A follow-up like "explain that more" does not know the previous answer, so ask full questions.
- **No OCR.** Scanned (image-only) PDFs have no text, so they cannot be searched. The loader prints a warning for them.
- **Noisy text from PDF layout.** Tables, formulas, reference lists, repeated page headers, publisher cover pages and rotated watermarks come out as noisy text (for example `a r X i v : 2 2 0 6 ...`). Repeated headers that contain the paper title can also raise the score of unrelated chunks from that paper.
- **Some chunks are cut at the token limit.** 7 of 302 chunks are longer than the 256 tokens the embedding model reads, so their ends are ignored during search (6 reference-list chunks and 1 results table).
- **Neighbouring chunks can both be retrieved.** Because of the 20-word overlap, two results can share part of their text.
- **Local, single-user app.** It uses Flask's development server on localhost (127.0.0.1 and ::1), with no login. It is not meant to be put on the internet.
- **Upload limit of 25 MB per request** (all files in one upload together).
- **Deleting a paper rebuilds the whole index** (about 15 seconds for a few papers), because the simple Flat index is rebuilt from the remaining PDFs. Its chats are deleted too.
- **File names change on upload.** Spaces and special characters become underscores (`secure_filename`).

## Possible improvements

Ideas only, not built:

- Hybrid search: combine FAISS with keyword search (BM25) for exact terms like names and numbers
- Re-ranking: re-score the top results with a cross-encoder before sending them to the LLM
- A small retrieval evaluation set (questions with the correct page) to compare chunk sizes and K
- OCR for scanned PDFs
- Remove repeated page headers and reference lists before chunking

## Running the tests

The tests are scripts that print their results. Run them from the project folder with the venv active:

```
python -m tests.verify_setup          # libraries installed, Ollama reachable
python -m tests.test_loader           # PDF loading and text quality
python -m tests.test_chunker          # chunk counts, sizes and overlap
python -m tests.test_embedder         # embeddings, token lengths, similarity demo
python -m tests.test_vector_store     # saved index, normalization, self-search check
python -m tests.test_retriever        # top-K results for test questions
python -m tests.test_prompt_builder   # exact messages sent to the LLM
python -m tests.test_generator        # answers from llama3.2:3b (needs Ollama)
python -m tests.test_app              # all Flask routes (needs Ollama)
python -m tests.test_chat_store       # saving and listing chats (no LLM needed)
python -m tests.test_suggestions      # cleaning the suggested questions (no LLM needed)
python -m tests.test_dashboard        # the 4 pages, static files, no long dashes or emoji
```

Notes:

- Most tests need papers in `data/` and a built index (`python scripts/build_index.py`). Without your own papers, `python -m tests.make_sample_pdfs` puts 3 small sample PDFs in `data/` (this is what CI does).
- `test_app` works only in temporary folders with its own sample PDFs, so it never changes your `data/`, `index/` or `chats/`.
- Stop the running app before running the tests if you want port 5000 free; the tests themselves do not use the port.
- A test script exits with an error code when one of its checks fails, so CI can detect it. LLM answers are printed but not checked word by word, because their wording can change between runs.

Lint and type check (install the tools once with `pip install -r requirements-dev.txt`):

```
ruff check .
mypy app.py src tests scripts
```

## Continuous integration

Every push and pull request runs the workflow in `.github/workflows/ci.yml` on GitHub Actions:

| Check | What it does |
|---|---|
| Lint (ruff) | Code style, unused names and import order |
| Type check (mypy) | Static type check of all Python files |
| One-click setup (Windows, macOS, Linux) | Runs `setup.bat` or `setup.sh` on a clean machine, then checks that the venv works, that Python cache files go to `.cache/pycache/` and that no `__pycache__` folder is created |
| Tests (Windows, macOS, Linux) | Installs Ollama and `llama3.2:3b`, creates 3 synthetic sample PDFs (`tests/make_sample_pdfs.py`), builds the index and runs every test script |

The real research papers are never uploaded to GitHub, which is why CI uses generated sample PDFs.

## Generated files

Files that are created again and again stay out of the project folders:

Everything that is generated again and again goes into one folder, `.cache/`:

```
.cache/
|-- pycache/   Python cache files for app.py, src/, tests/ and scripts/ (same layout as the project)
|-- ruff/      ruff cache
`-- mypy/      mypy cache
```

- Python normally creates a `__pycache__` folder next to every `.py` file. `scripts/configure_venv.py` (run by the setup scripts) installs a small helper into the venv that writes this project's cache files to `.cache/pycache/` instead. It works for every run with the venv's Python: the app, the tests and your editor. Libraries keep their own caches inside `venv/`, so startup is just as fast.
- ruff and mypy write their caches to `.cache/` (set in `pyproject.toml`).
- CI fails if a `__pycache__` folder ever appears outside `venv/`.
- You can delete `.cache/` at any time; it is created again when needed.
- `index/` holds the generated search index, and `data/` holds your PDFs. All of these are ignored by git.

## Screenshots

![Dashboard](docs/screenshot.png)

Screenshot coming soon.

## License

Copyright (c) 2026 Tanmay Singh. All rights reserved. No one may use, copy, modify or distribute this project without written permission. See [LICENSE](LICENSE).
