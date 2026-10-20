import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import docker_bootstrap as bootstrap


class ModelBootstrapTests(unittest.TestCase):
    def setUp(self):
        self.config = json.loads(bootstrap.DEFAULT_EMBEDDING_CONFIG.read_text())
        self.version = {'version': self.config['ollama_version']}
        self.tags = {'models': [{'name': self.config['model'], 'digest': self.config['model_digest']}]}

    def test_existing_model_is_not_downloaded(self):
        with patch.object(bootstrap, 'request', side_effect=[self.version, self.tags]) as request:
            bootstrap.prepare_model('http://ollama:11434', self.config)
        self.assertEqual(request.call_count, 2)

    def test_missing_model_is_downloaded_and_verified(self):
        responses = [self.version, {'models': []}, {'status': 'success'}, self.tags]
        with patch.object(bootstrap, 'request', side_effect=responses) as request:
            bootstrap.prepare_model('http://ollama:11434', self.config)
        self.assertEqual(request.call_args_list[2].args, (
            'http://ollama:11434', '/api/pull', {'name': self.config['model'], 'stream': False}))
        self.assertEqual(request.call_args_list[2].kwargs, {'timeout': 1800})
        self.assertEqual(request.call_count, 4)

    def test_existing_digest_mismatch_does_not_replace_model(self):
        wrong = {'models': [{'name': self.config['model'], 'digest': '0' * 64}]}
        with patch.object(bootstrap, 'request', side_effect=[self.version, wrong]) as request:
            with self.assertRaisesRegex(RuntimeError, 'digest differs'):
                bootstrap.prepare_model('http://ollama:11434', self.config)
        self.assertEqual(request.call_count, 2)

    def test_runtime_version_mismatch_stops_before_model_operations(self):
        with patch.object(bootstrap, 'request', return_value={'version': 'wrong'}) as request:
            with self.assertRaisesRegex(RuntimeError, 'version differs'):
                bootstrap.prepare_model('http://ollama:11434', self.config)
        request.assert_called_once_with('http://ollama:11434', '/api/version')


class IndexBootstrapTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.index = Path(self.directory.name) / 'index'
        self.chunks = bootstrap.ROOT / 'rag-kstu/data/expanded/chunks.current.jsonl'
        self.environment = patch.dict(os.environ, {'KSTU_INDEX': str(self.index)})
        self.environment.start()
        self.addCleanup(self.environment.stop)
        for name in ('prepare_model', 'build_index', 'Retriever'):
            patcher = patch.object(bootstrap, name)
            setattr(self, name, patcher.start())
            self.addCleanup(patcher.stop)
        self.Retriever.return_value.__enter__.return_value.manifest = {'chunks_path': str(self.chunks)}

    def test_existing_index_is_verified_and_reused(self):
        self.index.mkdir()
        (self.index / 'manifest.json').write_text('{}')
        bootstrap.bootstrap()
        self.build_index.assert_not_called()
        self.Retriever.assert_called_once_with(self.index.resolve(), bootstrap.DEFAULT_EMBEDDING_CONFIG)
        self.Retriever.return_value.__exit__.assert_called_once()

    def test_failed_integrity_does_not_rebuild_or_remove_index(self):
        self.index.mkdir()
        manifest = self.index / 'manifest.json'
        manifest.write_text('preserve')
        self.Retriever.side_effect = ValueError('hash drift')
        with self.assertRaisesRegex(RuntimeError, 'not rebuilt automatically'):
            bootstrap.bootstrap()
        self.build_index.assert_not_called()
        self.assertEqual(manifest.read_text(), 'preserve')

    def test_missing_index_is_built_and_verified(self):
        bootstrap.bootstrap()
        self.build_index.assert_called_once_with(self.chunks, self.index.resolve(), bootstrap.DEFAULT_EMBEDDING_CONFIG)
        self.Retriever.return_value.__exit__.assert_called_once()

    def test_empty_index_directory_can_be_built(self):
        self.index.mkdir()
        bootstrap.bootstrap()
        self.build_index.assert_called_once()
        self.assertFalse(self.index.exists())

    def test_nonempty_directory_without_manifest_is_preserved(self):
        self.index.mkdir()
        marker = self.index / 'unrelated'
        marker.write_text('preserve')
        with self.assertRaisesRegex(RuntimeError, 'not empty'):
            bootstrap.bootstrap()
        self.build_index.assert_not_called()
        self.Retriever.assert_not_called()
        self.assertEqual(marker.read_text(), 'preserve')


if __name__ == '__main__':
    unittest.main()
