# Assignment status — 20 October 2026

The local FastAPI and Streamlit application is implemented. Source expansion and live generation verification are in progress; the assignment is not yet fully verified. GitHub publication is deferred at the user's request to verify locally first.

## Implemented and checked

- Reviewed expanded corpus: 69 current chunks, including the unchanged 30 original chunks. Five archive chunks remain excluded. Original index remains available for rollback.
- HTML extraction preserves 114 programme rows across 12 institutes and five separate applicant checklists. The programme page covers bachelor and specialist qualifications; answers must preserve this distinction.
- Independently reviewed PDF passages support explanations of published 2025 retake, GPA and academic-leave rules. The separately published 2026 appeal deadline replaces the conflicting older clause in the new selection. This is not a certification of non-repeal or individual eligibility.
- Separate local Qdrant index rebuilt with the same pinned Ollama bge-m3 model, 1,024 dimensions. BM25 and dense retrieval remain combined with reciprocal-rank fusion.
- Typed FastAPI endpoints, Streamlit chat, server-generated PDF/HTML citations, hosted Groq generation and independent support checking are implemented.
- Ten expansion tests, 24 retrieval tests and five package tests pass. Chat checks are recorded in the chat report as the implementation evolves.
- A standalone expanded export verifies all 113 inventory entries and reconstructs 69 current chunks using only its own evidence files.

## Remaining gates and gaps

Live answers and browser checks are still being verified. The original frozen generation set belongs to the original corpus: its policy-refusal labels must not be reported as current expanded-corpus expectations. New expanded smoke cases are development checks, not a blind final evaluation.

Current university-wide bachelor ORT thresholds and grant quotas remain unverified. The central applicant checklist is published without an intake year. Tuition remains limited to the reviewed institute, audience, course and study-mode combinations. GPA evidence supports the published weighted formula, not a complete grade-conversion calculator.

Full source-checked generation evaluation and expanded fresh-clone API/UI verification remain outstanding. Ragas and the defense remain stage 5. See [chat report](data/CHAT-REPORT.md), [expanded source manifest](data/expanded/source-manifest.json) and [verification record](evaluation/verification.json).
