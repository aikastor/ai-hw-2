FROM python:3.13-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app/rag-kstu
WORKDIR /app
COPY rag-kstu/requirements*.txt /app/rag-kstu/
RUN python -m pip install -r rag-kstu/requirements-chat.txt
COPY data/ /app/data/
COPY task.md /app/task.md
COPY rag-kstu/ /app/rag-kstu/
RUN useradd --create-home --uid 10001 kstu \
    && mkdir -p /var/lib/kstu/index \
    && chown -R kstu:kstu /var/lib/kstu
USER kstu
