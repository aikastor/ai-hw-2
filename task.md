# Technical specification

Project: Smart University Knowledge Hub (AI assistant for the Student Office and Admissions Office)

## 1. General information

- Project type: Retrieval-Augmented Generation (RAG) system.
- Goal: Create an interactive AI assistant that automates answers to questions from current and prospective students, using official, publicly available university documents.
- Key focus: Production readiness, including minimizing hallucinations, protecting data, logging, and preserving table structure during retrieval.

## 2. Data sources (knowledge base)

The system must use the following publicly available documents, uploaded as PDFs or parsed from web pages:

- University academic policy: rules for exam retakes, GPA calculation, and academic leave.
- Admissions rules for the current academic year: required documents, admission score thresholds, tuition fees, and grants.
- Academic calendar: examination periods, course registration deadlines, and holidays.

## 3. Architecture and functional requirements

The project must have three main layers (pipelines).

### 3.1. Data ingestion and processing pipeline

#### Text extraction

Write a script to parse PDF files. Correct extraction of tabular data is mandatory. Convert tables to Markdown before embedding so that the LLM retains the structure of rows and columns.

#### Semantic chunking

Split text into meaningful units, such as paragraphs or logical blocks, rather than using a fixed character count. The recommended chunk size is 500–1,000 tokens, with 10–15% overlap.

#### Metadata enrichment

Automatically assign the following tags to each chunk:  

- `source`: document or page title.
- `category`: "prospective student", "current student", or "calendar".
- `page_number`: page number in the PDF.

### 3.2. Storage and retrieval

#### Vector database

Use PGVector (PostgreSQL), Qdrant, or ChromaDB.

#### Hybrid search

Combine the following search methods:

- Semantic search using vector embeddings to understand the meaning of a question.
- Keyword search using BM25 to find exact keywords, abbreviations, and course codes.

#### Metadata filtering

Support excluding irrelevant documents at query time. For example, if the user is identified as a prospective student, search only the admissions rules.

### 3.3. Generation and guardrails

#### Prompt engineering and system prompt

Give the LLM strict instructions in its system prompt:

- Prohibit answers based on information outside the supplied context (strict hallucination prevention).
- If the context does not contain the answer, the model must use this response template:

> Unfortunately, I do not have accurate information on this question. Please contact the Student Office (room 101).

#### User interface

Implement a chat interface using Streamlit or Chainlit. Every bot response must display clickable source citations beneath it, including the document title and page number.

## 4. Recommended technology stack

- Programming language: Python 3.10+.
- Backend and API: FastAPI.
- Vector engine: Qdrant or PGVector (PostgreSQL).
- LLM and embeddings: OpenAI API (GPT-4o-mini) OR local models through Ollama (Llama 3 or Mistral) for full privacy.
- Frontend: Streamlit or Chainlit.

## 5. Development stages and plan

1. Collect publicly available university PDF documents. Write the parsing and chunking script.
2. Set up the vector database, generate embeddings, and check the quality of retrieved context.
3. Integrate the LLM, configure the system prompt, and add hallucination safeguards.
4. Develop the Streamlit UI and add source citations.
5. Test with Ragas, collect metrics, and prepare documentation for the project defense.
