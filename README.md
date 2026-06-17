# Local RAG Bot

Tiny local-first RAG chatbot for answering questions only from local files.

The first version is intentionally small:

- no cloud API required
- no web search
- no external Python dependencies
- optional Ollama generation if available
- extractive fallback when no local LLM is running

## Quick Start

```bash
python3 -m local_ragbot ingest data --index indexes/default.json
python3 -m local_ragbot ask "What is this bot allowed to answer?" --index indexes/default.json
python3 -m local_ragbot serve --index indexes/default.json --host 127.0.0.1 --port 8088
```

Add Markdown, text, or JSON files to `data/`, then run `ingest` again.

## Ollama

If Ollama is installed and running, the bot can use a tiny local model:

```bash
ollama pull llama3.2:1b
python3 -m local_ragbot ask "..." --model llama3.2:1b
```

Without Ollama, it returns the most relevant local excerpts.

## Guardrail

The assistant is RAG-only. If retrieval finds weak or no context, it refuses instead of guessing.

