#!/usr/bin/env python3
"""Prepare the pinned embedding model and persistent index before API startup."""
import json
import os
from pathlib import Path
import sys
import time
from urllib.error import URLError
from urllib.request import Request, urlopen

from retrieval import DEFAULT_EMBEDDING_CONFIG, ROOT, Retriever, build_index


def request(host, path, payload=None, timeout=10):
    body = None if payload is None else json.dumps(payload).encode()
    headers = {} if body is None else {'Content-Type': 'application/json'}
    with urlopen(Request(host + path, data=body, headers=headers), timeout=timeout) as response:
        return json.load(response)


def prepare_model(host, config):
    deadline = time.monotonic() + 180
    while True:
        try:
            version = request(host, '/api/version')
            break
        except (URLError, TimeoutError) as error:
            if time.monotonic() >= deadline:
                raise RuntimeError('Ollama did not become ready within 180 seconds') from error
            time.sleep(2)
    if version.get('version') != config['ollama_version']:
        raise RuntimeError('Ollama version differs from the pinned embedding configuration')
    models = request(host, '/api/tags').get('models', [])
    matching = [model for model in models if model.get('name') == config['model']]
    if not matching:
        print('Downloading the pinned embedding model.', flush=True)
        result = request(host, '/api/pull', {'name': config['model'], 'stream': False}, timeout=1800)
        if result.get('status') != 'success':
            raise RuntimeError('Ollama model download did not complete successfully')
        models = request(host, '/api/tags').get('models', [])
        matching = [model for model in models if model.get('name') == config['model']]
    expected = config['model_digest'].removeprefix('sha256:')
    if len(matching) != 1 or matching[0].get('digest', '').removeprefix('sha256:') != expected:
        raise RuntimeError('Embedding model digest differs from the pin. Restore the pinned model before restarting; the existing model was not replaced.')


def bootstrap():
    config = json.loads(DEFAULT_EMBEDDING_CONFIG.read_text())
    host = os.environ.setdefault('OLLAMA_HOST', 'http://ollama:11434').rstrip('/')
    prepare_model(host, config)
    chunks = ROOT / 'rag-kstu/data/expanded/chunks.current.jsonl'
    index = Path(os.environ.get('KSTU_INDEX', '/var/lib/kstu/index')).resolve()
    if (index / 'manifest.json').is_file():
        try:
            with Retriever(index, DEFAULT_EMBEDDING_CONFIG) as retriever:
                if Path(retriever.manifest['chunks_path']).resolve() != chunks.resolve():
                    raise ValueError('Index belongs to another corpus')
        except Exception as error:
            raise RuntimeError(f'Persistent index validation failed ({type(error).__name__}: {error}). Stop the app and explicitly rebuild this index from the packaged expanded corpus, or choose a new KSTU_INDEX. The index was not rebuilt automatically.') from error
        print('Persistent expanded index verified.', flush=True)
        return
    if index.exists():
        if not index.is_dir() or any(index.iterdir()):
            raise RuntimeError('Index path has no manifest and is not empty. Choose an empty KSTU_INDEX or restore its manifest.')
        index.rmdir()
    print('Building the persistent expanded index.', flush=True)
    build_index(chunks, index, DEFAULT_EMBEDDING_CONFIG)
    with Retriever(index, DEFAULT_EMBEDDING_CONFIG):
        pass
    print('Persistent expanded index built and verified.', flush=True)


if __name__ == '__main__':
    try:
        bootstrap()
    except Exception as error:
        print(f'Bootstrap failed: {error}', file=sys.stderr)
        sys.exit(1)
