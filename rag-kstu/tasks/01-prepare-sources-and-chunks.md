# Build semantic chunks and enrich metadata

Completed for the reviewed limited corpus on 20 October 2026. See the [handoff report](../data/REPORT.md) and [validation results](../data/validation.json). Full assignment coverage remains incomplete.

Build the corpus for the single-university assistant described in [the assignment](../../task.md). Run commands from the repository root. Put all new artifacts beneath `rag-kstu/`.

This is the next implementation task after the completed enrichment pass. Use saved OCR, extracted text, reviewed Markdown tables, existing eligibility decisions, and the separate enrichment evidence packets. Build and validate chunks from the usable evidence now. Keep remaining coverage gaps explicit.

This task completes the chunking portion of `task.md` section 3.1 and stage 1. It ends with validated chunks and a coverage report. Embeddings, vector storage, generation, the chat interface, and Ragas evaluation follow in later tasks.

## Start the implementation

Run this command in a terminal. It starts a Codex implementation session; the chunking scripts do not exist yet.

```sh
codex exec --cd /Users/aika/study/ai-homework-2 --skip-git-repo-check --sandbox workspace-write 'Implement rag-kstu/tasks/01-prepare-sources-and-chunks.md completely. Reuse reviewed OCR and the enrichment evidence packets. Build semantic chunks, assign metadata automatically, run validation and determinism checks, and document the exact rerun commands. Keep new artifacts under rag-kstu. Do not crawl, rerun bulk OCR, create embeddings, or build the chatbot.'
```

If using the IDE chat, paste the quoted instruction instead.

## Scope from task.md

| Assignment requirement | This task's implementation |
| --- | --- |
| Semantic units instead of fixed character counts | Split reviewed source blocks at section, paragraph, clause, and table boundaries |
| Recommended 500–1,000 tokens with 10–15% overlap | Use a named tokenizer, measure actual overlap, and document semantic exceptions |
| Tables converted to Markdown | Reuse reviewed Markdown tables and preserve headers, units, footnotes, and conditions |
| `source`, `category`, `page_number` metadata | Attach validated title, audience category, and physical PDF page metadata to every chunk |
| Academic policy, admissions, and calendar sources | Select existing KSTU evidence and report coverage for all ten required topics |
| Later clickable citations and metadata filtering | Retain official URLs, page/block references, audience, year, and eligibility |

Do not crawl, start bulk extraction/OCR, repair the nationwide corpus, or wait for every required topic to become current. Preserve earlier `data/`, `tasks/`, and `.audit/` files. If a selected source is defective or unavailable, record the exact exclusion and continue with the remaining usable material.

## 1. Establish the input selection

Read these inputs:

- `rag-kstu/UNIVERSITY.md` and `rag-kstu/sources/shortlist.json`.
- `rag-kstu/data/enrichment/REPORT.md`, `rag-kstu/data/enrichment/source-manifest.json`, `rag-kstu/data/enrichment/coverage.json`, and the evidence packets they reference.
- `data/knowledge/selection.json`, `data/knowledge/universities.json`, and `data/knowledge/manifest.json`.
- The original, extraction, and recognition files referenced by the selected records.
- `scripts/extract.py`, `scripts/knowledge.py`, and `scripts/validate_knowledge.py` for reusable formats and validation behavior.

The shortlist contains candidates, including withheld pages. It is not an approved corpus. Check its recorded input hashes against the live files. If the collection has changed, reconcile the new evidence and create a new snapshot within this folder.

Create `rag-kstu/data/source-manifest.json` with an explicit KSTU allowlist. Record each original hash, original path, official URL, extraction path/hash, selected pages and block indices, recognition status, applicability decision, audience, and supporting review evidence.

Reuse complete reviewed text rather than rerunning OCR. Build chunks from the selected extraction blocks, not by splitting the old generated chunk strings again. The existing current/archive chunks are comparison material. Preserve original content and every qualification attached to a rule or table. Exclude unapproved pages and record any repair as deferred work.

