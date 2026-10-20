#!/usr/bin/env python3
"""Необязательная обёртка запуска Docker Compose; Python на хосте не обязателен."""
from pathlib import Path
import shutil
import subprocess
import sys


def main():
    root = Path(__file__).resolve().parents[2]
    if '--help' in sys.argv:
        print('Основная команда из корня репозитория: docker compose up --build')
        return
    if not shutil.which('docker'):
        raise SystemExit('Установите и запустите Docker Desktop (или Docker Engine с Compose).')
    config = root / 'rag-kstu/.env'
    if not config.exists():
        shutil.copyfile(root / 'rag-kstu/.env.example', config)
        raise SystemExit('Создан rag-kstu/.env. Укажите в нём свой GROQ_API_KEY и повторите запуск.')
    subprocess.run(['docker', 'compose', 'up', '--build'], cwd=root, check=True)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        pass
    except subprocess.CalledProcessError as error:
        raise SystemExit(error.returncode)
