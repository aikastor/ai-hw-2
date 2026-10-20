# Why KSTU is the starting university

Choose KSTU for the assignment because the saved corpus includes a current academic calendar, scoped tuition tables, admissions material, and substantial policy documents. This is a judgment about the available project evidence, not an academic ranking.

The comparison below was read from `data/knowledge/universities.json` on 20 October 2026. Counts describe the published local snapshot. They are not unique documents or proof that the assignment's topics are complete.

| Candidate | Reviewed page identities | Pending page identities | Current chunks | Archive chunks | Main limitation |
| --- | ---: | ---: | ---: | ---: | --- |
| KSTU | 237 | 128 | 5 | 99 | Much policy evidence remains historical or has unresolved approval details |
| AUCA | 97 | 0 | 1 | 60 | Current selection contains tuition discounts; the saved academic calendar is for 2025–2026 |
| OshSU | 124 | 137 | 3 | 60 | Significant pending review and limited current topic coverage |
| KNU | 347 | 74 | 2 | 152 | Current chunks concern intake plans, not the complete required policy/calendar set |
| UCA | 96 | 117 | 2 | 49 | Reviewed handbook and admissions material includes specific graduate-program scope |
| INAI | 47 | 26 | 5 | 29 | Current chunks come from tuition and intake-plan documents |

KSTU's five current chunks must be interpreted narrowly. One is the full-time bachelor/specialist calendar. Two are tuition selections for specific institutes and student groups. Another is an institutional voucher-admissions provision. The remaining chunk contains only general provisions from the master's admission rules. Five chunks do not establish complete undergraduate admissions coverage.

## Required evidence and remaining gaps

The following is the **pre-enrichment baseline**, retained to explain the selection. The later [enrichment result](data/enrichment/REPORT.md) and [coverage matrix](data/enrichment/coverage.json) supersede these readiness counts: seven topics now have current scoped evidence, while three policy topics retain applicability qualifications.

The original current chunk text was checked on 20 October 2026 against the ten topics named in `task.md`. Seven lacked sufficient approved current evidence for student-facing answers. Three had usable scoped evidence. This counts current-answer readiness, not whether documents had been collected.

| Current-answer status | Topics | Count |
| --- | --- | ---: |
| Insufficient approved current evidence | Retakes, GPA, academic leave, admissions documents, thresholds, grant eligibility, holidays | 7 |
| Usable within limited scope | Tuition, exam periods, registration dates | 3 |

The calendar selection contains a spring pre-registration window and winter/summer examination periods for full-time bachelor/specialist students. It contains no holiday entries. Tuition covers selected programs and student groups in two institutes. The funding and voucher provisions do not establish individual grant eligibility.

Existing archive material can still be chunked separately. These gaps do not require restarting OCR and do not block building a limited current corpus.

| Required topic | Existing evidence to inspect | Remaining work |
| --- | --- | --- |
| Retakes | Repeat-learning and assessment regulations | Resolve approval/current applicability and distinguish exam retakes from repeating a course |
| GPA | Credit-system regulations; a grading/GPA appendix in the master's rules | Establish the correct audience and operative policy; a master's admissions conversion formula is not automatically the university's general GPA rule |
| Academic leave | Transfer, dismissal, reinstatement, and academic-leave regulation | Resolve unclear cover approval and current applicability |
| Required admissions documents | Saved official document-list page | Confirm the applicable intake year and applicant group |
| Admission thresholds | Saved file titled ORT thresholds for 2025 | Obtain evidence for the target intake; do not reuse 2025 values as 2026–2027 thresholds |
| Tuition | Current logistics and railway-institute tables | Preserve institute, program, nationality, course, study mode, currency, and fee-period restrictions |
| Grants | Admissions and funding provisions | Establish concrete applicant eligibility; general budget funding is not an individual grant entitlement |
| Calendar | Current full-time bachelor/specialist calendar | Check which exam periods, registration deadlines, and holidays are actually covered |

The selection and exclusion reasons are in [the published page selection](../data/knowledge/selection.json). The [source shortlist](sources/shortlist.json) pins candidate originals and extraction paths for the next task. A shortlist entry is a discovery lead, not permission to include every page.

Live fetch attempts for the calendar, a tuition PDF, and the admissions-document page failed through the web tool during this assessment. No live freshness or access conclusion follows from those failures. The choice rests on saved evidence, and currentness remains a source-review requirement.
