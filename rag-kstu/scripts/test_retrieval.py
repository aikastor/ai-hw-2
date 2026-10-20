"""Reviewed-corpus retrieval and local Ollama embedding contract checks."""
import hashlib
import importlib.util
import json
import math
import shutil
import socket
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if not (ROOT / 'rag-kstu').is_dir():
    ROOT = Path.cwd()
ENGINE = ROOT / 'rag-kstu/scripts/retrieval.py'
spec = importlib.util.spec_from_file_location('kstu_retrieval', ENGINE)
retrieval = importlib.util.module_from_spec(spec)
spec.loader.exec_module(retrieval)
DATA = ROOT / 'rag-kstu/data'
CONFIG = ROOT / 'rag-kstu/models/ollama-embedding.json'


def read_rows(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


class OllamaEndpointTests(unittest.TestCase):
    def test_compose_endpoint_requires_exact_opt_in(self):
        for flag in ('', '0', 'true', 'yes'):
            with patch.dict('os.environ', {'KSTU_ALLOW_DOCKER_OLLAMA': flag}):
                with self.assertRaises(ValueError):
                    retrieval.OllamaEmbedder._loopback_url('http://ollama:11434')
        with patch.dict('os.environ', {'KSTU_ALLOW_DOCKER_OLLAMA': '1'}):
            self.assertEqual(retrieval.OllamaEmbedder._loopback_url('http://ollama:11434'),
                             'http://ollama:11434')

    def test_compose_opt_in_does_not_admit_other_remote_urls(self):
        rejected = ['http://ollama', 'ollama:11434', 'https://ollama:11434',
                    'http://ollama:11435', 'http://ollama:11434/',
                    'http://user:password@ollama:11434', 'http://ollama:11434/api',
                    'http://ollama:11434?x=1', 'http://ollama:11434#fragment',
                    'http://remote:11434', 'http://192.168.1.2:11434',
                    'http://ollama.example:11434', 'http://OLLAMA:11434',
                    ' http://ollama:11434', 'http://ollama:11434\n']
        with patch.dict('os.environ', {'KSTU_ALLOW_DOCKER_OLLAMA': '1'}):
            for host in rejected:
                with self.subTest(host=host), self.assertRaises(ValueError):
                    retrieval.OllamaEmbedder._loopback_url(host)

    def test_loopback_behavior_is_unchanged_with_compose_opt_in(self):
        with patch.dict('os.environ', {'KSTU_ALLOW_DOCKER_OLLAMA': '1'}):
            for host, expected in [('localhost', 'http://127.0.0.1:11434'),
                                   ('http://127.0.0.1:12345', 'http://127.0.0.1:12345'),
                                   ('http://[::1]:11434', 'http://[::1]:11434')]:
                self.assertEqual(retrieval.OllamaEmbedder._loopback_url(host), expected)
            for host in ['http://user@localhost:11434', 'http://localhost:11434/api',
                         'http://localhost:11434?x=1', 'http://localhost:11434#fragment']:
                with self.assertRaises(ValueError):
                    retrieval.OllamaEmbedder._loopback_url(host)

    def test_compose_endpoint_still_checks_runtime_and_model_pins(self):
        config = json.loads(CONFIG.read_text())
        for wrong in ('runtime', 'digest', None):
            def respond(method, path, payload=None):
                if path == '/api/version':
                    return {'version': 'wrong' if wrong == 'runtime' else config['ollama_version']}
                if path == '/api/tags':
                    return {'models': [{'name': config['model'], 'digest': 'wrong' if wrong == 'digest' else config['model_digest']}]}
                if path == '/api/show':
                    return {'capabilities': ['embedding']}
                raise AssertionError(path)
            with patch.dict('os.environ', {'KSTU_ALLOW_DOCKER_OLLAMA': '1', 'OLLAMA_HOST': 'http://ollama:11434'}), patch.object(retrieval.OllamaEmbedder, '_request', side_effect=respond):
                if wrong:
                    with self.assertRaisesRegex(ValueError, 'pinned'):
                        retrieval.OllamaEmbedder()
                else:
                    self.assertEqual(retrieval.OllamaEmbedder().base_url, 'http://ollama:11434')


class RetrievalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='kstu-retrieval-tests-')
        cls.work = Path(cls.temp.name)
        cls.index = cls.work / 'index'
        cls.current = read_rows(DATA / 'chunks.current.jsonl')
        cls.archive = read_rows(DATA / 'chunks.archive.jsonl')
        cls.by_id = {row['chunk_id']: row for row in cls.current}
        cls.manifest = retrieval.build_index(DATA / 'chunks.current.jsonl', cls.index, embedding_config=CONFIG)
        cls.retriever = retrieval.Retriever(cls.index, embedding_config=CONFIG)

    @classmethod
    def tearDownClass(cls):
        cls.retriever.close()
        cls.temp.cleanup()

    def search(self, query, **kwargs):
        return self.retriever.search(query, **kwargs)['hits']

    def test_current_only_payload_and_parent_coverage(self):
        self.assertEqual(len(self.current), 30)
        self.assertEqual(len(self.archive), 5)
        self.assertEqual(self.manifest['schema_version'], 2)
        self.assertEqual(self.manifest['chunk_count'], len(self.current))
        self.assertEqual(self.manifest['point_count'], 30)
        self.assertEqual(self.manifest['embedding_config_sha256'], hashlib.sha256(CONFIG.read_bytes()).hexdigest())
        self.assertEqual(self.manifest['embedding'], self.retriever.embedder.identity)
        self.assertNotIn('model_manifest_sha256', self.manifest)
        self.assertNotIn('logical_vector_fingerprint', self.manifest)
        points, cursor = self.retriever.client.scroll(
            retrieval.COLLECTION, limit=10000, with_vectors=True)
        self.assertIsNone(cursor)
        self.assertEqual(len(points), self.manifest['point_count'])
        self.assertEqual(self.manifest['stored_vector_fingerprint'], retrieval.point_fingerprint(points))
        self.assertEqual({p.payload['chunk_id'] for p in points}, set(self.by_id))
        self.assertFalse({p.payload['chunk_id'] for p in points} &
                         {row['chunk_id'] for row in self.archive})
        for point in points:
            payload = point.payload
            parent = self.by_id[payload['chunk_id']]
            self.assertEqual(payload['eligibility'], 'current')
            self.assertIs(payload['current_answer_eligible'], True)
            self.assertEqual(payload['university_id'], 'kstu')
            self.assertEqual(payload['academic_year'], '2026-2027')
            self.assertEqual(payload['categories'],
                             [parent['category']] + parent['additional_categories'])
            self.assertEqual(payload['topic'], parent['topic'])
            self.assertEqual(len(point.vector), 1024)
            self.assertTrue(all(math.isfinite(value) for value in point.vector))
            self.assertAlmostEqual(sum(value * value for value in point.vector), 1.0, places=5)

    def test_full_parent_windows_include_qualifiers_and_table_tail(self):
        embedder = self.retriever.embedder
        longest = max(self.current, key=lambda row: row['token_count'])
        self.assertGreaterEqual(longest['token_count'], 1315)
        tables = [row for row in self.current if 'tuition' in row['topic']]
        self.assertTrue(tables)
        for parent in self.current:
            text = parent['text']
            windows = embedder.windows(text, parent['chunk_id'])
            self.assertEqual(len(windows), 1)
            window = windows[0]
            self.assertEqual(window['start'], 0)
            self.assertEqual(window['end'], len(text))
            self.assertEqual(window['text_sha256'], hashlib.sha256(text.encode()).hexdigest())
            self.assertNotIn('model_token_count', window)
            self.assertEqual(window['context_enforcement'], 'server truncate=false')
        for parent in [longest] + tables:
            hit = next(hit for hit in self.search(parent['text'][-100:], mode='bm25', top_k=50)
                       if hit['chunk_id'] == parent['chunk_id'])
            self.assertEqual(hit['text'][-100:], parent['text'][-100:])

    def test_dense_russian_and_english_retrieve_admissions_evidence(self):
        for query in ('Какие документы нужны для поступления в магистратуру?',
                      'What documents are required for admission to a masters degree?'):
            hits = self.search(query, mode='dense', category='prospective student', top_k=5)
            self.assertTrue(hits)
            self.assertTrue(any(hit['selection_id'].startswith('masters-') for hit in hits))
            self.assertTrue(all(hit['category'] == 'prospective student' for hit in hits))

    def test_exact_programme_code_bm25(self):
        hits = self.search('580600', mode='bm25', top_k=10)
        self.assertTrue(hits)
        self.assertIn('580600', hits[0]['text'])
        self.assertGreater(hits[0]['bm25_score'], 0)
        self.assertIsNone(hits[0]['dense_score'])

    def test_scopes_are_isolated_in_all_modes(self):
        scopes = {
            'masters_admissions': 'masters-',
            'tokmok_admissions': 'tokmok-',
            'logistics_tuition': 'tuition-33d',
            'railway_tuition': 'tuition-757',
            'calendar_fulltime_bachelor_specialist': 'calendar-',
        }
        for mode in ('dense', 'bm25', 'hybrid'):
            for scope, prefix in scopes.items():
                hits = self.search('КГТУ обучение документы 2026', scope=scope, mode=mode, top_k=30)
                if mode != 'bm25':
                    self.assertTrue(hits, (mode, scope))
                for hit in hits:
                    self.assertEqual(hit['scope'], scope)
                    self.assertTrue(hit['selection_id'].startswith(prefix))

    def test_current_student_can_retrieve_additional_category_tuition(self):
        for mode in ('dense', 'bm25', 'hybrid'):
            hits = self.search('580600', category='current student', scope='logistics_tuition', mode=mode)
            self.assertTrue(hits)
            for hit in hits:
                self.assertIn('current student', hit['additional_categories'])
                self.assertEqual(hit['category'], 'prospective student')

    def test_unsupported_metadata_never_falls_back_to_unfiltered_search(self):
        cases = [{'scope': 'unknown_scope'}, {'academic_year': '2025-2026'},
                 {'topic': 'retakes'}, {'topic': 'gpa_calculation'}, {'topic': 'academic_leave'}]
        for mode in ('dense', 'bm25', 'hybrid'):
            for filters in cases:
                result = self.retriever.search('КГТУ документы GPA', mode=mode, **filters)
                self.assertEqual(result['hits'], [], (mode, filters))
                self.assertEqual(result['status'], 'no_matching_scope')

    def test_full_parent_text_and_citations_are_returned_once(self):
        for mode in ('dense', 'bm25', 'hybrid'):
            hits = self.search('КГТУ обучение документы', mode=mode, top_k=50)
            self.assertTrue(hits)
            ids = [hit['chunk_id'] for hit in hits]
            self.assertEqual(len(ids), len(set(ids)))
            for hit in hits:
                original = self.by_id[hit['chunk_id']]
                self.assertEqual(hit['text'], original['text'])
                self.assertEqual(hit['citations'], original['citations'])
                self.assertEqual(hit['audience_restrictions'], original['audience_restrictions'])
                self.assertEqual(hit['page_number'], original['page_number'])
                self.assertEqual(hit['source_url'], original['source_url'])

    def test_rrf_ranks_parents_once_before_combining(self):
        query = 'магистратуру документы обучение'
        dense = self.search(query, mode='dense', top_k=100)
        bm25 = self.search(query, mode='bm25', top_k=100)
        hybrid = self.search(query, mode='hybrid', top_k=100)
        expected = {}
        for ranking in (dense, bm25):
            for rank, hit in enumerate(ranking, 1):
                cid = hit['chunk_id']
                expected[cid] = expected.get(cid, 0.0) + 1 / (retrieval.SETTINGS['rrf_k'] + rank)
        self.assertEqual([hit['chunk_id'] for hit in hybrid],
                         sorted(expected, key=lambda cid: (-expected[cid], cid)))
        for hit in hybrid:
            self.assertAlmostEqual(hit['rrf_score'], expected[hit['chunk_id']])

    def test_input_validation(self):
        for query in ('', '  \n', None):
            with self.assertRaises(ValueError):
                self.retriever.search(query)
        for filters in ({'category': 'everyone'}, {'mode': 'random'}, {'top_k': 0}, {'top_k': True}):
            with self.assertRaises(ValueError):
                self.retriever.search('КГТУ', **filters)

    def test_real_ollama_response_has_expected_model_shape_and_norm(self):
        longest = max(self.current, key=lambda row: row['token_count'])
        vectors = self.retriever.embedder.embed_passages([longest['text']])
        self.assertEqual(len(vectors), 1)
        self.assertEqual(len(vectors[0]), 1024)
        self.assertTrue(all(math.isfinite(value) for value in vectors[0]))
        self.assertAlmostEqual(math.fsum(value * value for value in vectors[0]), 1.0, places=5)

    def test_real_ollama_rejects_overflow_with_truncation_disabled(self):
        embedder = self.retriever.embedder
        with self.assertRaisesRegex(ValueError, 'length|context|token|exceed|long|HTTP 400'):
            embedder._request('POST', '/api/embed', {
                'model': embedder.config['model'],
                'input': ['магистратура ' * 12000],
                'truncate': False,
                'options': {'num_ctx': embedder.config['max_tokens']},
            })

    def test_mutated_embedding_config_and_model_identity_are_rejected(self):
        original = json.loads(CONFIG.read_text())
        mutations = {
            'provider': 'remote', 'model': 'not-bge-m3:latest', 'dimension': 384,
            'max_tokens': 512, 'model_digest': '0' * 64, 'ollama_version': 'not-pinned',
        }
        for key, value in mutations.items():
            with self.subTest(key=key):
                path = self.work / ('mutated-' + key + '.json')
                path.write_text(json.dumps(dict(original, **{key: value})))
                with self.assertRaisesRegex(ValueError, 'config|pinned|differs|digest'):
                    retrieval.OllamaEmbedder(embedding_config=path)
        changed = self.work / 'changed-config-bytes.json'
        changed.write_text(json.dumps(original, indent=4) + '\n')
        clone = self.work / 'changed-config-index'
        shutil.copytree(self.index, clone)
        with self.assertRaisesRegex(ValueError, 'model differs|rebuild'):
            retrieval.Retriever(clone, embedding_config=changed)

    def test_unavailable_loopback_ollama_has_actionable_error(self):
        embedder = self.retriever.embedder
        with socket.socket() as unavailable:
            unavailable.bind(('127.0.0.1', 0))
            host = 'http://127.0.0.1:' + str(unavailable.getsockname()[1])
            with patch.object(embedder, 'base_url', host):
                with self.assertRaisesRegex(ValueError, 'Local Ollama is unavailable.*start the pinned runtime'):
                    embedder._request('GET', '/api/version')

    def test_malformed_embedding_responses_are_rejected(self):
        embedder = self.retriever.embedder
        unit = [1.0] + [0.0] * 1023
        cases = [
            ({'model': embedder.config['model'], 'embeddings': []}, 'count'),
            ({'model': embedder.config['model'], 'embeddings': [unit, unit]}, 'count'),
            ({'model': embedder.config['model'], 'embeddings': [[1.0]]}, 'dimension'),
            ({'model': embedder.config['model'], 'embeddings': [[float('nan')] + [0.0] * 1023]}, 'finite'),
            ({'model': embedder.config['model'], 'embeddings': [[float('inf')] + [0.0] * 1023]}, 'finite'),
            ({'model': embedder.config['model'], 'embeddings': [[0.0] * 1024]}, 'unit norm'),
            ({'model': 'different-model', 'embeddings': [unit]}, 'model differs'),
        ]
        for response, error in cases:
            with self.subTest(error=error, count=len(response['embeddings'])):
                request = embedder._request
                def malformed_response(method, path, payload=None):
                    if path == '/api/embed':
                        return response
                    return request(method, path, payload)
                with patch.object(embedder, '_request', side_effect=malformed_response):
                    with self.assertRaisesRegex(ValueError, error):
                        embedder.embed_queries(['КГТУ'])

    def test_runtime_and_model_drift_are_rejected_before_embedding(self):
        embedder = self.retriever.embedder
        request = embedder._request
        version = request('GET', '/api/version')
        tags = request('GET', '/api/tags')
        wrong_tags = json.loads(json.dumps(tags))
        for model in wrong_tags['models']:
            if model['name'] == embedder.config['model']:
                model['digest'] = '0' * 64
        cases = [('/api/version', dict(version, version='changed-runtime')),
                 ('/api/tags', wrong_tags)]
        for endpoint, response in cases:
            with self.subTest(endpoint=endpoint):
                def drifted_response(method, path, payload=None):
                    if path == '/api/embed':
                        self.fail('Embedding must stop before a request after identity drift')
                    if path == endpoint:
                        return response
                    return request(method, path, payload)
                with patch.object(embedder, '_request', side_effect=drifted_response):
                    with self.assertRaisesRegex(ValueError, 'differs|digest|pinned'):
                        embedder.embed_queries(['КГТУ'])

    def test_invalid_http_response_json_and_server_error_are_rejected(self):
        import httpx
        embedder = self.retriever.embedder
        cases = [
            (httpx.Response(400, json={'error': 'input length exceeds context'}), 'HTTP 400.*input length'),
            (httpx.Response(200, text='not-json'), 'invalid JSON'),
            (httpx.Response(200, json=[]), 'invalid response'),
            (httpx.Response(200, json={'error': 'model unavailable'}), 'invalid response.*model unavailable'),
        ]
        for response, error in cases:
            with self.subTest(error=error):
                with patch('httpx.Client') as client:
                    client.return_value.__enter__.return_value.request.return_value = response
                    with self.assertRaisesRegex(ValueError, error):
                        embedder._request('POST', '/api/embed', {'input': ['КГТУ'], 'truncate': False})

    def test_model_drift_during_embedding_batch_is_rejected(self):
        embedder = self.retriever.embedder
        request = embedder._request
        embedded = False
        def change_tag(method, path, payload=None):
            nonlocal embedded
            if path == '/api/embed':
                embedded = True
                return {'model': embedder.config['model'], 'embeddings': [[1.0] + [0.0] * 1023]}
            if path == '/api/tags' and embedded:
                return {'models': []}
            return request(method, path, payload)
        with patch.object(embedder, '_request', side_effect=change_tag):
            with self.assertRaisesRegex(ValueError, 'digest|missing'):
                embedder.embed_queries(['КГТУ'])

    def test_stale_chunk_fingerprint_is_rejected(self):
        clone = self.work / 'stale-chunks'
        shutil.copytree(self.index, clone)
        path = clone / 'manifest.json'
        manifest = json.loads(path.read_text())
        manifest['chunks_sha256'] = '0' * 64
        path.write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError, 'corpus changed|hash drift|rebuild'):
            retrieval.Retriever(clone, embedding_config=CONFIG)

    def test_changed_stored_vector_fingerprint_is_rejected(self):
        clone = self.work / 'stale-vector-fingerprint'
        shutil.copytree(self.index, clone)
        path = clone / 'manifest.json'
        manifest = json.loads(path.read_text())
        manifest['stored_vector_fingerprint'] = '0' * 64
        path.write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError, 'Stored vector index differs|rebuild'):
            retrieval.Retriever(clone, embedding_config=CONFIG)

    def test_stale_embedding_config_manifest_is_rejected(self):
        clone = self.work / 'stale-config'
        shutil.copytree(self.index, clone)
        path = clone / 'manifest.json'
        manifest = json.loads(path.read_text())
        manifest['embedding_config_sha256'] = '0' * 64
        path.write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError, 'config|hash drift|rebuild'):
            retrieval.Retriever(clone, embedding_config=CONFIG)

    def test_rebuild_rejects_protected_config_and_active_index(self):
        before = CONFIG.read_bytes()
        for target in (CONFIG, CONFIG.parent, CONFIG.parent.parent, CONFIG.parent / 'bge-m3'):
            with self.assertRaisesRegex(ValueError, 'protected'):
                retrieval.build_index(DATA / 'chunks.current.jsonl', target, embedding_config=CONFIG)
        self.assertEqual(before, CONFIG.read_bytes())
        with self.assertRaisesRegex(ValueError, 'in use'):
            retrieval.build_index(DATA / 'chunks.current.jsonl', self.index, embedding_config=CONFIG)
        unrelated = self.work / 'unrelated'
        unrelated.mkdir()
        (unrelated / 'manifest.json').write_text('{"model": "not retrieval"}')
        with self.assertRaisesRegex(ValueError, 'completed retrieval manifest'):
            retrieval.build_index(DATA / 'chunks.current.jsonl', unrelated, embedding_config=CONFIG)
        self.assertTrue((unrelated / 'manifest.json').exists())

    def test_failed_publication_restores_previous_index(self):
        for number, failure in enumerate((OSError('injected publication failure'), KeyboardInterrupt(), KeyboardInterrupt())):
            with self.subTest(failure=type(failure).__name__):
                target = self.work / ('rollback-index-' + str(number))
                shutil.copytree(self.index, target)
                original = (target / 'manifest.json').read_bytes()
                rename = Path.rename
                def fail_publication(path, destination):
                    if number == 2 and path.resolve() == target.resolve():
                        rename(path, destination)
                        raise failure
                    if path.name.startswith('.kstu-retrieval-') and not path.name.startswith('.kstu-retrieval-backup-') and Path(destination).resolve() == target.resolve():
                        raise failure
                    return rename(path, destination)
                with patch.object(Path, 'rename', fail_publication):
                    with self.assertRaises(type(failure)):
                        retrieval.build_index(DATA / 'chunks.current.jsonl', target, embedding_config=CONFIG)
                self.assertEqual((target / 'manifest.json').read_bytes(), original)
                with retrieval.Retriever(target, embedding_config=CONFIG) as restored:
                    self.assertEqual(len(restored.chunks), 30)

    def test_rebuild_preserves_ids_config_identity_and_vector_direction(self):
        rebuilt = self.work / 'rebuilt'
        manifest = retrieval.build_index(DATA / 'chunks.current.jsonl', rebuilt, embedding_config=CONFIG)
        for key in ('chunks_sha256', 'source_manifest_sha256', 'embedding_config_sha256', 'embedding'):
            self.assertEqual(manifest[key], self.manifest[key])
        self.assertEqual(read_rows(self.index / 'windows.jsonl'), read_rows(rebuilt / 'windows.jsonl'))
        original, _ = self.retriever.client.scroll(retrieval.COLLECTION, limit=10000, with_vectors=True)
        with retrieval.Retriever(rebuilt, embedding_config=CONFIG) as other:
            repeated, _ = other.client.scroll(retrieval.COLLECTION, limit=10000, with_vectors=True)
        first = {point.id: point for point in original}
        second = {point.id: point for point in repeated}
        self.assertEqual(set(first), set(second))
        for point_id, point in first.items():
            a, b = point.vector, second[point_id].vector
            cosine = sum(x * y for x, y in zip(a, b)) / math.sqrt(
                sum(x * x for x in a) * sum(y * y for y in b))
            self.assertGreater(cosine, 0.9999)



if __name__ == '__main__':
    unittest.main()
