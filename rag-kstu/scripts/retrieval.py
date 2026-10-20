#!/usr/bin/env python3
"""Offline, scoped KSTU retrieval. Results are evidence candidates, never answers."""
import argparse
from collections import Counter
import math
import os
import hashlib
import ipaddress
import json
import re
import shutil
import sys
import tempfile
import uuid
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[2] if (Path(__file__).resolve().parent.parent / 'UNIVERSITY.md').exists() else Path.cwd()
DEFAULT_CHUNKS = ROOT / 'rag-kstu/data/chunks.current.jsonl'
DEFAULT_INDEX = ROOT / 'rag-kstu/data/retrieval'
DEFAULT_EMBEDDING_CONFIG = ROOT / 'rag-kstu/models/ollama-embedding.json'
SOURCE_MANIFEST = ROOT / 'rag-kstu/data/source-manifest.json'
COLLECTION = 'kstu_current'
CATEGORIES = {'prospective student', 'current student', 'calendar'}
SCOPES = {
    'masters-': 'masters_admissions',
    'tokmok-': 'tokmok_admissions',
    'tuition-33d': 'logistics_tuition',
    'tuition-757': 'railway_tuition',
    'calendar-': 'calendar_fulltime_bachelor_specialist',
}
SETTINGS = {'embedding_unit': 'full_parent', 'context_enforcement': 'server truncate=false', 'rrf_k': 60,
            'dense_parent_aggregation': 'max', 'lexical_tokenizer': 'Unicode word lowercase',
            'scope_map': SCOPES, 'collection': COLLECTION,
            'bm25_idf': 'log(1 + (N - df + 0.5)/(df + 0.5))'}


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def read_jsonl(path):
    return [json.loads(line) for line in Path(path).read_text(encoding='utf-8').splitlines() if line.strip()]


def write_json(path, value):
    Path(path).write_text(canonical(value) + '\n', encoding='utf-8')


def write_jsonl(path, rows):
    Path(path).write_text(''.join(canonical(row) + '\n' for row in rows), encoding='utf-8')


def scope_for(chunk):
    if chunk.get('scope') in {'bachelor_programmes', 'bachelor_admissions', 'general_academic_policy'}:
        return chunk['scope']
    matches = [scope for prefix, scope in SCOPES.items() if chunk['selection_id'].startswith(prefix)]
    if len(matches) != 1:
        raise ValueError('Current chunk has no unique reviewed scope: ' + chunk['selection_id'])
    return matches[0]


def manifest_for(chunks_path):
    candidate = Path(chunks_path).resolve().parent / 'source-manifest.json'
    return candidate if candidate.is_file() else SOURCE_MANIFEST


def validate_corpus(chunks_path):
    """Archives are validated for source completeness but never returned or embedded."""
    sys.path.insert(0, str(ROOT / 'rag-kstu/scripts'))
    from validate_chunks import validate_records, validate_coverage
    chunks_path = Path(chunks_path).resolve()
    source_manifest = manifest_for(chunks_path)
    if read_json(source_manifest).get('kind') == 'reviewed_expansion':
        from expanded_sources import validate_expansion
        return validate_expansion(chunks_path)
    current = read_jsonl(chunks_path)
    archive = read_jsonl(chunks_path.parent / 'chunks.archive.jsonl')
    manifest = read_json(SOURCE_MANIFEST)
    validate_records(manifest, current + archive)
    validate_coverage(manifest, read_json(chunks_path.parent / 'coverage.json'))
    if not current:
        raise ValueError('Current corpus is empty')
    for chunk in current:
        if (chunk['eligibility'] != 'current' or chunk.get('current_answer_eligible') is not True
                or chunk['university_id'] != 'kstu'
                or chunk['academic_year'] != manifest['target_academic_year']):
            raise ValueError('Ineligible chunk in current corpus')
        scope_for(chunk)
    return current


