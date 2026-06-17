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

## Local LLM / Ollama Setup

Local RAG Bot can run in two modes:

1. **Extractive fallback mode**
   No LLM required. The bot searches your local indexed files and returns the most relevant excerpts.

2. **Ollama mode**
   Uses a local Ollama model to generate a cleaner answer from the retrieved local context.

Without Ollama, the bot is not a full “smart” chatbot. It is a local retrieval tool that finds matching snippets. With Ollama, it becomes a small local RAG assistant.

### Requirements

```bash
python --version
```

Python **3.11+** is required.

### Install Ollama

Official Ollama documentation:

* https://ollama.com/download
* https://github.com/ollama/ollama

Linux/macOS:

```bash
curl -fsSL https://ollama.com/install.sh | sh
```

Windows PowerShell:

```powershell
irm https://ollama.com/install.ps1 | iex
```

After installation, verify that Ollama works:

```bash
ollama --version
ollama list
```

### Pull a small local model

For a lightweight first test:

```bash
ollama pull llama3.2:1b
```

You can also test the model directly:

```bash
ollama run llama3.2:1b
```

### Use Local RAG Bot without Ollama

This returns local excerpts only:

```bash
python -m local_ragbot ingest data --dataset default --index-dir indexes
python -m local_ragbot ask "What is this bot allowed to answer?" --dataset default --index-dir indexes
```

### Use Local RAG Bot with Ollama

This retrieves local context first, then asks Ollama to generate the final answer:

```bash
python -m local_ragbot ask "What is this bot allowed to answer?" \
  --dataset default \
  --index-dir indexes \
  --model llama3.2:1b
```

To see which mode was used:

```bash
python -m local_ragbot ask "What is this bot allowed to answer?" \
  --dataset default \
  --index-dir indexes \
  --model llama3.2:1b \
  --json
```

Look for:

```json
"mode": "ollama"
```

If you see:

```json
"mode": "extractive"
```

then Ollama was not used and the bot returned local excerpts instead.

### Serve with Ollama enabled

Start the web/API server with a model:

```bash
python -m local_ragbot serve --index-dir indexes --host 127.0.0.1 --port 8088 --model llama3.2:1b
```

Then open:

```text
http://127.0.0.1:8088
```

Or ask via API:

```bash
curl -X POST http://127.0.0.1:8088/ask \
  -H "Content-Type: application/json" \
  -d '{"dataset":"default","question":"What is this bot allowed to answer?"}'
```

### Important

The bot is designed to answer only from indexed local files. If the local documents do not contain enough matching context, it should refuse or return only the closest local excerpts instead of guessing.

Without Ollama, it returns the most relevant local excerpts.

## Guardrail

The assistant is RAG-only. If retrieval finds weak or no context, it refuses instead of guessing.
