# KSTU retrieval with Ollama embeddings

The embedding migration is complete. Retrieval now uses `bge-m3:latest` through the local Ollama API, followed by persistent Qdrant, BM25 and reciprocal-rank fusion. The index contains 30 current chunks and 30 vectors of 1,024 dimensions. Five archive chunks remain excluded. The reviewed source chunks and citations were preserved.

This follows the assignment's local Ollama embedding path. The embedding model is dedicated to retrieval; Llama/Mistral answer generation, FastAPI application endpoints, chat UI and Ragas remain later stages. No university crawling, OCR or extraction was performed during this migration.

## Installed runtime and model

Ollama 0.40.6 is installed under `rag-kstu/tools/ollama/`. Its official macOS release archive is pinned to SHA256 `b2b55434865a668decb494110d7fd970eed3ecc8837be2872f672ccbb95df974`. The server listens on `127.0.0.1:11434`, stores models in `rag-kstu/models/ollama/`, and starts with `OLLAMA_NO_CLOUD=1`. No global Homebrew package, system startup service or PATH modification was needed.

The embedding model digest is `7907646426070047a77226ac3e684fbbe8410524f7b4a74d02837e43f2146bab`. `models/ollama-embedding.json` records that identity, runtime version, 1,024 dimensions and 8,192-token context. Setup checks the pinned runtime and model digest before writing configuration. Runtime retrieval checks version/digest before and after every embedding batch and rejects changes.

