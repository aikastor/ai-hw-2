# KSTU sources and semantic chunks

The selected corpus is ready for retrieval development. Task 01 completes chunking for this limited reviewed selection. Full assignment coverage remains incomplete. Current answers are supported for seven topics within the audiences below. General enrolled-student GPA, retakes and academic leave remain archive-only because operative applicability is unresolved.

Chunking reused saved extraction, prior recognition, reviewed Markdown tables, and the enrichment overlay dated 20 October 2026. The earlier enrichment crawl is separate. This implementation acquired no university sources and ran no crawler, extraction or OCR. Only the lightweight tokenizer package and its vocabulary were downloaded for setup. No embeddings, vector database, chatbot or Ragas run was created.

## Setup and exact commands

Run from `/Users/aika/study/ai-homework-2`. Tested with Python 3.14.7. The chunking environment imports standard-library modules and pinned `tiktoken`, without the heavy OCR environment.

```sh
python3 -m venv rag-kstu/.venv
rag-kstu/.venv/bin/python -m pip install -r rag-kstu/requirements-chunking.txt
rag-kstu/.venv/bin/python rag-kstu/scripts/prepare_sources.py
rag-kstu/.venv/bin/python rag-kstu/scripts/build_chunks.py
rag-kstu/.venv/bin/python rag-kstu/scripts/prepare_questions.py
rag-kstu/.venv/bin/python rag-kstu/scripts/validate_chunks.py --check-determinism
rag-kstu/.venv/bin/python -m unittest discover -s rag-kstu/scripts -p test_chunks.py -v
```

After package installation, rebuilding and validation work offline. The checked-in tokenizer vocabulary is at `tokenizer/9b5ad71b2ce5302211f9c61530b329a4922fc6a4`. Its SHA256 is `223921b76ee99bde995b7ff738513eef100fb51d18c93597a113bcffe865b2a7`. Missing or corrupt vocabulary causes failure instead of an implicit download. `requirements-chunking.txt` pins tiktoken 0.12.0 and its transitive dependencies. `cl100k_base` counts actual tokens and is suitable for the later OpenAI text-embedding-3 path. An alternative embedding tokenizer requires a deliberate rebuild and new measurements.

`prepare_sources.py` rechecks the four recorded shortlist input hashes, original and extraction hashes, review packet hashes and selected block hashes. All four frozen shortlist inputs matched. `shortlist-snapshot.json` records the reconciliation. This is a new local allowlist overlay; earlier collection, recognition, eligibility, task and audit artifacts were preserved.

## Corpus inventory

The allowlist contains nine distinct original hashes. Eight contribute chunk text. The repeat-learning policy is cover/context evidence only and emits no body. Five sources contribute current chunks, three contribute archive chunks. Duplicate acquisitions retain their source references under `acquisition_provenance`; hashes are selected once without merging different document versions or audiences.

There are 32 semantic selections, 30 current chunks and 5 archive chunks. `source-manifest.json` owns every source title, official URL, extraction path/hash, page/block or reviewed-passage reference, character slice, recognition decision, applicability, audience and category. The builder reads that manifest exclusively. Findings summaries are not source text.

Current material consists of master's admissions rules with cover authority, the Tokmok branch checklist with its graphic-design ORT exception, selected calendar associations, and the two institute-specific tuition schedules. Master's admission GPA is `prospective student` and uses topic `admission_gpa`; it does not close the general `gpa` gap. Applicant tuition tables use `prospective student` with `current student` as an additional category. General policies are `current student`, and calendar records are `calendar`. Section-level mappings are explicit selection records, not keyword guesses.

Every PDF reference uses its one-based physical page. Repeated context is a contributing reference, so master's chunks begin with cover page 1 and also retain their answer-bearing pages 2–4 in `citations` and `body_page_number`. PDF citation URLs include `#page=N`. The resolver also supports HTML with a null page and unchanged official URL; this selected corpus contains no HTML chunks.

## Coverage and fallback behavior

Every topic is partial at university-wide scope. Seven have current scoped support. The other three contain published archive evidence only. Each record in `coverage.json` identifies exact selections, pages/blocks, audiences, year/effective evidence, remaining gap, next action and a fallback question.

| Required topic | Current answer scope | Remaining gap |
| --- | --- | --- |
| Retakes | None | Confirm operative policy and amendments; distinguish exam retakes from repeated study. |
| General GPA | None | Confirm current policy and reconcile grade conversion and denominator exclusions. |
| Academic leave | None | Confirm operative authority and amendments. |
| Admissions documents | Master's 2026–2027; selected Tokmok checklist | University-wide bachelor checklist and other audiences. |
| Admissions thresholds | Master's competition GPA 2.33 grant / 2.18 fee-paying | Current bachelor ORT order and all exceptions. |
| Tuition | Selected logistics/railway programmes, citizenship groups, course columns and study modes | Other institutes, audiences and unapproved continuations. |
| Grants | Master's related-field/first-education conditions, contract categories, exceptions and confirmation | Bachelor's eligibility, individual entitlement and vacancies. |
| Examination periods | Four selected full-time bachelor/specialist calendar entries | Other audiences and unselected entries. |
| Course registration deadlines | Six selected calendar windows | Other audiences and exact clock times. |
| Holidays | Eight selected university-calendar associations | Other audiences; this is not independent legal holiday evidence. |

