# Official programme and applicant evidence

Reviewed 2026-10-20. Only official KSTU sources were used. Three live HTML pages were downloaded to this isolated directory. No workspace files were edited.

## Programmes

Source. https://kstu.kg/abiturientu/1/napravlenija-podgotovki/bakalavr-i-magistratura#cc11982

Live HTML differs materially from the web search cache. The live introduction explicitly names the 2026–2027 intake. It says «Прием абитуриентов ... на 2026–2027 учебный год по направлениям бакалавриата». The page title is «Бакалавр и Специалитет». It contains 12 institute tables with 114 rows and three columns. Rowspans associate the same direction with several separate profiles. The complete extraction is programmes.json and programmes.md. programmes.json retains original table number, HTML row number, and original cell row/column for repeated rowspans. extract.py reruns extraction from saved originals.

The page does not provide qualification per row, course length, ORT score, fees or grants. Its programme lists include explicit «специализация» rows such as mining, applied geology, eastern architecture, and railway rolling stock. Do not tell users that every row is bachelor just because the introduction says bachelor. A scoped answer may say «В опубликованном перечне бакалавриата и специалитета на 2026–2027 ...». For a bachelor-only answer use corroborated bachelor entries or clearly label examples.

Concrete useful examples in the live catalogue include IT programming/software engineering, applied mathematics and informatics, cybersecurity profiles, artificial intelligence and machine learning, food biotechnology, electrical power/electrical engineering, mechatronics and robotics, communication systems, construction, architecture/design, logistics, economics and management. Preserve institute and profile context. These are actual programme-table rows, not inferred tuition rows. The source supports programmes and profiles, but not admission guarantees or available seats.

Raw file page-0.html. SHA-256 6844f19b7f47daa5622c63e9e1c47a65e6d9845b3ec694c4f02a65ad38e73ca0.

## Required applicant documents

Source. https://kstu.kg/abiturientu/4/dokumenty#c4011

Live source has five audience sections. The 11th-grade bachelor/ORT list requires school certificate original and two copies, ORT certificate, passport or other ID including Tunduk, military-registration certificate for liable applicants, four photos 3x4cm. Requirements for foreign applicants differ, including six photos, medical certificate 086 and mandatory medical insurance. Do not merge those lists.

The content frame id c4011 provides a stable HTML locator. requirements.json contains the source-separated lists. requirements-body.html and requirements-body.txt preserve the actual frame. The page prints no intake year. Treat it as the currently published university checklist, not a dated 2026 admission order. There is a conflict with an indexed 2026 IET brochure which asks six photos after school. Prefer the central university page for the general checklist and preserve unit-specific exceptions if that brochure is used.

Raw file page-2.html. SHA-256 8ebbfe632d6b78a2ad0aa8fe8c76d1a0c9433dd37368b01f7ec4b0cfef81e060.

## Threshold and grant gaps

Source. https://kstu.kg/abiturientu/1/dokumenty

The live normative index links «Пороговые баллы ОРТ на 2025 год», not a 2026 threshold order. It now links current 2026 additional-test and ORT-tour orders and current master's rules. Do not promote the 2025 thresholds to the target 2026–2027 intake. It still links a grant-commission order, which is not itself evidence of applicant grant eligibility or programme quotas. No university-wide 2026 bachelor grant quota/eligibility evidence was established in this bounded research.

Source. https://kstu.kg/abiturientu/1/plan-nabora

Current web-open rendering lists only the 2026–27 SPO contract admission plan and an empty budget heading. Its search cache instead advertises several 2025 higher-education plans. Use live acquisition over cached search. Do not infer 2026 bachelor quotas from cached 2025 plans.

Raw normative index page-1.html. SHA-256 15317dfa6931cf21ab4ac392ec66dfaf5a19178b88bcc9a84a0d237399bd41d0. Exact PDF candidates are in page-1-links.json. Already known master's and old threshold documents were not downloaded again.

## Additional bounded leads

https://kstu.kg/fileadmin/user_upload/iet_brochure.pdf. Indexed official 2026 IET brochure with programmes and after-school/after-college requirement sections. Search returned the new1.kstu.kg mirror; validate main-host official linkage and file year before inclusion.

https://kstu.kg/fileadmin/user_upload/buklet_kafedry_men_2026.pdf. Indexed 2026 management brochure explicitly calls Management and Business Administration bachelor, and gives 4/5 years for full/part-time. Dated and unit-specific, useful to corroborate general catalogue rows. Not downloaded here to avoid overlapping root acquisition.

https://kstu.kg/fileadmin/user_upload/buklet_ogr_i_vd_09.03.2026_g.pdf. Indexed 2026 Open-Pit Mining and Blasting brochure with budget/contract statement and provisional document window 1 July–20 August 2026. Unit-specific and mainly specialist/master/PhD, unsuitable as university-wide bachelor evidence.