class OllamaEmbedder:
    """Pinned bge-m3 on local or explicitly enabled Compose Ollama."""
    def __init__(self, embedding_config=DEFAULT_EMBEDDING_CONFIG):
        self.config_path = Path(embedding_config).resolve()
        config_bytes = self.config_path.read_bytes()
        self.config = json.loads(config_bytes)
        self.config_hash = sha(config_bytes)
        required = {'provider', 'model', 'model_digest', 'dimension', 'max_tokens', 'ollama_version'}
        if (not isinstance(self.config, dict) or not required <= self.config.keys()
                or self.config['provider'] != 'ollama' or self.config['model'] != 'bge-m3:latest'
                or type(self.config['dimension']) is not int or self.config['dimension'] != 1024
                or type(self.config['max_tokens']) is not int or self.config['max_tokens'] != 8192
                or not isinstance(self.config['model_digest'], str)
                or re.fullmatch(r'(?:sha256:)?[0-9a-f]{64}', self.config['model_digest']) is None
                or not isinstance(self.config['ollama_version'], str) or not self.config['ollama_version']):
            raise ValueError('Unsupported Ollama embedding config; pin bge-m3:latest, its digest, 1024 dimensions and 8192 tokens')
        self.dimension = self.config['dimension']
        host = os.environ.get('OLLAMA_HOST', 'http://127.0.0.1:11434')
        self.base_url = self._loopback_url(host)
        self._verify_identity()
        details = self._request('POST', '/api/show', {'model': self.config['model'], 'verbose': True})
        capabilities = details.get('capabilities')
        if capabilities is not None and (not isinstance(capabilities, list) or 'embedding' not in capabilities):
            raise ValueError('Pinned Ollama model does not support embeddings')
        model_info = details.get('model_info', {})
        if not isinstance(model_info, dict):
            raise ValueError('Ollama returned invalid model metadata')
        for name, value in model_info.items():
            if name.endswith('.embedding_length') and value != self.dimension:
                raise ValueError('Ollama model embedding dimension differs from config')
            if name.endswith('.context_length') and (type(value) is not int or value < self.config['max_tokens']):
                raise ValueError('Ollama model context is shorter than configured embedding context')
        self.identity = {key: self.config[key] for key in sorted(required)}

    def _verify_identity(self):
        version = self._request('GET', '/api/version')
        if version.get('version') != self.config['ollama_version']:
            raise ValueError('Ollama runtime version differs from pinned embedding config')
        tags = self._request('GET', '/api/tags')
        models = tags.get('models')
        if not isinstance(models, list) or any(not isinstance(model, dict) for model in models):
            raise ValueError('Ollama returned an invalid model listing')
        matches = [model for model in models if model.get('name') == self.config['model']]
        if len(matches) != 1 or matches[0].get('digest') != self.config['model_digest']:
            raise ValueError('Ollama bge-m3 model is missing or its digest differs from pinned embedding config')

    @staticmethod
    def _loopback_url(host):
        if host == 'http://ollama:11434' and os.environ.get('KSTU_ALLOW_DOCKER_OLLAMA') == '1':
            return host
        if not isinstance(host, str) or not host.strip():
            raise ValueError('OLLAMA_HOST must be a loopback HTTP URL')
        parsed = urlsplit(host if '://' in host else 'http://' + host)
        try:
            hostname, port = parsed.hostname, parsed.port
            address = ipaddress.ip_address('127.0.0.1' if hostname == 'localhost' else hostname)
        except ValueError as error:
            raise ValueError('OLLAMA_HOST must use localhost or a loopback IP address') from error
        if (parsed.scheme not in {'http', 'https'} or not address.is_loopback
                or parsed.username is not None or parsed.password is not None
                or parsed.path not in {'', '/'} or parsed.query or parsed.fragment or port == 0):
            raise ValueError('OLLAMA_HOST must be a loopback HTTP URL without credentials, path, query or fragment')
        literal = '[' + str(address) + ']' if address.version == 6 else str(address)
        return parsed.scheme + '://' + literal + ':' + str(port or 11434)

    def _request(self, method, path, payload=None):
        import httpx
        try:
            # Ignore proxy environment variables and never follow redirects away from the configured endpoint.
            with httpx.Client(base_url=self.base_url, timeout=300, trust_env=False,
                              follow_redirects=False) as client:
                response = client.request(method, path, json=payload)
            if not response.is_success:
                raise ValueError('Ollama ' + path + ' failed (HTTP ' + str(response.status_code)
                                 + '): ' + response.text[:500])
            data = response.json()
        except httpx.RequestError as error:
            raise ValueError('Local Ollama is unavailable at ' + self.base_url
                             + '; start the pinned runtime and install the pinned bge-m3 model') from error
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            raise ValueError('Ollama returned invalid JSON for ' + path) from error
        if not isinstance(data, dict) or data.get('error'):
            detail = data.get('error') if isinstance(data, dict) else type(data).__name__
            raise ValueError('Ollama returned an invalid response for ' + path + ': ' + str(detail))
        return data

    def windows(self, text, chunk_id):
        """One original-text span; /api/embed rejects over-context input with truncate=false."""
        if not isinstance(text, str) or not text.strip():
            raise ValueError('Cannot embed empty text')
        digest = sha(text.encode())
        identity = canonical([chunk_id, 0, len(text), digest])
        return [{'window_id': str(uuid.uuid5(uuid.NAMESPACE_URL, identity)),
                 'chunk_id': chunk_id, 'start': 0, 'end': len(text),
                 'text_sha256': digest, 'context_enforcement': 'server truncate=false'}]

    def embed(self, texts):
        if any(not isinstance(text, str) or not text.strip() for text in texts):
            raise ValueError('Cannot embed empty text')
        vectors = []
        for offset in range(0, len(texts), 4):
            batch = texts[offset:offset + 4]
            self._verify_identity()
            data = self._request('POST', '/api/embed', {
                'model': self.config['model'], 'input': batch, 'truncate': False,
                'keep_alive': '5m', 'options': {'num_ctx': self.config['max_tokens']}})
            self._verify_identity()
            if data.get('model') != self.config['model']:
                raise ValueError('Ollama embedding response model differs from pinned model')
            embeddings = data.get('embeddings')
            if not isinstance(embeddings, list) or len(embeddings) != len(batch):
                raise ValueError('Ollama embedding response count differs from input count')
            for vector in embeddings:
                if (not isinstance(vector, list) or len(vector) != self.dimension
                        or any(type(value) not in (int, float) or not math.isfinite(value) for value in vector)):
                    raise ValueError('Ollama returned a non-finite or wrong-dimension embedding')
                norm = math.sqrt(math.fsum(value * value for value in vector))
                if not math.isclose(norm, 1.0, rel_tol=1e-3, abs_tol=1e-3):
                    raise ValueError('Ollama returned an embedding without unit norm')
                vectors.append(vector)
        return vectors

    def embed_queries(self, texts):
        return self.embed(texts)

    def embed_passages(self, texts):
        return self.embed(texts)


