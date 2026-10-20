# Grounded chat verification

Status on 20 October 2026 is **in progress**. The local FastAPI and Streamlit services run, but this is not a completed assignment or a published repository.

The backend uses Groq `openai/gpt-oss-120b`, selected from the account's actual model listing. A minimal strict JSON-schema completion returned HTTP 200. The documented model supports 131,072 context tokens and strict structured output. Parameters are temperature 0, reasoning effort low and maximum completion length 2,000 tokens. No tools, external search or alternate provider is enabled. The account returned a limit of 8,000 tokens per minute. There is one bounded rate-limit retry, and provider calls have timeouts and bounded concurrency.

Official references checked during implementation are [chat completions](https://console.groq.com/docs/text-chat), [models](https://console.groq.com/docs/models), [GPT-OSS 120B](https://console.groq.com/docs/model/openai/gpt-oss-120b) and [structured output](https://console.groq.com/docs/structured-outputs).

## Observed local behavior

The existing 13 source tests and 24 real retrieval tests passed. The chat contract tests cover typed validation, exact refusal, missing audience, history isolation, one-thread Qdrant ownership, clean mock shutdown, complete chunks, malformed generation, invented citations, numbers, provider failures and bounded retries. Package tests reject unsafe paths, symlinks, missing files, hash drift, secrets and existing destinations.

Both `/health` and Streamlit's health route returned HTTP 200. The interface was opened in Chrome and Safari. Safari displayed the exact fallback for a general enrolled-student GPA question. A supported master's state-grant threshold returned an answer of 2.33 with citations through the real API after quotation constraints were added.

Initial generation checks exposed false refusals. The model combined source lines, changed whitespace or inserted ellipses into quotations. Generation now selects short server-owned quotation handles in its JSON schema. The server reconstructs exact source lines and rejects mismatched source/handle pairs. This replaces the unreliable attempt to make the model copy long source lines verbatim. A separate verification call checks entailment, audience, conditions and completeness. Local checks verify eligible IDs, quotations, numbers and server-owned citation metadata. Whitespace-only quote transcription can be recovered from the original chunk; evaluation stores the resulting exact source substring.

The user subsequently authorized source expansion. The student-facing audience selector has been removed. A separate expanded index now contains 69 chunks, including 39 additions for programme tables, applicant checklists and published academic policies. The original corpus and index remain intact. Independent review checked all 114 programme rows across 12 institutes, five applicant groups, PDF policy clauses and the updated appeal deadline. The catalogue mixes bachelor and specialist qualifications; generated examples must preserve qualification and institute.

## Evaluation and remaining gates

`generation-final.jsonl` was frozen before tuning and has 26 new English/Russian cases, including six table cases, unsupported policies, ambiguities, follow-ups and instruction attacks. The bilingual retrieval set remains reused development evidence. The first handoff evaluation was interrupted after it exposed false refusals. Its results are development evidence and do not establish a passing generation score.

Full handoff, bilingual and frozen generation evaluation, source audit of every accepted claim, two browser-session isolation, citation navigation and fresh-clone end-to-end checks remain pending until recorded in `evaluation/verification.json`. No always-refuse success claim is made. Rate-limit and provider configuration errors have been observed as service errors, separate from the university-evidence fallback.

Model-based support verification is probabilistic. Exact quotations and valid citations cannot prove entailment or complete applicability. Table numbers must keep programme, institute, course, nationality, mode, som currency and year. Manual source review remains required before reporting supported-answer accuracy.

## Privacy and delivery

Only selected evidence and bounded supplied user history go to hosted Groq. Embeddings remain local Ollama bge-m3. Runtime/version/model digest checks and the original Qdrant index are preserved. Access logging is disabled in the documented API command. Credentials, provider account records and full prompts are excluded from routine logs and the package. Evaluation fixtures contain authored test questions, not personal student data.

The exporter uses a strict allowlist plus all 39 hash-pinned manifest inputs, preserving sibling `data/` paths and bytes. The largest pinned input is about 59 MB and is below GitHub's 100 MiB file limit. It does not copy the original Qdrant index, weights, virtual environments or audit transcripts.

GitHub publication is deferred at the user's request to run and verify locally first. `gh` is installed but unauthenticated. No remote repository or upload is claimed. Ragas and defense remain stage 5. Published policy explanations now have reviewed evidence for retakes, enrolled-student GPA and academic leave. Current university-wide bachelor ORT thresholds and grant quotas remain unverified; the central applicant checklist is undated. Full legal non-repeal and individual eligibility are not established by the published-policy review.

## Expanded verification update

The expanded source tests pass 10 cases, retrieval regression passes 24, chat contracts pass 34, and package tests pass five. A standalone export verifies 113 files and independently validates all 69 chunks. Seven expanded live smoke cases are development checks and are being rerun after source-reference and rate-limit fixes; they are not a final held-out score. Initial runs exposed both provider 429 responses and verifier false refusals despite correct retrieved programme evidence. These failures are retained in the local audit; do not interpret quote/citation validity as answer success.

## Response behavior override — 20 October 2026

The user removed the fixed English fallback requirement. Missing evidence now receives a localized explanation tied to the failure reason, without an unverified office referral. Malformed provider output is a service failure. Historical exact-refusal scores belong to the former contract; new evaluation uses refusal status, absent citations, a recorded reason and manual review of the explanation.