Questions outside those scopes must receive the assignment's exact fallback.

> Unfortunately, I do not have accurate information on this question. Please contact the Student Office (room 101).

Room 101 is the assignment's required template, not a verified KSTU office location.

## Semantic boundaries, tables and overlap

The adapter declares complete clauses, policy continuation dependencies, calendar grid/label associations and paired programme/per-credit rows as indivisible units. Clause 3.3 of the retake rules retains both physical pages 7–8. General GPA retains the complete special-grade exceptions. Master's grant conditions retain related-field, first-education, foreign-treaty and confirmation conditions together. Tokmok's checklist retains its ORT exception. Source text is selected verbatim rather than paraphrased.

Tuition tables repeat approvals, year, currency in som, institute, citizenship restrictions, study mode and column headers. Programme rows stay with their per-credit rows. Blank cells remain blank. Markdown headers and rows are contiguous. Repeated context has its own citations and is excluded from semantic overlap.

The observed distribution is 19 chunks below 500 tokens, 14 within 500–1,000, and 2 above 1,000. Minimum is 173 and maximum is 1,328. Short chunks are mostly complete calendar associations and the Tokmok checklist. Merging them would mix distinct event/dependency selections; no text was added to pad them. Master's grants are 1,315 tokens and general GPA with exceptions is 1,328; both retain required qualifications instead of splitting them away. Every exception appears in `build-stats.json` and on its chunk.

There are three adjacent chunk boundaries within a selection. The railway table shares one complete programme/per-credit pair, 108 tokens divided by the preceding 900-token chunk, or 12.0%. Master's document requirements and retake-rule boundaries have zero semantic overlap because no complete trailing unit fits both the overlap range and next chunk's size. Each records that exception. Different selections do not overlap. These results establish measured, limited compliance, not universal adherence to the size/overlap recommendation.

## Exclusions and deferred work

`exclusions.json` records 82 exclusions. These account for unselected pages/blocks of the nine overlay sources and all other shortlist candidates. The old administrative calendar, the historical threshold document, pending national procedures, undated checklists and discovery directories do not enter current output. The unreviewed portions of otherwise selected documents remain excluded. Unselected brochure programmes, marketing material, contacts and its Kyrgyz page are also excluded; bilingual equivalence is not asserted.

The old undated and historical sources were not promoted or re-chunked merely because they were shortlisted. The selected archive output deliberately contains only the reviewed policy evidence needed by this task. No further repair or acquisition was performed. The concrete next actions remain in the coverage records.

## Verification and handoff cases

`validation.json` records the actual validation outcome, artifact hashes, selection accounting and determinism result. The validator independently reconstructs source text and checks eligibility, source/page metadata, category/audience mappings, token counts, overlap measurements, tables, question references and exclusions. Its determinism mode builds twice into temporary directories and compares ordered JSONL bytes, including IDs, plus build statistics. The focused tests use the real selected documents and negative controls rather than placeholder-only evidence.

An independent source-scope review found no concrete correctness findings. It checked master's authority dependencies, policy exceptions and continuation, tuition row pairs and Markdown, calendar association scope, page references, archive isolation and exclusions. The final validator run returned `status: passed`, with zero unaccounted selected units. All 13 focused tests passed. Two fresh builds and the saved corpus matched byte for byte, including ordered IDs and content.

`evaluation/questions.jsonl` contains 30 handoff cases with verified expected answers, evidence fragments and expected original/page references. Ten are refusals and five are table lookups. All ten required topics appear. This dataset is preparation for retrieval development, not evidence of retrieval accuracy or Ragas performance. Question reference IDs cite body pages as well as applicable authority dependencies.

The implementation applies Model the Domain through explicit semantic selection records, Build the Lever through rerunnable source/chunk/question scripts, and Prove It Works through artifact reconstruction, real-source checks and byte-identical reruns. These choices keep applicability decisions inspectable and prevent keyword-driven category assignment.

Observed command results on 20 October 2026 were as follows.

```text
prepare_sources.py
Prepared 9 source identities and 32 selections; 82 exclusion records. Frozen shortlist inputs match.

build_chunks.py
{"archive": 5, "current": 30}

prepare_questions.py
Wrote 30 grounded handoff cases, including 10 refusals and 5 table lookups.

validate_chunks.py --check-determinism
status: passed
selected_unit_count: 57
unaccounted_selected_units: 0
Two fresh builds and saved corpus are byte-identical, including ordered IDs and content.

unittest discover -s rag-kstu/scripts -p test_chunks.py -v
Ran 13 tests
OK
```

The independent artifact review found no concrete source-scope issues. No retrieval or generation behavior was evaluated at this stage. The throughput checkpoint and design choice are recorded in [the design note](../.audit/chunking-design.md). There are no open implementation decisions for task 01; the evidence gaps listed above remain research work for full coverage.
