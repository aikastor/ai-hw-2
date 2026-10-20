# Build and verify local retrieval

Completed on 20 October 2026. See [the handoff report](../data/RETRIEVAL-REPORT.md), [validation](../data/retrieval-validation.json), and [evaluation](../evaluation/retrieval-results.json). This is a retrieval baseline; generation and semantic refusal remain later work.

Stage 2 consumes the validated current KSTU chunks. Preserve source text, tables, audience restrictions, years, authority dependencies and citations. Do not acquire documents, run OCR, include archives, generate answers or build a chat interface.

Build local multilingual embeddings through Ollama (`bge-m3`, exact digest pinned) and persist vectors in Qdrant. Add BM25 keyword search and reciprocal-rank fusion, deduplicating semantic parent chunks before fusion. Use category, explicit audience scope, academic year and topic filters consistently in both ranking branches. Unsupported explicit filters return no evidence.

Use a model tokenizer for embedding limits. Every original character must be submitted to the embedding model. The selected Ollama model accepts complete selected chunks; request `truncate: false` so overflow is rejected rather than silently dropped. Keep the reviewed semantic chunks unchanged; return full chunks and their citations after ranking.

Pin dependencies, model revision and artifact hashes. Detect stale corpus/model/index data. Provide offline reruns after one-time setup, focused real-corpus tests, an independent review, and a retrieval evaluation that does not leak expected answers or source-selection labels into search filters.

Report hit rate, reciprocal rank and evidence fragment coverage for BM25, dense and hybrid search. Separate explicit metadata isolation from semantic answerability. Raw similarity search is not a refusal classifier. The 30 existing handoff cases are development evidence; use a separate frozen query set before the first retrieval run and do not tune ranking to it.

The user has a Groq key available for possible later generation. Its account preflight could not access the SDK embedding models. Stage 2 therefore uses local Ollama embeddings and does not require or read that key. The prior E5/ONNX baseline is retained under `.audit/retrieval-e5-baseline/`. The exact implementation commands and observed results belong in `data/RETRIEVAL-REPORT.md`.
