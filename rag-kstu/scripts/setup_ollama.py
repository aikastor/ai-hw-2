#!/usr/bin/env python3
"""Install the pinned macOS Ollama CLI and prepare its local embedding model."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import tarfile
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
VERSION = '0.40.6'
URL = f'https://github.com/ollama/ollama/releases/download/v{VERSION}/ollama-darwin.tgz'
SHA256 = 'b2b55434865a668decb494110d7fd970eed3ecc8837be2872f672ccbb95df974'
RUNTIME = ROOT / 'rag-kstu/tools/ollama'
CONFIG = ROOT / 'rag-kstu/models/ollama-embedding.json'
MODELS = ROOT / 'rag-kstu/models/ollama'
MODEL = 'bge-m3:latest'
MODEL_DIGEST = '7907646426070047a77226ac3e684fbbe8410524f7b4a74d02837e43f2146bab'
HOST = 'http://127.0.0.1:11434'


def environment():
    env = os.environ.copy()
    env.update(OLLAMA_MODELS=str(MODELS), OLLAMA_HOST='127.0.0.1:11434', OLLAMA_NO_CLOUD='1')
    return env


def request(path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(HOST + path, data=data, headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req, timeout=120) as response:
        return json.load(response)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['install','serve','pull'])
    command = parser.parse_args().command
    executable = RUNTIME / 'ollama'
    if command == 'install':
        if platform.system() != 'Darwin':
            raise SystemExit('This pinned installer targets macOS. Install Ollama for your OS before using retrieval.')
        RUNTIME.mkdir(parents=True, exist_ok=True)
        archive = RUNTIME / 'ollama-darwin.tgz'
        if not archive.exists() or hashlib.sha256(archive.read_bytes()).hexdigest() != SHA256:
            urllib.request.urlretrieve(URL, archive)
        if hashlib.sha256(archive.read_bytes()).hexdigest() != SHA256:
            raise ValueError('Ollama release archive hash mismatch')
        with tarfile.open(archive) as source:
            source.extractall(RUNTIME, filter='data')
        print(f'Installed pinned Ollama {VERSION} at {executable}.')
    elif command == 'serve':
        if not executable.is_file():
            raise SystemExit('Run setup_ollama.py install first.')
        MODELS.mkdir(parents=True, exist_ok=True)
        os.execve(str(executable), [str(executable), 'serve'], environment())
    else:
        if not executable.is_file():
            raise SystemExit('Run setup_ollama.py install first.')
        version = request('/api/version')['version']
        if version != VERSION:
            raise ValueError(f'Expected Ollama {VERSION}; found {version}.')
        subprocess.run([str(executable), 'pull', MODEL], check=True, env=environment())
        tags = request('/api/tags')['models']
        record = next(r for r in tags if r['name'] == MODEL)
        if record['digest'] != MODEL_DIGEST:
            raise ValueError('Downloaded bge-m3 digest changed; review before updating the pinned model.')
        info = request('/api/show', {'model': MODEL}).get('model_info', {})
        config = {'provider':'ollama','model':MODEL,'model_digest':record['digest'],
                  'dimension':1024,'max_tokens':8192,'ollama_version':version,
                  'model_info':{k:v for k,v in info.items() if k.endswith(('embedding_length','context_length'))}}
        CONFIG.parent.mkdir(parents=True, exist_ok=True)
        CONFIG.write_text(json.dumps(config, indent=2)+'\n')
        print(json.dumps(config, indent=2))


if __name__ == '__main__':
    main()
