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
python3 -m local_ragbot ingest data --dataset default --index-dir indexes
python3 -m local_ragbot ask "What is this bot allowed to answer?" --dataset default --index-dir indexes
python3 -m local_ragbot serve --index-dir indexes --host 127.0.0.1 --port 8088
```

Add Markdown, text, or JSON files to `data/<dataset>/`, then run `ingest` again.

Dataset mode keeps domains separated:

```bash
python3 -m local_ragbot ingest data --dataset coach-potato --index-dir indexes
python3 -m local_ragbot ask "How is my training going?" --dataset coach-potato --index-dir indexes
curl -X POST http://127.0.0.1:8088/ask \
  -H 'Content-Type: application/json' \
  -d '{"dataset":"coach-potato","question":"How is my training going?"}'
```

## Ollama

If Ollama is installed and running, the bot can use a tiny local model:

```bash
ollama pull llama3.2:1b
python3 -m local_ragbot ask "..." --model llama3.2:1b
```

Without Ollama, it returns the most relevant local excerpts.

## Guardrail

The assistant is RAG-only. If retrieval finds weak or no context, it refuses instead of guessing.