def point_fingerprint(points):
    values = [{'id': str(point.id), 'payload': point.payload, 'vector': point.vector} for point in points]
    return sha(canonical(sorted(values, key=lambda row: row['id'])).encode())


def _build_index(chunks_path=DEFAULT_CHUNKS, index_dir=DEFAULT_INDEX, embedding_config=DEFAULT_EMBEDDING_CONFIG):
    from qdrant_client import QdrantClient, models
    chunks_path, index_dir = Path(chunks_path).resolve(), Path(index_dir).resolve()
    chunks = validate_corpus(chunks_path)
    source_manifest = manifest_for(chunks_path)
    embedder = OllamaEmbedder(embedding_config)
    windows = [window for chunk in chunks for window in embedder.windows(chunk['text'], chunk['chunk_id'])]
    by_id = {chunk['chunk_id']: chunk for chunk in chunks}
    vectors = embedder.embed_passages([by_id[w['chunk_id']]['text'][w['start']:w['end']] for w in windows])
    points = []
    for window, vector in zip(windows, vectors):
        chunk = by_id[window['chunk_id']]
        payload = dict(window, eligibility='current', current_answer_eligible=True, university_id='kstu',
                       academic_year=chunk['academic_year'], categories=[chunk['category']] + chunk['additional_categories'],
                       topic=chunk['topic'], scope=scope_for(chunk))
        points.append(models.PointStruct(id=window['window_id'], vector=vector, payload=payload))
    if index_dir.exists() and not (index_dir / 'manifest.json').exists():
        raise ValueError('Refusing to replace a directory without a completed retrieval manifest')
    index_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix='.kstu-retrieval-', dir=index_dir.parent))
    try:
        write_jsonl(staging / 'chunks.jsonl', chunks)
        write_jsonl(staging / 'windows.jsonl', windows)
        client = QdrantClient(path=str(staging / 'qdrant'))
        try:
            client.create_collection(COLLECTION, vectors_config=models.VectorParams(size=embedder.dimension, distance=models.Distance.COSINE))
            client.upsert(COLLECTION, points=points, wait=True)
        finally:
            client.close()
        # Qdrant normalizes persisted cosine vectors on reload. Fingerprint that
        # reopened representation, which is what every later reader observes.
        client = QdrantClient(path=str(staging / 'qdrant'))
        try:
            stored, _ = client.scroll(COLLECTION, limit=len(points) + 1, with_vectors=True)
            fingerprint = point_fingerprint(stored)
        finally:
            client.close()
        files = {str(path.relative_to(staging)): sha(path.read_bytes())
                 for path in sorted(staging.rglob('*')) if path.is_file() and path.name != '.lock'}
        manifest = {'schema_version': 2, 'status': 'complete', 'chunks_path': str(chunks_path),
                    'chunks_sha256': sha(chunks_path.read_bytes()),
                    'source_manifest_path': str(source_manifest),
                    'source_manifest_sha256': sha(source_manifest.read_bytes()),
                    'embedding_config_sha256': embedder.config_hash, 'embedding': embedder.identity,
                    'chunk_count': len(chunks), 'point_count': len(points), 'settings': SETTINGS,
                    'stored_vector_fingerprint': fingerprint, 'files': files}
        write_json(staging / 'manifest.json', manifest)
        backup = None
        if index_dir.exists():
            backup = Path(tempfile.mkdtemp(prefix='.kstu-retrieval-backup-', dir=index_dir.parent))
            backup.rmdir()
        try:
            if backup is not None:
                index_dir.rename(backup)
            staging.rename(index_dir)
        except BaseException:
            if backup is not None and backup.exists() and not index_dir.exists():
                backup.rename(index_dir)
            raise
        if backup is not None:
            shutil.rmtree(backup)
        return manifest
    finally:
        if staging.exists():
            shutil.rmtree(staging)


