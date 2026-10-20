# Run the KSTU grounded chat

The application answers questions from the reviewed KSTU corpus for 2026-2027. It uses local Ollama bge-m3 embeddings, Qdrant hybrid retrieval, FastAPI, Streamlit and Groq hosted generation. Groq receives selected source passages and supplied conversation messages. This configuration is not fully private.

The expanded corpus adds the official 2026–2027 programme catalogue, separately scoped admissions checklists, and reviewed passages on GPA, retakes, academic leave and appeals. The catalogue includes bachelor and specialist programmes; not every row is a bachelor programme. Academic policy answers must identify the published policy year, and the admissions checklist is undated. Current 2026 bachelor ORT thresholds and grant quotas remain unverified. Tuition covers only reviewed logistics and railway groups. [Base source coverage](data/coverage.json) and the [expanded source manifest](data/expanded/source-manifest.json) record the evidence and limits.

## Install the application

Clone the repository first:

```sh
git clone https://github.com/aikastor/ai-hw-2.git
cd ai-hw-2
```

Run commands from the standalone repository root, which contains both `rag-kstu/` and `data/`. Python 3.13 is the verified environment. The pinned Ollama installer supports macOS. Another operating system needs the same Ollama version and bge-m3 digest installed separately.

You need your own Groq API key, internet access for installation and hosted answers, and disk space for Python dependencies and the embedding model (about 1.2 GB for the model alone). macOS is the tested platform; Linux and Windows execution has not been verified.

```sh
python3.13 -m venv rag-kstu/.venv-retrieval
rag-kstu/.venv-retrieval/bin/python -m pip install -r rag-kstu/requirements-chat.txt
cp rag-kstu/.env.example rag-kstu/.env
```

Set `GROQ_API_KEY` in the ignored `rag-kstu/.env`. The selected model is `openai/gpt-oss-120b`. No credentials belong in Git or frontend settings. The backend checks the configured model rather than silently switching providers or models.

Install the pinned Ollama runtime once.

```sh
rag-kstu/.venv-retrieval/bin/python rag-kstu/scripts/setup_ollama.py install
```

Start Ollama in a terminal and leave it running. If the pinned service is already running at `127.0.0.1:11434`, reuse it.

```sh
rag-kstu/.venv-retrieval/bin/python rag-kstu/scripts/setup_ollama.py serve
```

In another terminal, download the pinned embedding model and build this checkout's local index. Run these commands before starting FastAPI. Do not copy an index from another checkout because its manifest contains an absolute corpus path.

```sh
rag-kstu/.venv-retrieval/bin/python rag-kstu/scripts/setup_ollama.py pull
rag-kstu/.venv-retrieval/bin/python rag-kstu/scripts/retrieval.py build --chunks rag-kstu/data/expanded/chunks.current.jsonl --index rag-kstu/data/retrieval-expanded
```

The model and runtime pins are in [the retrieval report](data/RETRIEVAL-REPORT.md). A fresh clone needs the packaged reviewed evidence, tokenizer and expanded chunks. It does not need crawling, OCR or re-chunking.

## Start the API and chat

Launch one API worker. One dedicated executor owns the Retriever, including its construction and shutdown. Multiple workers cannot open the same local Qdrant directory.

```sh
KSTU_INDEX="$PWD/rag-kstu/data/retrieval-expanded" PYTHONPATH=rag-kstu rag-kstu/.venv-retrieval/bin/python -m uvicorn app.api:app --host 127.0.0.1 --port 8000 --workers 1 --no-access-log
```

The explicit `KSTU_INDEX` selects the expanded index. The original corpus and index remain available for baseline checks.

Launch Streamlit in another terminal.

```sh
rag-kstu/.venv-retrieval/bin/python -m streamlit run rag-kstu/app/frontend.py --server.address 127.0.0.1 --server.port 8501 --server.headless true
```

Open http://127.0.0.1:8501. API readiness is at http://127.0.0.1:8000/health, and the typed request contract is at http://127.0.0.1:8000/docs.

Use Ctrl+C in each server terminal to stop Streamlit, FastAPI and Ollama. After editing a prompt, restart FastAPI: prompts are loaded at process startup. If Qdrant reports that storage is already accessed, stop the other API or retrieval process using that index; do not delete its storage.

