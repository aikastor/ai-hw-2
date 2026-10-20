# KSTU enrichment result — 20 October 2026

The targeted enrichment pass is complete. Full university-wide coverage is **not** complete. The [coverage matrix](coverage.json) records all ten assignment topics: seven have verified current evidence for specific audiences; retakes, general GPA, and academic leave have reviewed published policy text with unresolved current applicability.

## What was recovered

- The targeted crawl downloaded 42 records: 26 new hashes and 16 already collected. It reported no failed downloads. These are acquisition counts, not approved-source counts.
- A separate targeted fetch acquired the current Tokmok branch brochure.
- The [curated manifest](source-manifest.json) references nine distinct originals. One is cover/context evidence only; inclusion does not approve an entire document.
- [Admissions review](admissions/REPORT.md) recovered master's document requirements, GPA admission thresholds, and grant conditions, plus a Tokmok document checklist.
- [Calendar review](calendar/REPORT.md) recovered eight holiday/date associations and five additional registration windows, alongside five previously approved entries. These 18 selected entries cover full-time bachelor's/specialist students, not every calendar event or audience.
- [Policy review](policies/REPORT.md) recovered complete retake, general GPA, and academic-leave clauses. [Tuition review](tuition/REPORT.md) retains the two existing institute-specific fee tables.

Existing OCR, extracted text, and reviewed tables were reused. Only the new relevant brochure needed fresh text extraction. Earlier collection and eligibility files remain separate from this evidence overlay.

## Remaining gaps

| Area | What is still needed |
| --- | --- |
| Bachelor's admissions | Current university-wide document requirements, ORT thresholds with their exceptions, and grant eligibility. Master's GPA thresholds and branch-specific requirements cannot fill these gaps. |
| Retakes, general GPA, academic leave | Confirm operative applicability or amendments for the published policies. The general grade-conversion matrix also needs reconciliation before implementing a GPA calculator. |
| Tuition | Fee schedules for programmes and student groups beyond the two selected institutes. |
| Calendar | Additional audiences and unselected entries if the application is expected to cover them. |

The live KSTU admissions index linked an older threshold file. A national testing-centre news page was acquired separately, but it returned an application shell; its public news API request returned HTTP 500. That attempt did not establish current threshold values. These are unresolved research leads, not evidence that the information does not exist.

## Faster route from here

Review only the missing claims and the source context needed to interpret them. Reuse existing recognition; skip duplicate downloads, bilingual equivalence checks, unrelated regulations, and full-document OCR. Do not expand to another university.

Keep audience, year, fee units, exceptions, source pages, and table relationships. Those checks determine whether the assistant can give a correct answer. Downloaded candidates and qualified policies must not silently enter the current-answer corpus.

Chunking remains the next implementation stage after this enrichment assessment; it has not run. The prepared [chunking task](../../tasks/01-prepare-sources-and-chunks.md) now includes these evidence packets. Unresolved claims must remain excluded from current answers or explicitly scoped to verified evidence.

## Verification

[Validation](validation.json) checked nine original hashes, 62 policy/calendar block hashes, and all 42 main-crawl downloads. The [independent calendar review](calendar/independent-review.json) passed the selected 18 entries and 29 source-block references with scope limits. These checks establish artifact consistency and selected evidence quality, not full university coverage.

The [crawl report](../acquisition/20261020-162300-936458/REPORT.md) remains an acquisition report. Its unreviewed candidate statuses are intentionally separate from the later claim-level decisions in this enrichment folder.
