#!/usr/bin/env python3
"""Exercise expansion against the real frozen base and deliberate source corruption."""
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

import expanded_sources as expansion


HTML = '''<html><h1>Бакалавр и Специалитет</h1><section id="cc11982"><div>
<p>Прием на 2026–2027 учебный год по направлениям бакалавриата.</p>
<p>ИНСТИТУТ ТЕХНОЛОГИЙ</p><figure><table><tr><td>№</td><td>Направление</td><td>Профиль / специализация</td></tr>
<tr><td rowspan="2">1</td><td rowspan="2">Информатика</td><td>Программирование</td></tr>
<tr><td>Информационные системы</td></tr>
<tr><td>2</td><td>Специальность</td><td>специализация</td></tr></table></figure>
</div></section></html>'''


class ExpandedSourcesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original_root = expansion.ROOT
        cls.base_manifest = json.loads((cls.original_root / 'rag-kstu/data/source-manifest.json').read_text())

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name).resolve()
        paths = set(self.base_manifest['inputs'])
        for source in self.base_manifest['sources']:
            paths.add(source['original_path'])
            for prefix in ('extraction', 'selected_text'):
                if source.get(prefix + '_path'):
                    paths.add(source[prefix + '_path'])
        paths.update({'rag-kstu/data/source-manifest.json', 'rag-kstu/data/chunks.current.jsonl',
                      'rag-kstu/data/chunks.archive.jsonl', 'rag-kstu/data/coverage.json'})
        paths.update(str(p.relative_to(self.original_root)) for p in (self.original_root / 'rag-kstu/data/tokenizer').iterdir() if p.is_file())
        for name in paths:
            target = self.root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(self.original_root / name, target)
        for module in (expansion, expansion.base, expansion.validator):
            patcher = patch.object(module, 'ROOT', self.root)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.raw = self.root / 'rag-kstu/data/expanded/sources/programmes.html'
        self.raw.parent.mkdir(parents=True)
        self.raw.write_text(HTML, encoding='utf-8')
        self.artifact = self.raw.with_suffix('.json')
        self.artifact.write_text(json.dumps({'passages': expansion.extract_programmes(self.raw)}, ensure_ascii=False))
        self.ref = {'artifact_path': self.relative(self.artifact), 'artifact_sha256': self.digest(self.artifact),
                    'reader': 'passage', 'page_number': None, 'passage_id': 'programmes-table-1-rows-2-3',
                    'text_sha256': expansion.base.sha256(expansion.extract_programmes(self.raw)[0]['text'].encode())}
        self.selection = {'selection_id': 'expanded-programmes',
                          'source': {'title': 'Бакалавр и Специалитет', 'source_url': 'https://kstu.kg/programmes',
                                     'raw_path': self.relative(self.raw), 'source_sha256': self.digest(self.raw), 'format': 'html_programmes'},
                          'refs': [self.ref], 'context': [], 'scope': 'bachelor_programmes',
                          'category': 'prospective student', 'additional_categories': [], 'topic': ['programmes'],
                          'audience_restrictions': ['Bachelor and specialist applicants'],
                          'current_answer_eligible': True, 'effective_date_evidence': {'status': 'printed_academic_year', 'year': '2026-2027'},
                          'review_decision': 'approved', 'limitations': ['Page mixes bachelor and specialist programmes.']}
        self.review = self.raw.parent / 'review.json'
        self.manifest_path = self.raw.parent.parent / 'source-manifest.json'
        self.manifest = {'kind': 'reviewed_expansion', 'university_id': 'kstu', 'target_academic_year': '2026-2027'}
        for field, name in [('base_manifest', 'source-manifest.json'), ('base_current', 'chunks.current.jsonl'), ('base_archive', 'chunks.archive.jsonl')]:
            path = self.root / 'rag-kstu/data' / name
            self.manifest[field + '_path'] = self.relative(path)
            self.manifest[field + '_sha256'] = self.digest(path)
        self.save_selection()
        self.output = self.manifest_path.parent

    def relative(self, path):
        return str(path.relative_to(self.root))

    def digest(self, path):
        return expansion.base.sha256(path.read_bytes())

    def save_selection(self):
        selected = {k: v for k, v in self.selection.items() if k != 'review_ref'}
        self.review.write_text(json.dumps({'selections': [selected]}, ensure_ascii=False))
        self.selection['review_ref'] = {'artifact_path': self.relative(self.review), 'artifact_sha256': self.digest(self.review), 'selection_id': self.selection['selection_id']}
        self.manifest['supplements'] = [self.selection]
        self.manifest_path.write_text(json.dumps(self.manifest, ensure_ascii=False))

    def build(self):
        return expansion.build(self.manifest_path, self.output)

    def test_deterministic_build_preserves_frozen_records_and_source_citations(self):
        self.build()
        current_path = self.output / 'chunks.current.jsonl'
        before = current_path.read_bytes()
        records = expansion.validate_expansion(current_path)
        base = (self.root / self.manifest['base_current_path']).read_bytes()
        self.assertTrue(before.startswith(base))
        self.assertEqual(records[:-1], [json.loads(line) for line in base.splitlines()])
        added = records[-1]
        self.assertEqual(added['scope'], 'bachelor_programmes')
        self.assertEqual(added['citations'][0]['source_url'], 'https://kstu.kg/programmes')
        self.assertIsNone(added['citations'][0]['page_number'])
        self.assertIn('Информационные системы', added['text'])
        self.assertEqual(added['token_count'], expansion.base.token_count(added['text']))
        self.assertEqual((self.output / 'chunks.archive.jsonl').read_bytes(), (self.root / self.manifest['base_archive_path']).read_bytes())
        self.build()
        self.assertEqual(current_path.read_bytes(), before)

    def test_raw_source_drift_is_rejected(self):
        self.build()
        self.raw.write_text(HTML + 'changed')
        with self.assertRaisesRegex(ValueError, 'Hash drift'):
            expansion.validate_expansion(self.output / 'chunks.current.jsonl')

    def test_unknown_scope_is_rejected_even_if_reviewed(self):
        self.selection['scope'] = 'unrelated_scope'
        self.save_selection()
        with self.assertRaisesRegex(ValueError, 'Unknown reviewed expansion scope'):
            self.build()

    def test_review_authority_cannot_be_omitted(self):
        self.selection.pop('review_ref')
        self.manifest_path.write_text(json.dumps(self.manifest))
        with self.assertRaisesRegex(ValueError, 'Missing independent review authority'):
            self.build()

    def test_selected_text_must_match_independent_html_reparse(self):
        artifact = json.loads(self.artifact.read_text())
        artifact['passages'][0]['text'] += ' Fictional degree'
        self.artifact.write_text(json.dumps(artifact))
        self.ref.update(artifact_sha256=self.digest(self.artifact), text_sha256=expansion.base.sha256(artifact['passages'][0]['text'].encode()))
        self.save_selection()
        with self.assertRaisesRegex(ValueError, 'independently parsed raw source'):
            self.build()

    def test_paths_reject_symlinks_and_traversal(self):
        link = self.raw.parent / 'alias.html'
        link.symlink_to(self.raw)
        with self.assertRaisesRegex(ValueError, 'Symlink'):
            expansion.safe_path(link)
        with self.assertRaisesRegex(ValueError, 'traversal'):
            expansion.safe_path('rag-kstu/../rag-kstu/data')

    def test_policy_clause_keeps_every_contributing_physical_page(self):
        raw = self.raw.with_name('policy.pdf')
        raw.write_bytes(b'%PDF-1.4\nSynthetic policy fixture\n')
        document = {'source_sha256': self.digest(raw), 'pages': [
            {'page_number': 2, 'blocks': [{'type': 'text', 'text': '3.3 Правила пересдачи, начало.'}]},
            {'page_number': 3, 'blocks': [{'type': 'text', 'text': 'Продолжение пункта 3.3 с условиями.'}]}]}
        artifact = raw.with_suffix('.json')
        artifact.write_text(json.dumps(document, ensure_ascii=False))
        refs = [{'artifact_path': self.relative(artifact), 'artifact_sha256': self.digest(artifact),
                 'reader': 'block', 'page_number': page['page_number'], 'block_index': 0,
                 'text_sha256': expansion.base.sha256(page['blocks'][0]['text'].encode())}
                for page in document['pages']]
        self.selection.update(scope='general_academic_policy', category='current student', topic=['retakes'],
                              source={'title': 'Положение 2025 года', 'source_url': 'https://kstu.kg/policy.pdf',
                                      'raw_path': self.relative(raw), 'source_sha256': self.digest(raw), 'format': 'pdf'},
                              units=[{'unit_id': 'complete-clause-3.3', 'kind': 'paragraph', 'parts': refs}],
                              effective_date_evidence={'status': 'published_policy_2025', 'effective_year_unverified': True})
        self.selection.pop('refs')
        self.save_selection()
        self.build()
        chunk = expansion.validate_expansion(self.output / 'chunks.current.jsonl')[-1]
        self.assertEqual(chunk['unit_ids'], ['complete-clause-3.3'])
        self.assertEqual([c['page_number'] for c in chunk['citations']], [2, 3])
        self.assertEqual([c['url'] for c in chunk['citations']],
                         ['https://kstu.kg/policy.pdf#page=2', 'https://kstu.kg/policy.pdf#page=3'])
        self.assertIn('Продолжение пункта 3.3', chunk['text'])
        self.assertTrue(chunk['effective_date_evidence']['effective_year_unverified'])

    def test_unknown_or_duplicate_chunk_ids_are_rejected(self):
        self.build()
        path = self.output / 'chunks.current.jsonl'
        original = path.read_text()
        rows = [json.loads(line) for line in original.splitlines()]
        rows[-1]['chunk_id'] = 'invented-id'
        path.write_text('\n'.join(map(json.dumps, rows)) + '\n')
        with self.assertRaisesRegex(ValueError, 'exact source reconstruction'):
            expansion.validate_expansion(path)
        path.write_text(original + original.splitlines()[0] + '\n')
        with self.assertRaisesRegex(ValueError, 'exact source reconstruction'):
            expansion.validate_expansion(path)

    def test_table_headers_and_connected_rowspan_group_are_complete(self):
        passages = expansion.extract_programmes(self.raw)
        self.assertEqual(len(passages), 2)
        self.assertEqual(passages[0]['locator']['last_html_row'], 3)
        self.assertEqual([row[1] for row in passages[0]['rows']], ['Информатика', 'Информатика'])
        for passage in passages:
            self.assertIn('Бакалавр и Специалитет', passage['text'])
            self.assertIn('2026–2027', passage['text'])
            self.assertIn('Профиль / специализация', passage['text'])
            self.assertIn('ИНСТИТУТ ТЕХНОЛОГИЙ', passage['text'])
        self.assertEqual(passages[1]['rows'][0][-1], 'специализация')

    def test_requirements_keep_school_and_foreign_audiences_separate(self):
        path = self.raw.parent / 'requirements.html'
        path.write_text('<h1>Документы</h1><div id="c4011"><p>На базе 11-го класса</p><ul><li>Аттестат</li><li>ОРТ</li></ul><h2>Для иностранных граждан</h2><ul><li><p>Медицинская страховка (ОМС)</p><p class="text-center">ИНОГОРОДНИМ ПРЕДОСТАВЛЯЕТСЯ ОБЩЕЖИТИЕ</p></li></ul></div>')
        passages = expansion.extract_requirements(path)
        self.assertEqual(len(passages), 2)
        self.assertIn('ОРТ', passages[0]['text'])
        self.assertNotIn('Медицинская', passages[0]['text'])
        self.assertIn('Для иностранных граждан', passages[1]['text'])
        self.assertIn('Медицинская страховка (ОМС)', passages[1]['text'])
        self.assertNotIn('ИНОГОРОДНИМ', passages[1]['text'])
        self.assertIsNone(passages[1]['page_number'])


if __name__ == '__main__':
    unittest.main()
