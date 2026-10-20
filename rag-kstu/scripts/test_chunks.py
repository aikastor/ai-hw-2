#!/usr/bin/env python3
"""Focused checks of real reviewed KSTU documents and deliberate corruptions."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

import validate_chunks as validation


class RealCorpusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = validation.read('rag-kstu/data/source-manifest.json')
        cls.chunks = validation.load_chunks('rag-kstu/data')

    def group(self, selection):
        return [c for c in self.chunks if c['selection_id'] == selection]

    def test_all_real_sources_and_selected_units_validate(self):
        report = validation.validate_records(self.manifest, self.chunks)
        self.assertEqual(report['unaccounted_selected_units'], 0)
        self.assertGreater(report['chunk_counts']['current'], 0)
        self.assertGreater(report['chunk_counts']['archive'], 0)

    def test_tuition_every_reviewed_row_pair_currency_mode_and_nationality(self):
        for selection in self.manifest['selections']:
            if selection['topic'] != ['tuition']:
                continue
            chunks = self.group(selection['selection_id'])
            context = '\n'.join(validation.reference_text(r) for r in selection['context'])
            self.assertIn('сом', context)
            self.assertTrue('Очная форма обучения' in context or 'Заочная форма обучения с ДОТ' in context)
            self.assertTrue('ГРАЖДАНЕ КР' in context or 'ближнего зарубежья' in context)
            self.assertIn('1 курс', context)
            self.assertIn('6 курс', context)
            for unit in selection['units']:
                pair = validation.reference_text(unit['parts'][0]).rstrip('\n')
                lines = pair.splitlines()
                self.assertEqual(len(lines), 2)
                self.assertIn('1 кредит', lines[1])
                holders = [c for c in chunks if unit['unit_id'] in c['unit_ids']]
                self.assertTrue(holders)
                for chunk in holders:
                    self.assertIn(pair, chunk['text'])
                    table_lines = [line for line in chunk['text'].splitlines() if line.startswith('|')]
                    self.assertEqual(table_lines[0].count('|'), lines[0].count('|'))
                    self.assertIn(lines[0] + '\n' + lines[1], chunk['text'])
                    self.assertNotIn('|\n\n|', chunk['text'])
        full = self.group('tuition-33d632ae-kr-full-time')[0]['text']
        self.assertIn('580600 | 81000 | 81000 | 77220 | 72600 | 72600 |  |', full)
        self.assertIn('1350 | 1350 | 1287 | 1210 | 1210 |  |', full)
        distance = self.group('tuition-33d632ae-kr-distance')[0]['text']
        self.assertIn('580600 |  | 81000 | 61776 | 58080 | 58080 | 58080 |', distance)
        self.assertIn('Заочная форма обучения с ДОТ', distance)
        self.assertIn('входящие в межправ.согл.', self.group('tuition-33d632ae-near-foreign-agreement')[0]['text'])
        self.assertIn('не входящие в межправ.согл.', self.group('tuition-33d632ae-near-foreign-other')[0]['text'])

    def test_masters_documents_keep_eaeu_exception_and_cover(self):
        chunks = self.group('masters-documents')
        exception = 'за исключением граждан государств - участников ЕАЭС'
        self.assertTrue(any(exception in c['text'] and 'свидетельство об эквивалентности' in c['text'] for c in chunks))
        for chunk in chunks:
            self.assertEqual(chunk['page_number'], 1)
            self.assertIn('2026 / 2027', chunk['text'])
            self.assertIn('на программы подготовки магистров', chunk['text'])
            self.assertIn(1, {r['page_number'] for r in chunk['citations']})
            self.assertEqual(chunk['category'], 'prospective student')
        grants = self.group('masters-grants')[0]['text']
        for phrase in ['образование данного уровня впервые', 'по родственным направлениям', 'за исключением стран с международными договорами', 'государственные грантовые места — 2,33', 'подписать договор об обучении на бюджетной форме']:
            self.assertIn(phrase, grants)

    def test_tokmok_ort_exception_stays_with_checklist(self):
        chunks = self.group('tokmok-documents')
        self.assertEqual(len(chunks), 1)
        for phrase in ['Сертификат ОРТ', 'Графический дизайн(очно)', '(без ОРТ, внутренние вступительные экзамены)', 'Медицинская справка №086-У', 'Фотографии 4 шт. (3 х 4)']:
            self.assertIn(phrase, chunks[0]['text'])
        self.assertIn('Токмок', chunks[0]['source'])

    def test_policy_retake_33_continuation_and_exceptions(self):
        group = self.group('policy-retake-rules')
        rule = next(c for c in group if '3.3.' in c['text'])
        self.assertTrue({7, 8} <= {r['page_number'] for r in rule['citations']})
        self.assertIn('документально подтвержденной уважительной причине', rule['text'])
        self.assertIn('длительные служебные командировки, стихийные бедствия)', rule['text'])
        self.assertIn('за исключением документально обоснованных случаев', rule['text'])
        self.assertEqual(rule['eligibility'], 'archive')
        leave = '\n'.join(c['text'] for c in self.group('policy-academic-leave'))
        self.assertIn('если иное не предусмотрено межправительственными и межведомственными соглашениями', leave)
        self.assertIn('максимум на два семестра и только один раз', leave)
        fx = self.group('policy-retake-fx-i-f')[0]['text']
        self.assertIn('предоставляются дополнительные сроки по заявлению', fx)
        general = self.group('policy-gpa-formula')[0]
        self.assertEqual(general['category'], 'current student')
        self.assertEqual(general['eligibility'], 'archive')
        self.assertIn('не используется при вычислении GPA', general['text'])

    def test_old_calendar_absent_from_current_and_gpa_scopes_separate(self):
        allowed = next(s['source_sha256'] for s in self.manifest['selections'] if s['selection_id'] == 'calendar-01')
        for chunk in self.chunks:
            if chunk['eligibility'] == 'current' and chunk['category'] == 'calendar':
                self.assertEqual(chunk['source_sha256'], allowed)
                self.assertIn('2026-27', chunk['text'])
            if chunk['eligibility'] == 'current':
                self.assertNotIn('gpa', chunk['topic'])
                self.assertNotIn('policy-', chunk['selection_id'])
        self.assertEqual(self.group('masters-gpa-appendix')[0]['topic'], ['admission_gpa'])
        self.assertEqual(validation.validate_coverage(self.manifest, validation.read('rag-kstu/data/coverage.json'))['topics_with_current_scoped_evidence'], 7)

    def test_questions_have_real_references_and_reviewed_dates(self):
        report = validation.validate_questions(validation.ROOT / 'rag-kstu/evaluation/questions.jsonl', self.chunks)
        self.assertGreaterEqual(report['cases'], 20)
        self.assertGreaterEqual(report['refusal_cases'], 5)
        self.assertGreaterEqual(report['table_lookup_cases'], 3)

    def corrupt(self, mutate, message):
        chunks = copy.deepcopy(self.chunks)
        manifest = copy.deepcopy(self.manifest)
        mutate(manifest, chunks)
        with self.assertRaisesRegex(ValueError, message):
            validation.validate_records(manifest, chunks)

    def test_negative_text_category_page_eligibility_count_hash_controls(self):
        self.corrupt(lambda m, c: c[0].update(text=c[0]['text'] + ' invented'), 'exact approved units')
        self.corrupt(lambda m, c: c[0].update(category='current student'), 'category differs')
        self.corrupt(lambda m, c: c[0].update(page_number=999), 'physical page mismatch')
        self.corrupt(lambda m, c: c[0].update(eligibility='archive'), 'eligibility differs')
        self.corrupt(lambda m, c: c[0].update(token_count=1), 'token count')
        self.corrupt(lambda m, c: m['sources'][0].update(source_sha256='0' * 64), 'allowlist differs')
        self.corrupt(lambda m, c: m['inputs'].update({'rag-kstu/UNIVERSITY.md': '0' * 64}), 'Hash drift')
        self.corrupt(lambda m, c: c[0].update(selection_id='withheld'), 'withheld')

    def test_negative_overlap_and_repeated_context_measurements(self):
        def change(field):
            def mutate(manifest, chunks):
                chunk = next(c for c in chunks if c['overlap']['previous_chunk_id'])
                chunk['overlap'][field] += 1
                payload = {k: v for k, v in chunk.items() if k != 'chunk_id'}
                chunk['chunk_id'] = 'kstu-' + validation.digest(validation.canonical({'chunk': payload, 'settings': manifest['settings']}).encode())
            return mutate
        self.corrupt(change('shared_tokens'), 'semantic overlap')
        self.corrupt(change('repeated_context_tokens'), 'context count')

    def test_negative_selected_content_omission(self):
        def omit(manifest, chunks):
            chunks[:] = [c for c in chunks if c['selection_id'] != 'tokmok-documents']
        self.corrupt(omit, 'Unaccounted selected units')

    def test_negative_policy_promotion_in_manifest_and_chunks(self):
        def promote(manifest, chunks):
            for selection in manifest['selections']:
                if selection['selection_id'].startswith('policy-'):
                    selection.update(eligibility='current', current_answer_eligible=True, academic_year='2026-2027')
            for chunk in chunks:
                if chunk['selection_id'].startswith('policy-'):
                    chunk.update(eligibility='current', current_answer_eligible=True, academic_year='2026-2027')
        self.corrupt(promote, 'cannot be promoted')

    def test_negative_calendar_association_change(self):
        def change(manifest, chunks):
            selection = next(s for s in manifest['selections'] if s['selection_id'] == 'calendar-01')
            selection['event_association']['date'] = '2027-02-01'
        self.corrupt(change, 'association not reviewed')

    def test_byte_identical_fresh_builds(self):
        from build_chunks import build
        with tempfile.TemporaryDirectory(prefix='kstu-test-first-') as first, tempfile.TemporaryDirectory(prefix='kstu-test-second-') as second:
            build('rag-kstu/data/source-manifest.json', first)
            build('rag-kstu/data/source-manifest.json', second)
            for filename in ('chunks.current.jsonl', 'chunks.archive.jsonl', 'build-stats.json'):
                self.assertEqual((Path(first) / filename).read_bytes(), (Path(second) / filename).read_bytes())
                self.assertEqual((Path(first) / filename).read_bytes(), (validation.ROOT / 'rag-kstu/data' / filename).read_bytes())


if __name__ == '__main__':
    unittest.main()