The enrichment packets have different shapes. Resolve policy and calendar selections to their referenced extraction blocks. For admissions, use the reviewed text in `masters-passages.json` and `tokmok-p1.txt` with their authority and exception dependencies. Reuse approved tuition Markdown tables through their recorded provenance. Finding summaries are review notes, not source text for chunks.

Keep archive material separate. Reclassify it as current only with explicit evidence of authority and applicability. A 2025 policy can remain operative, but publication age or an undated official link alone does not prove that. The enrichment review supplies a separate, scoped decision for master's rules supported by their reviewed cover; preserve that authority dependency. Policy packets marked `current_answer_eligible: false` remain withheld from current answers. Never treat the whole acquisition directory or every page of a selected document as approved.

Do not run the optional crawler during this task. Record acquisition gaps and continue work on usable saved evidence.

## 2. Record coverage before chunking

Create `rag-kstu/data/coverage.json` with one record per required topic:

- Retakes.
- GPA calculation.
- Academic leave.
- Admissions documents.
- Admissions thresholds.
- Tuition.
- Grants.
- Examination periods.
- Course registration deadlines.
- Holidays.

Use `supported`, `partial`, or `missing`. Each supported claim must identify source pages/blocks, target year or effective period, and the exact audience. Distinguish master's, bachelor's, specialist, college, and doctoral rules. Do not fill KSTU gaps with another university's policies.

For each missing or partial topic, record a concrete next action and an example question that must receive the fallback.

The enrichment snapshot has current scoped evidence for seven topics. Retakes, general GPA, and academic leave have readable published policy evidence but unresolved current applicability. Bachelor's admissions, broader tuition, and other audience gaps remain even where a topic has some current support. Recompute this assessment from selected claims rather than treating the topic count as full coverage.

## 3. Build semantic chunks

Implement a narrow ingestion adapter under `rag-kstu/scripts/` or `rag-kstu/src/`. Use the explicit manifest as its input.

Do not invoke the existing full-corpus builder with only a different output path. It always includes the original collection, and its validator expects the multi-university union.

Use these rules:

1. Split at sections, paragraphs, numbered clauses, and complete logical units. Preserve headings and conditions needed to interpret each unit.
2. Target 500–1,000 tokens with 10–15% overlap where semantic boundaries permit. Use a real tokenizer, record its name/version, and select an embedding-compatible tokenizer for the later retrieval stage.
3. Keep naturally short units when merging would mix sources, audiences, dates, or unrelated rules. Record the exception.
4. Reuse reviewed Markdown table blocks. If a reviewed structured table has no Markdown representation, render its verified cells without rerunning extraction. Preserve headers, row labels, units, footnotes, and audience restrictions.
5. For large tables, split only at complete row groups and repeat their headers and applicable notes. Retain source references for repeated context. If a safe split is impossible, report an oversized unit rather than silently truncating it.
6. Keep exclusions, exceptions, deadlines, and qualifying conditions with the clauses they modify.
7. Do not join text across pages unless every required page/block is approved and the full dependency is verified. Record all contributing page citations.
8. Deduplicate repeated acquisitions without losing their provenance. Never deduplicate away meaningful differences in year, language, audience, or policy version.
9. Produce stable IDs and deterministic ordering. Do not paraphrase or invent source text.

Construct overlap from complete trailing paragraphs or logical units within the same source section and audience. Aim for 10–15% of the preceding chunk's token count. Record actual shared token counts and the denominator. Do not overlap across unrelated sections or documents, or pad short units to meet a target. Count repeated headings and table headers separately from semantic overlap.

Automatically assign metadata while building each chunk:

