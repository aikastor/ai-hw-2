#!/usr/bin/env python3
"""Установка и запуск локального приложения на macOS (Python 3.13)."""
import getpass
import json
import os
from pathlib import Path
import platform
import socket
import subprocess
import sys
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / 'rag-kstu'


def fetch(url):
    with urllib.request.urlopen(url, timeout=5) as response:
        return json.load(response)


def free_port(port):
    with socket.socket() as connection:
        return connection.connect_ex(('127.0.0.1', port)) != 0


def main():
    if '--help' in sys.argv:
        print(__doc__)
        print('Запуск: python3.13 rag-kstu/scripts/run_teacher.py')
        print('Ключ Groq вводится скрыто; Ctrl+C останавливает запущенные скриптом процессы.')
        return
    if sys.version_info[:2] != (3, 13) or platform.system() != 'Darwin':
        raise SystemExit('Для автоматического запуска нужны macOS и Python 3.13. См. README для ручной установки.')
    for port in (8000, 8501):
        if not free_port(port):
            raise SystemExit(f'Порт {port} занят. Сначала остановите ранее запущенное приложение.')
    os.chdir(ROOT)
    python = APP / '.venv-retrieval/bin/python'
    if not python.exists():
        subprocess.run([sys.executable, '-m', 'venv', str(APP / '.venv-retrieval')], check=True)
    if os.environ.get('KSTU_LAUNCHER_READY') != '1':
        subprocess.run([str(python), '-m', 'pip', 'install', '-r', str(APP / 'requirements-chat.txt')], check=True)
        env = dict(os.environ, KSTU_LAUNCHER_READY='1')
        os.execve(str(python), [str(python), str(Path(__file__).resolve())], env)
    from dotenv import dotenv_values
    key = os.environ.get('GROQ_API_KEY') or dotenv_values(APP / '.env').get('GROQ_API_KEY')
    if not key or key == 'replace-with-your-groq-key':
        key = getpass.getpass('Введите ваш GROQ_API_KEY (ввод скрыт, ключ не сохраняется): ').strip()
    if not key:
        raise SystemExit('Для генерации ответов нужен ключ Groq.')
    env = dict(os.environ, GROQ_API_KEY=key, PYTHONPATH=str(APP),
               KSTU_INDEX=str(APP / 'data/retrieval-expanded'))
    logs = APP / '.run-logs'
    logs.mkdir(exist_ok=True)
    processes = []
    handles = []

    def start(name, args, child_env):
        log = (logs / (name + '.log')).open('w')
        handles.append(log)
        process = subprocess.Popen(args, cwd=ROOT, env=child_env, stdout=log, stderr=subprocess.STDOUT)
        processes.append(process)
        return process

    def wait_ready(url, process, timeout=120):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if process is not None and process.poll() is not None:
                raise RuntimeError(f'Процесс завершился. Проверьте журнал в {logs}')
            try:
                with urllib.request.urlopen(url, timeout=5) as response:
                    if response.status == 200:
                        return
            except (OSError, ValueError):
                pass
            time.sleep(1)
        raise RuntimeError(f'Сервис не готов: {url}. Проверьте журналы в {logs}')

    try:
        try:
            version = fetch('http://127.0.0.1:11434/api/version')
        except OSError:
            version = None
        if version is None:
            if not (APP / 'tools/ollama/ollama').exists():
                subprocess.run([str(python), str(APP / 'scripts/setup_ollama.py'), 'install'], check=True)
            ollama = start('ollama', [str(python), str(APP / 'scripts/setup_ollama.py'), 'serve'], os.environ.copy())
            wait_ready('http://127.0.0.1:11434/api/version', ollama)
            version = fetch('http://127.0.0.1:11434/api/version')
        config = json.loads((APP / 'models/ollama-embedding.json').read_text())
        if version['version'] != config['ollama_version']:
            raise RuntimeError('Версия уже работающего Ollama не совпадает с закреплённой версией. См. README.')
        models = fetch('http://127.0.0.1:11434/api/tags')['models']
        if not any(m.get('name') == config['model'] and m.get('digest') == config['model_digest'] for m in models):
            if not (APP / 'tools/ollama/ollama').exists():
                subprocess.run([str(python), str(APP / 'scripts/setup_ollama.py'), 'install'], check=True)
            subprocess.run([str(python), str(APP / 'scripts/setup_ollama.py'), 'pull'], check=True)
        index = APP / 'data/retrieval-expanded'
        if not (index / 'manifest.json').exists():
            print('Создание локального индекса…', flush=True)
            subprocess.run([str(python), str(APP / 'scripts/retrieval.py'), 'build', '--chunks',
                            str(APP / 'data/expanded/chunks.current.jsonl'), '--index', str(index)], check=True)
        api = start('api', [str(python), '-m', 'uvicorn', 'app.api:app', '--host', '127.0.0.1',
                            '--port', '8000', '--workers', '1', '--no-access-log'], env)
        wait_ready('http://127.0.0.1:8000/health', api)
        ui_env = {k: v for k, v in os.environ.items() if k not in ('GROQ_API_KEY', 'GROQ_MODEL')}
        ui_env['KSTU_API_URL'] = 'http://127.0.0.1:8000'
        ui = start('ui', [str(python), '-m', 'streamlit', 'run', str(APP / 'app/frontend.py'),
                          '--server.address', '127.0.0.1', '--server.port', '8501', '--server.headless', 'true'], ui_env)
        wait_ready('http://127.0.0.1:8501/_stcore/health', ui)
        print('Готово: http://127.0.0.1:8501\nОставьте терминал открытым. Для остановки нажмите Ctrl+C.', flush=True)
        while all(p.poll() is None for p in processes):
            time.sleep(1)
        raise RuntimeError(f'Один из сервисов остановился. Журналы: {logs}')
    finally:
        for process in reversed(processes):
            if process.poll() is None:
                process.terminate()
        for process in processes:
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        for handle in handles:
            handle.close()


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('\nПриложение остановлено.')
    except (RuntimeError, subprocess.CalledProcessError, OSError) as error:
        raise SystemExit(str(error))