Try these questions.

- What GPA minimum permits competition for a masters state-grant place?
- What is first-year full-time Logistics bachelor tuition for Kyrgyz citizens in 2026-2027?
- Какие программы доступны после школы?
- How is GPA calculated according to the published academic policy?

When reviewed evidence is missing, the app explains the limitation in Russian or English according to the question and suggests what information would help. It does not invent a contact or office location. The user superseded the original fixed-English-fallback requirement on 20 October 2026. Malformed provider output is a service error, not evidence that university information is unavailable.

Supported responses show clickable official source titles, with physical pages for PDF evidence and page links for HTML evidence. Missing audience information can produce a clarification. Provider, Ollama and index outages produce retryable service errors. The UI preserves validated turns in the browser session. **Reset conversation** clears the conversation.

## Verify behavior

Stop FastAPI before running standalone commands against its index. The source tests do not require Groq. Retrieval tests require the pinned Ollama service.

```sh
rag-kstu/.venv-retrieval/bin/python -m unittest discover -s rag-kstu/scripts -p test_chunks.py -v
rag-kstu/.venv-retrieval/bin/python -m unittest discover -s rag-kstu/scripts -p test_retrieval.py -v
PYTHONPATH=rag-kstu rag-kstu/.venv-retrieval/bin/python -m unittest discover -s rag-kstu/scripts -p test_chat.py -v
rag-kstu/.venv-retrieval/bin/python -m unittest discover -s rag-kstu/scripts -p test_package_repository.py -v
rag-kstu/.venv-retrieval/bin/python -m unittest discover -s rag-kstu/scripts -p test_expanded_sources.py -v
```

Validate determinism without overwriting the earlier source report.

```sh
PYTHONPATH=rag-kstu/scripts rag-kstu/.venv-retrieval/bin/python -c "from validate_chunks import validate; print(validate('rag-kstu/data/source-manifest.json','rag-kstu/data',True))"
```

Validate the expanded corpus against its pinned sources without re-chunking.

```sh
rag-kstu/.venv-retrieval/bin/python rag-kstu/scripts/expanded_sources.py validate
```

Start the API again before HTTP generation evaluation. The original evaluation sets describe the base corpus. Run the expanded development smoke cases against the expanded API. These cases are not a held-out evaluation.

```sh
rag-kstu/.venv-retrieval/bin/python rag-kstu/scripts/evaluate_chat.py --cases rag-kstu/evaluation/expanded-smoke.jsonl --chunks rag-kstu/data/expanded/chunks.current.jsonl --output rag-kstu/evaluation/expanded-smoke-results.json
```

Evaluation saves evidence, claims, exact quotations, decisions, citations and usage. Gold labels are never sent to the chat endpoint as retrieval filters. The bilingual retrieval set is reused development evidence. The separate generation set was frozen before prompt tuning. A passing quotation check alone does not establish semantic support. Read the actual source audit and incomplete checks in [the chat report](data/CHAT-REPORT.md).

The account's observed Groq limit is 8,000 tokens per minute. Two-pass claim generation and verification can take longer under that limit. Retries and concurrent provider requests are bounded. There is no streaming of unvalidated claims.

## Export a standalone repository

The exporter preserves every manifest-pinned input at its original relative path. It rejects missing files, hash drift, traversal paths, symlinks, credential patterns, oversized files and an existing destination. It excludes secrets, caches, audit transcripts, model weights and generated indexes.

```sh
rag-kstu/.venv-retrieval/bin/python rag-kstu/scripts/package_repository.py /tmp/rag-kstu-export
cd /tmp/rag-kstu-export
python3 rag-kstu/scripts/verify_package.py
```

The package inventory lists hashes of selected repository files. University documents remain third-party materials. See [attribution](ATTRIBUTION.md).

Repository destination: https://github.com/aikastor/ai-hw-2. Ragas evaluation and project defense remain stage 5. Source-coverage research remains separate. See [Russian validation questions](evaluation/validation-ru.md) for manual checks; these are expected behaviors, not a claim that every case passes.