The [Ollama model page](https://ollama.com/library/bge-m3) describes BGE-M3 as a multilingual embedding model supporting more than 100 languages and an 8K context. Its download is about 1.2 GB. The old E5/ONNX inference code and dependencies have been removed from the active retrieval path. The earlier index, code, reports and evaluation results remain under `.audit/retrieval-e5-baseline/` for comparison.

## Exact setup and rerun commands

Run from `/Users/aika/study/ai-homework-2`. Python 3.13.2 was used. `requirements-retrieval.txt` pins the Python dependencies. The runtime and model are separate downloads, ignored by Git.

One-time setup:

```sh
python3.13 -m venv rag-kstu/.venv-retrieval
rag-kstu/.venv-retrieval/bin/python -m pip install -r rag-kstu/requirements-retrieval.txt
rag-kstu/.venv-retrieval/bin/python rag-kstu/scripts/setup_ollama.py install
```

Start the server in one terminal and leave it running. The server is already running at the end of this implementation session; do not start a second copy on the same port.

```sh
rag-kstu/.venv-retrieval/bin/python rag-kstu/scripts/setup_ollama.py serve
```

In another terminal:

```sh
rag-kstu/.venv-retrieval/bin/python rag-kstu/scripts/setup_ollama.py pull
rag-kstu/.venv-retrieval/bin/python rag-kstu/scripts/retrieval.py build
rag-kstu/.venv-retrieval/bin/python rag-kstu/scripts/retrieval.py search \
  'Какой минимальный GPA нужен для гранта в магистратуру?' \
  --scope masters_admissions --top-k 3
rag-kstu/.venv-retrieval/bin/python -m unittest discover \
  -s rag-kstu/scripts -p test_retrieval.py -v
rag-kstu/.venv-retrieval/bin/python rag-kstu/scripts/evaluate_retrieval.py
```

After setup, embedding, indexing, search, tests and evaluation use the local API without a cloud key. Stop the foreground server with Ctrl+C when it is no longer needed. The installer targets macOS; other systems need their own Ollama installation at the pinned version. The former `download_embedding_model.py` command has been replaced by `setup_ollama.py`.

## Input completeness and stored state

Ollama receives each complete selected chunk through `POST /api/embed` with `truncate: false` and `num_ctx: 8192`. Oversized input therefore fails instead of being shortened. The current corpus fits. The response must contain one finite, unit-normalized vector of the expected dimension for every input, and the expected model name. Requests are batched in groups of four. No E5 query/passage prefixes or ONNX tokenizer remain.

`windows.jsonl` now records one full original character span per parent, with exact source-text SHA256 and server truncation enforcement. It does not invent local tokenizer counts. All original text, final qualifications, table rows, audience restrictions and citations remain attached to the returned parent chunks.

The Qdrant index lives in `data/retrieval/`. Its schema-2 manifest pins corpus/source-manifest/config hashes, runtime/model identity, settings, stored artifact hashes and the current stored-vector fingerprint. A fingerprint verifies that saved artifact; it is not a promise that GPU floating-point results from separate builds are byte-identical. Rebuild tests check stable IDs/config identity and vector direction with cosine similarity above 0.9999.

Protected source/model paths and unrelated index-directory files cannot be replaced. A sibling lock prevents rebuilding an active index. Publication uses a backup directory and restores the old index if either rename raises an ordinary error or KeyboardInterrupt. Tests inject both interruption points. This is a rollback-protected swap, not a power-loss/crash-atomic publication guarantee. Local Qdrant uses one active client per storage directory; a multi-process deployment needs a Qdrant server.

## Retrieval and scope

Dense search uses cosine similarity. BM25 uses Unicode lowercase words and positive Okapi IDF `log(1+(N-df+0.5)/(df+0.5))`. Hybrid search fuses deduplicated parent rankings with RRF `k=60`, using stable chunk-ID tie breaks. Corpus text and BM25/RRF parameters were not changed to improve the evaluation results.

Both ranking branches enforce KSTU identity, current eligibility, exact academic year and the requested filters. Category matches the primary or reviewed additional categories. CLI options are `--mode bm25|dense|hybrid`, `--category`, `--academic-year`, `--scope`, `--topic` and `--top-k`. `--embedding-config` selects the pinned configuration file; there is no old `--model-dir` backend.

| Scope | Reviewed evidence |
| --- | --- |
| `masters_admissions` | Master's documents, GPA competition, grant conditions and admission GPA appendix. |
| `tokmok_admissions` | Tokmok checklist with its graphic-design ORT exception. |
| `logistics_tuition` | Selected logistics nationality and study-mode tables. |
| `railway_tuition` | Selected railway Kyrgyz-citizen full-time table. |
| `calendar_fulltime_bachelor_specialist` | Selected full-time bachelor/specialist calendar associations. |

These are explicit caller scopes. They do not infer nationality, programme or study-mode eligibility from free text. Applicable restrictions remain in each chunk and must be checked before answering. An unknown explicit scope, unsupported topic, or unavailable year returns no evidence. An unscoped question may return unrelated candidates with `answerability: not_assessed`; retrieval is not a semantic refusal classifier.

## Observed verification and evaluation

A real API smoke request returned HTTP 200, model `bge-m3:latest`, 1,024 dimensions and unit norm. The rebuilt index contains 30 eligible parents and 30 points. The focused suite uses actual Ollama and local Qdrant as well as small mocks for malformed responses and deliberate drift. It verifies complete parent text, citations and table tails, real overflow rejection, archive isolation, categories, scope/year/topic filters, RRF, vector/config drift, unavailable runtime errors, protected paths, active-index locks, rollback and repeated-build vector direction.

All 24 focused tests passed on the final implementation. The final validation artifact is [retrieval-validation.json](retrieval-validation.json). An independent review accepted the migration after the per-batch identity and interruption-recovery findings were fixed. Its evidence trail is under `.audit/ollama-*`.

The same fixed question sets were rerun without passing expected selections, source IDs, answers, audience labels or refusal sentinels as filters on answerable cases. The set called `heldout` in the data was originally frozen before the first E5 run; it is now a reused bilingual regression set, not a fresh blind test. Its query and gold labels were not changed during this migration.

| Set | Mode | Hit@1 | Hit@5 | MRR@5 | Evidence fragment recall@5 |
| --- | --- | ---: | ---: | ---: | ---: |
| English handoff, 20 answerable | BM25 | 5% | 15% | 0.100 | 15% |
| English handoff, 20 answerable | Dense | 50% | 80% | 0.625 | 80% |
| English handoff, 20 answerable | Hybrid | 50% | 80% | 0.621 | 80% |
| Bilingual regression, 12 answerable | BM25 | 75% | 83.3% | 0.778 | 83.3% |
| Bilingual regression, 12 answerable | Dense | 83.3% | 91.7% | 0.875 | 91.7% |
| Bilingual regression, 12 answerable | Hybrid | 100% | 100% | 1.000 | 100% |

Hybrid misses in the English handoff are `masters-fee-confirmation`, `masters-foreign-exception`, `winter-exam` and `summer-exam`. English hybrid Hit@5 is 16/20, compared with 17/20 for the previous E5 baseline. Bilingual hybrid Hit@1 is 12/12, compared with 11/12 previously. These small-set tradeoffs do not establish one model as universally better. The migration establishes the requested Ollama serving path, not a production-accuracy claim.

All six explicit metadata-isolation cases pass for each mode. Dense and hybrid still return candidates for all ten unsupported raw handoff questions. Generation must verify applicability and use the exact assignment fallback when evidence is absent or inapplicable. Full topic/audience gaps remain in [coverage.json](coverage.json).

Per-case results are in [retrieval-results.json](../evaluation/retrieval-results.json). No generation, Ragas, latency benchmark or production-service test was performed. Room 101 remains an assignment template, not a verified office location.

## Provider and handoff notes

Groq's official SDK includes an embedding interface, but the supplied account's earlier preflight returned `model_not_found` for both SDK Nomic model IDs. That record remains in [groq-preflight.json](groq-preflight.json). Current embeddings use no Groq key and do not send corpus text to Groq. A later generation task can use a locally served Llama/Mistral model to keep the full Ollama path, or explicitly document a different hosted provider choice.

Model the Domain keeps pinned embedding identity separate from unchanged reviewed source chunks. Prove It Works is implemented through real API/index tests, source-text reconstruction and stored-artifact checks. The independent workstreams were runtime setup, staged engine migration, staged tests and read-only review; the root alone published the final index and reports.
