#!/usr/bin/env python3
"""Export only reviewed inputs and application files into a new standalone directory."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import tempfile

ROOT = Path(__file__).resolve().parents[2]
APP = 'rag-kstu/'
FILES = [
    '.env.example', '.gitignore', 'README.md', 'UNIVERSITY.md',
    'ATTRIBUTION.md', 'requirements-chunking.txt', 'requirements-retrieval.txt',
    'requirements-chat.txt', 'models/ollama-embedding.json',
    'data/source-manifest.json', 'data/chunks.current.jsonl', 'data/chunks.archive.jsonl',
    'data/build-stats.json', 'data/coverage.json', 'data/validation.json', 'data/exclusions.json',
    'data/shortlist-snapshot.json', 'data/REPORT.md',
    'data/retrieval-validation.json',
    'data/expanded/source-manifest.json', 'data/expanded/chunks.current.jsonl',
    'data/expanded/chunks.archive.jsonl', 'data/expanded/build-stats.json',
    'data/expanded/validation.json', 'data/expanded/review/policies.json',
    'data/expanded/review/programmes-research.md',
    'evaluation/questions.jsonl', 'evaluation/retrieval-heldout.jsonl',
    'evaluation/retrieval-results.json', 'evaluation/generation-final.jsonl',
    'evaluation/generation-final-manifest.json', 'evaluation/chat-results.json',
    'evaluation/chat-filter-results.json', 'evaluation/verification.json',
    'evaluation/expanded-smoke.jsonl', 'evaluation/expanded-smoke-results.json', 'evaluation/validation-ru.md',
    'docker/Dockerfile', 'docker/compose.yaml', 'docker/dockerignore',
    'scripts/docker_bootstrap.py', 'scripts/test_docker_bootstrap.py', 'scripts/retrieval.py', 'scripts/run_teacher.py', 'scripts/setup_ollama.py', 'scripts/build_chunks.py',
    'scripts/validate_chunks.py', 'scripts/test_chunks.py', 'scripts/test_retrieval.py',
    'scripts/test_chat.py', 'scripts/evaluate_chat.py', 'scripts/check_chat_filters.py', 'scripts/package_repository.py',
    'scripts/test_package_repository.py', 'scripts/verify_package.py',
    'scripts/prepare_expansion.py', 'scripts/expanded_sources.py', 'scripts/test_expanded_sources.py',
    'app/__init__.py', 'app/models.py', 'app/config.py', 'app/groq.py',
    'app/grounding.py', 'app/api.py', 'app/frontend.py',
    'app/prompts/generate.txt', 'app/prompts/verify.txt',
]
SECRET = re.compile(rb'(?:gsk_[A-Za-z0-9]{20,}|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|sk-proj-[A-Za-z0-9_-]{20,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----)')


def digest(path):
    with path.open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def safe_file(root, relative):
    path = PurePosixPath(relative)
    if path.is_absolute() or not path.parts or '..' in path.parts or '\\' in relative or str(path) != relative:
        raise ValueError('Unsafe package path: ' + relative)
    candidate = root
    for part in path.parts:
        candidate = candidate / part
        if candidate.is_symlink():
            raise ValueError('Symlink forbidden: ' + relative)
    if not candidate.is_file() or not candidate.resolve().is_relative_to(root.resolve()):
        raise ValueError('Missing or unsafe package file: ' + relative)
    if candidate.stat().st_size >= 100 * 1024 * 1024:
        raise ValueError('GitHub file limit exceeded: ' + relative)
    return candidate


def selected_files(root=ROOT):
    manifest = json.loads(safe_file(root, APP + 'data/source-manifest.json').read_text())
    files = {APP + name: None for name in FILES}
    for relative, expected in manifest['inputs'].items():
        path = safe_file(root, relative)
        if digest(path) != expected:
            raise ValueError('Pinned input hash drift: ' + relative)
        files[relative] = expected
    expansion = json.loads(safe_file(root, APP + 'data/expanded/source-manifest.json').read_text())
    pins = [(expansion[name + '_path'], expansion[name + '_sha256'])
            for name in ('base_manifest', 'base_current', 'base_archive')]
    for selection in expansion['supplements']:
        source = selection['source']
        pins.append((source['raw_path'], source['source_sha256']))
        refs = [selection['review_ref']] + selection.get('context', []) + selection.get('refs', [])
        refs += [ref for unit in selection.get('units', []) for ref in unit['parts']]
        pins.extend((ref['artifact_path'], ref['artifact_sha256']) for ref in refs)
    for relative, expected in pins:
        if digest(safe_file(root, relative)) != expected:
            raise ValueError('Pinned expansion input hash drift: ' + relative)
        files[relative] = expected
    for relative in sorted(files):
        path = safe_file(root, relative)
        if SECRET.search(path.read_bytes()):
            raise ValueError('Credential pattern detected: ' + relative)
    return sorted(files)


def export(destination, root=ROOT):
    destination = Path(destination).absolute()
    if destination.exists() or destination.is_symlink():
        raise ValueError('Destination already exists; refusing overwrite')
    if destination.is_relative_to(root / 'rag-kstu'):
        raise ValueError('Export outside the application directory')
    files = selected_files(root)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.kstu-export-', dir=destination.parent) as temp:
        stage = Path(temp) / 'repository'
        stage.mkdir()
        inventory = []
        for relative in files:
            source = safe_file(root, relative)
            target = stage / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            value = digest(target)
            if value != digest(source):
                raise ValueError('Copy hash mismatch: ' + relative)
            inventory.append({'path': relative, 'sha256': value, 'bytes': target.stat().st_size})
        (stage / '.gitignore').write_text((root / 'rag-kstu/.gitignore').read_text())
        (stage / 'README.md').write_text('# Чат-помощник КГТУ\n\nОтветы на русском и английском по официальным источникам КГТУ, со ссылками на документы.\n\n## Запуск для преподавателя через Docker\n\nНужны **Docker Desktop** (либо Docker Engine с Compose), интернет и собственный ключ Groq. Python и Ollama отдельно устанавливать не нужно.\n\n```sh\ngit clone https://github.com/aikastor/ai-hw-2.git\ncd ai-hw-2\ncp rag-kstu/.env.example rag-kstu/.env\n```\n\nВ Windows PowerShell используйте `Copy-Item` вместо `cp`, если требуется. Откройте `rag-kstu/.env` и укажите свой `GROQ_API_KEY`, затем:\n\n```sh\ndocker compose up --build\n```\n\nОткройте **http://localhost:8501** после готовности сервисов. Первый запуск скачивает образы и модель bge-m3 (около 1,2 ГБ), затем создаёт индекс. Повторные запуски используют сохранённые модель и базу.\n\nДля остановки — Ctrl+C или `docker compose down`. Не добавляйте `-v`, если хотите сохранить данные. Docker использует ресурсы вашего компьютера; приложение не размещается в облаке.\n\n## Документация\n\n- [Подробная инструкция и устранение проблем](rag-kstu/README.md).\n- [Вопросы для проверки на русском](rag-kstu/evaluation/validation-ru.md).\n\n## Данные и технологии\n\nCompose запускает Ollama, FastAPI со встроенной локальной Qdrant и Streamlit. Поиск объединяет BM25 и bge-m3. Groq генерирует и проверяет ответы; выбранные источники и сообщения передаются этому внешнему сервису. Ключ доступен только API.\n\nКаталоги `rag-kstu/data/` и `data/` содержат проверенные материалы для воспроизводимой сборки. Сбор сайта и OCR повторять не нужно. Секреты, виртуальные окружения, модель и сгенерированная база исключены из Git и контекста сборки.\n\nПокрытие неполное: общеуниверситетские пороги ОРТ и квоты грантов на бакалавриат ещё не подтверждены. Проверочные вопросы описывают ожидаемое поведение, а не гарантируют прохождение всех тестов.\n\nАвторство университетских документов сохранено: [атрибуция](rag-kstu/ATTRIBUTION.md).\n')
        for name, source_name in {'Dockerfile': 'Dockerfile', 'compose.yaml': 'compose.yaml', '.dockerignore': 'dockerignore'}.items():
            shutil.copyfile(root / 'rag-kstu/docker' / source_name, stage / name)
        for name in ['.gitignore', 'README.md', 'Dockerfile', 'compose.yaml', '.dockerignore']:
            target = stage / name
            inventory.append({'path': name, 'sha256': digest(target), 'bytes': target.stat().st_size})
        (stage / 'PACKAGE-INVENTORY.json').write_text(json.dumps({'schema_version': 1, 'files': sorted(inventory, key=lambda r:r['path'])}, indent=2)+'\n')
        stage.rename(destination)
    return {'destination': str(destination), 'files': len(inventory), 'bytes': sum(r['bytes'] for r in inventory)}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('destination', type=Path)
    args = parser.parse_args()
    print(json.dumps(export(args.destination), indent=2))