def index_lock_path(index_dir):
    path = Path(index_dir).resolve()
    return path.parent / ('.' + path.name + '.retrieval.lock')


def build_index(chunks_path=DEFAULT_CHUNKS, index_dir=DEFAULT_INDEX, embedding_config=DEFAULT_EMBEDDING_CONFIG):
    import portalocker
    original_index = Path(index_dir)
    target = original_index.resolve()
    protected = [Path(chunks_path).resolve(), SOURCE_MANIFEST, Path(embedding_config).resolve()]
    if original_index.is_symlink() or any(path.is_relative_to(target) for path in protected) or target.is_relative_to((ROOT / 'rag-kstu/models').resolve()):
        raise ValueError('Index path overlaps protected corpus or embedding model files')
    if target.exists():
        previous = read_json(target / 'manifest.json') if (target / 'manifest.json').is_file() else {}
        if previous.get('status') != 'complete' or previous.get('settings', {}).get('collection') != COLLECTION:
            raise ValueError('Refusing to replace a directory without a completed retrieval manifest')
        allowed = set(previous.get('files', {})) | {'manifest.json'}
        if any(str(path.relative_to(target)) not in allowed and path.name != '.lock'
               for path in target.rglob('*') if path.is_file()):
            raise ValueError('Refusing to replace retrieval directory containing untracked files')
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        with portalocker.Lock(str(index_lock_path(target)), timeout=0):
            return _build_index(chunks_path, target, embedding_config)
    except portalocker.exceptions.LockException as error:
        raise ValueError('Retrieval index is in use; close active searches before rebuilding') from error


