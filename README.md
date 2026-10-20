# KSTU grounded chat

A Russian/English university assistant that answers from reviewed official KSTU documents and web pages, with source citations.

## Run locally

Follow the [installation and startup guide](rag-kstu/README.md). It includes exact commands for cloning, installing dependencies, configuring your key, downloading the embedding model, building the index and starting the app.

Requirements: Python 3.13, your own Groq API key, and the pinned Ollama runtime/model. macOS is tested; other platforms are not yet verified.

The app uses FastAPI, Streamlit, local Qdrant, BM25 and Ollama bge-m3 embeddings. Groq generates and checks answers from the retrieved evidence. Selected evidence and conversation messages go to Groq.

After setup, open http://127.0.0.1:8501.

## Repository contents

- `rag-kstu/app/`: backend, frontend and prompts.
- `rag-kstu/scripts/`: source validation, index building, tests and packaging.
- `rag-kstu/data/` and `data/`: reviewed chunks and hash-pinned evidence needed to reproduce the index. Keep both directories.
- `rag-kstu/evaluation/`: evaluation records and [Russian validation questions](rag-kstu/evaluation/validation-ru.md).

Credentials, virtual environments, model weights and generated Qdrant indexes are excluded. Each clone builds its own index.

## Coverage and verification

The expanded corpus includes programme tables, applicant checklists and selected academic policies, tuition and calendar evidence. Coverage is incomplete; current bachelor ORT thresholds and grant quotas remain unverified. See [assignment status](rag-kstu/ASSIGNMENT-STATUS.md) and [observed chat results](rag-kstu/data/CHAT-REPORT.md). Historical evaluations may describe earlier corpus or prompt versions.

Reviewed university documents retain their original attribution. See [attribution](rag-kstu/ATTRIBUTION.md).