- Set `source` to the reviewed document or page title from the manifest. Do not use a hash or filename as the displayed title.
- Set `category` to one string: `prospective student` for admissions, admission GPA, grants, and applicant fee tables; `current student` for academic policies and enrolled-student fee rules; or `calendar` for calendar events. Use reviewed section-level mappings where a document has more than one purpose. Store those mappings in the manifest and validate every assignment.
- Copy `page_number` from the physical PDF page reference, starting at 1. For a chunk spanning pages, use its first contributing page and preserve every page in `citations`. Use `null` for HTML.

Assign categories from source purpose and reviewed audience metadata, not isolated keyword matches. General GPA and master's admission GPA belong to different audiences. If another category also applies, record it in an optional `additional_categories` list. Never invent missing titles, audiences, or page references; exclude unresolved selections with a reason.

Each chunk must contain:

- `chunk_id`, `text`, `token_count`, `university_id`.
- `source` as the document or page title, `source_url`, `source_sha256`, and extraction provenance.
- `category` as one of the three exact strings above.
- `topic`, as a list of strings.
- `page_number`, using the one-based physical PDF page or `null` for HTML.
- `citations`, with all contributing pages and block references. For a chunk spanning pages, `page_number` is the first page and `citations` contains every page.
- `academic_year`, effective-date evidence, audience restrictions, and `eligibility` as `current` or `archive`.
- Documented size/overlap exceptions when applicable.

For PDF links, use the official URL with a physical-page fragment where supported. Never invent a page number for HTML. Keep required context citations attached so later retrieval can return them with the chunk.

Write separate `rag-kstu/data/chunks.current.jsonl` and `rag-kstu/data/chunks.archive.jsonl` files. Record excluded selections and reasons separately.

## 4. Verify on real selected documents

Provide reproducible build and validation commands with pinned dependencies in this workspace. Avoid importing heavy OCR dependencies merely to read reviewed JSON.

Check the following behavior:

- Every emitted chunk belongs to KSTU and traces to existing, hash-matching approved source blocks.
- Current chunks have explicit current eligibility. Archive and withheld text cannot enter current output.
- All selected content is accounted for. Any omission has a reason.
- Real tuition tables retain row/column relationships, currency, study mode, nationality restrictions, and notes.
- Policy clauses retain their exceptions. The old administrative calendar is absent from current output. Retrieval behavior is tested in the later retrieval task.
- PDF citations resolve to the correct physical page. HTML citations retain their official URL.
- Token counts use the named tokenizer. Report size distribution, measured overlap, and all exceptions without claiming universal compliance.
- Every chunk has a nonempty source title, an allowed category, and a valid PDF page number or HTML `null`. Category assignment follows the reviewed audience mapping.
- Two builds on unchanged inputs produce identical ordered chunk content and IDs.

Use focused tests for these behaviors and inspect representative real outputs. Do not use placeholder text as the only verification evidence.

## 5. Publish the handoff

Write `rag-kstu/data/REPORT.md` with exact commands, source counts, current/archive chunk counts, topic coverage, exclusions, size exceptions, and validation results. Explain what questions the corpus can answer and what it must refuse.

Create `rag-kstu/evaluation/questions.jsonl` with at least 20 source-grounded cases spanning the required topics. Include at least five refusal cases and three table-lookup cases. Every answerable case needs expected source/page references and a verified answer. Missing topics must remain refusal cases rather than invented answers.

Use the assignment's exact fallback text:

> Unfortunately, I do not have accurate information on this question. Please contact the Student Office (room 101).

Treat room 101 as the assignment's required template, not a verified KSTU office location.

Mark this task complete only when the selected corpus passes validation and the report makes all gaps explicit. A limited corpus can be ready for retrieval development without satisfying full assignment coverage. State those two outcomes separately.

The final handoff must include the chunking script, validator, dependency/setup instructions, selected-source manifest, current and archive JSONL files, coverage and exclusion records, question set, and report. Show the exact commands and observed results for building, validating, and checking determinism. State that chunking reused prior extraction and the enrichment overlay; distinguish the completed enrichment crawl from any acquisition performed during chunking.