class Retriever:
    def __init__(self, index_dir=DEFAULT_INDEX, embedding_config=DEFAULT_EMBEDDING_CONFIG):
        import portalocker
        self.client = None
        self.index_lock = portalocker.Lock(str(index_lock_path(index_dir)), timeout=0)
        try:
            self.index_lock.acquire()
            self._open(index_dir, embedding_config)
        except Exception:
            self.close()
            raise

    def _open(self, index_dir=DEFAULT_INDEX, embedding_config=DEFAULT_EMBEDDING_CONFIG):
        from qdrant_client import QdrantClient
        self.index_dir = Path(index_dir).resolve()
        self.manifest = read_json(self.index_dir / 'manifest.json')
        self.client = None
        if (self.manifest.get('schema_version') != 2 or self.manifest.get('status') != 'complete'
                or self.manifest.get('settings') != SETTINGS):
            raise ValueError('Incomplete or incompatible index; rebuild retrieval')
        for name, expected in self.manifest['files'].items():
            path = (self.index_dir / name).resolve()
            if not path.is_relative_to(self.index_dir) or sha(path.read_bytes()) != expected:
                raise ValueError('Retrieval artifact hash drift: ' + name)
        self._check_corpus()
        validate_corpus(Path(self.manifest['chunks_path']))
        self.chunks = read_jsonl(self.index_dir / 'chunks.jsonl')
        self.by_id = {chunk['chunk_id']: chunk for chunk in self.chunks}
        self.windows = read_jsonl(self.index_dir / 'windows.jsonl')
        if len(self.chunks) != self.manifest['chunk_count'] or len(self.windows) != self.manifest['point_count']:
            raise ValueError('Index record count mismatch')
        self.embedder = OllamaEmbedder(embedding_config)
        if (self.embedder.config_hash != self.manifest['embedding_config_sha256']
                or self.embedder.identity != self.manifest['embedding']):
            raise ValueError('Index embedding model differs; rebuild retrieval')
        self.client = QdrantClient(path=str(self.index_dir / 'qdrant'))
        try:
            points, _ = self.client.scroll(COLLECTION, limit=self.manifest['point_count'] + 1, with_vectors=True)
            if point_fingerprint(points) != self.manifest['stored_vector_fingerprint']:
                raise ValueError('Stored vector index differs; rebuild retrieval')
        except Exception:
            self.close()
            raise

    def _check_corpus(self):
        path = Path(self.manifest['chunks_path'])
        if (sha(path.read_bytes()) != self.manifest['chunks_sha256']
                or sha(Path(self.manifest.get('source_manifest_path', SOURCE_MANIFEST)).read_bytes()) != self.manifest['source_manifest_sha256']):
            raise ValueError('Published corpus changed; rebuild retrieval')

    def close(self):
        if self.client is not None:
            self.client.close()
            self.client = None
        if getattr(self, 'index_lock', None) is not None:
            self.index_lock.release()
            self.index_lock = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def search(self, query, *, category=None, academic_year='2026-2027', scope=None,
               topic=None, top_k=5, mode='hybrid'):
        from qdrant_client import models
        from rank_bm25 import BM25Okapi
        if category is not None and category not in CATEGORIES:
            raise ValueError('Invalid category')
        if mode not in {'dense', 'bm25', 'hybrid'}:
            raise ValueError('Mode must be dense, bm25, or hybrid')
        if not isinstance(query, str) or not query.strip():
            raise ValueError('Query must contain text')
        if type(top_k) is not int or top_k < 1:
            raise ValueError('top_k must be a positive integer')
        self._check_corpus()
        eligible = [chunk for chunk in self.chunks
                    if chunk['eligibility'] == 'current' and chunk['current_answer_eligible'] is True
                    and chunk['university_id'] == 'kstu' and chunk['academic_year'] == academic_year
                    and (category is None or category in [chunk['category']] + chunk['additional_categories'])
                    and (scope is None or scope_for(chunk) == scope)
                    and (topic is None or topic in chunk['topic'])]
        base = {'status': 'candidates' if eligible else 'no_matching_scope', 'hits': [],
                'answerability': 'not_assessed', 'scope': scope, 'mode': mode}
        if not eligible:
            return base
        dense, lexical = {}, {}
        if mode in {'dense', 'hybrid'}:
            clauses = [('eligibility', 'current'), ('current_answer_eligible', True),
                       ('university_id', 'kstu'), ('academic_year', academic_year)]
            clauses.extend((key, value) for key, value in [('categories', category), ('scope', scope), ('topic', topic)]
                           if value is not None)
            query_filter = models.Filter(must=[models.FieldCondition(key=key, match=models.MatchValue(value=value))
                                               for key, value in clauses])
            vector = self.embedder.embed_queries([query])[0]
            result = self.client.query_points(COLLECTION, query=vector, query_filter=query_filter,
                                              limit=self.manifest['point_count'], with_payload=True)
            allowed = {chunk['chunk_id'] for chunk in eligible}
            for point in result.points:
                cid = point.payload['chunk_id']
                if cid not in allowed:
                    raise ValueError('Vector query violated metadata isolation')
                dense[cid] = max(dense.get(cid, float('-inf')), point.score)
        if mode in {'bm25', 'hybrid'}:
            tokenize = lambda text: re.findall(r'\w+', text.lower(), flags=re.UNICODE)
            corpus = [tokenize(chunk['text']) for chunk in eligible]
            if any(corpus):
                bm25 = BM25Okapi(corpus)
                frequencies = Counter(token for document in corpus for token in set(document))
                # Positive Okapi IDF also works for a filtered one-document scope.
                bm25.idf = {token: math.log1p((len(corpus) - count + 0.5) / (count + 0.5))
                            for token, count in frequencies.items()}
                scores = bm25.get_scores(tokenize(query))
                lexical = {chunk['chunk_id']: float(score) for chunk, score in zip(eligible, scores) if score > 0}
        ranks = {}
        for scores in (dense, lexical):
            for rank, cid in enumerate(sorted(scores, key=lambda cid: (-scores[cid], cid)), 1):
                ranks[cid] = ranks.get(cid, 0.0) + 1 / (SETTINGS['rrf_k'] + rank)
        chosen = ranks if mode == 'hybrid' else dense if mode == 'dense' else lexical
        for cid in sorted(chosen, key=lambda cid: (-chosen[cid], cid))[:top_k]:
            base['hits'].append(dict(self.by_id[cid], scope=scope_for(self.by_id[cid]),
                                     dense_score=dense.get(cid), bm25_score=lexical.get(cid),
                                     rrf_score=ranks.get(cid, 0.0)))
        return base


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    for name in ('build', 'search'):
        command = commands.add_parser(name)
        command.add_argument('--index', type=Path, default=DEFAULT_INDEX)
        command.add_argument('--embedding-config', type=Path, default=DEFAULT_EMBEDDING_CONFIG)
        if name == 'build':
            command.add_argument('--chunks', type=Path, default=DEFAULT_CHUNKS)
        else:
            command.add_argument('query')
            command.add_argument('--category', choices=sorted(CATEGORIES))
            command.add_argument('--academic-year', default='2026-2027')
            command.add_argument('--scope')
            command.add_argument('--topic')
            command.add_argument('--top-k', type=int, default=5)
            command.add_argument('--mode', choices=['dense', 'bm25', 'hybrid'], default='hybrid')
    args = parser.parse_args()
    if args.command == 'build':
        result = build_index(args.chunks, args.index, args.embedding_config)
    else:
        with Retriever(args.index, args.embedding_config) as retriever:
            result = retriever.search(args.query, category=args.category, academic_year=args.academic_year,
                                      scope=args.scope, topic=args.topic, top_k=args.top_k, mode=args.mode)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
