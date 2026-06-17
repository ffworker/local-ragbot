## Quick Start

Local RAG Bot is a local-first agentic RAG assistant.

It can:

* ingest local Markdown, text, and JSON files
* keep knowledge separated by dataset
* route questions to configured agents
* answer with Ollama when available
* fall back to extractive local excerpts
* track runtime/job state
* format answers for humans
* run a source-grounding check when configured

```bash
python --version
```

Python **3.11+** is required.

Create or update the default dataset:

```bash
mkdir -p data/default
python -m local_ragbot ingest data --dataset default --index-dir indexes
```

Ask a question:

```bash
python -m local_ragbot ask "What is this bot allowed to answer?" \
  --dataset default \
  --index-dir indexes
```

Debug the full pipeline:

```bash
python -m local_ragbot ask "What is this bot allowed to answer?" \
  --dataset default \
  --index-dir indexes \
  --json
```

Start the local web/API server:

```bash
python -m local_ragbot serve --index-dir indexes --host 127.0.0.1 --port 8088
```

Open:

```text
http://127.0.0.1:8088
```

---

## Agent Runtime

Agents are configured in:

```text
config/agents.toml
```

List configured agents:

```bash
python -m local_ragbot agents
python -m local_ragbot agents --json
```

List runtime state:

```bash
python -m local_ragbot runtime
python -m local_ragbot runtime --json
```

The runtime tracks whether an agent is:

```text
idle
busy
disabled
error
```

It also records job counts, last use, model name, and availability state.

---

## Datasets

Datasets keep domains separated.

Example folders:

```text
data/default
data/coach-potato
data/devops
data/homelab
```

Ingest a dataset:

```bash
python -m local_ragbot ingest data --dataset devops --index-dir indexes
```

Ask a dataset directly:

```bash
python -m local_ragbot ask "How do I use Docker Compose here?" \
  --dataset devops \
  --index-dir indexes
```

Ask with an explicit agent:

```bash
python -m local_ragbot ask "How do I use Docker Compose here?" \
  --agent devops_agent \
  --dataset devops \
  --index-dir indexes \
  --json
```

Ask with auto-routing:

```bash
python -m local_ragbot ask "How do I use Docker Compose here?" \
  --index-dir indexes \
  --json
```

Routing order:

```text
1. Explicit --agent
2. Explicit --dataset
3. route_keywords from config/agents.toml
4. defaults.default_agent
```

---

## Local LLM / Ollama Setup

The bot works without Ollama, but answers are extractive.

With Ollama, the selected agent generates a cleaner answer from retrieved local context.

Install Ollama:

```bash
curl -fsSL https://ollama.com/install.sh | sh
```

Pull a small test model:

```bash
ollama pull llama3.2:1b
```

Verify:

```bash
ollama list
curl http://127.0.0.1:11434/api/tags
```

Use an explicit model override:

```bash
python -m local_ragbot ask "What is this bot allowed to answer?" \
  --dataset default \
  --index-dir indexes \
  --model llama3.2:1b \
  --json
```

Force extractive mode:

```bash
python -m local_ragbot ask "What is this bot allowed to answer?" \
  --dataset default \
  --index-dir indexes \
  --model "" \
  --json
```

---

## HTTP API

Start server:

```bash
python -m local_ragbot serve --index-dir indexes --host 127.0.0.1 --port 8088
```

Endpoints:

```text
GET  /health
GET  /datasets
GET  /agents
GET  /runtime
POST /ask
```

Ask via API:

```bash
curl -s -X POST http://127.0.0.1:8088/ask \
  -H "Content-Type: application/json" \
  -d '{"agent":"local_answerer","dataset":"default","question":"What is this bot allowed to answer?"}' \
  | python -m json.tool
```

---

## Response Shape

A normal `--json` response includes:

```json
{
  "answer": "Markdown-formatted human answer",
  "raw_answer": "Raw model or extractive answer before final formatting",
  "display": {
    "format": "markdown",
    "title": "Answer",
    "kind": "generated"
  },
  "sources": [
    {
      "dataset": "default",
      "source": "notes.md",
      "score": 0.42
    }
  ],
  "source_check": {
    "status": "checked",
    "grounded": true,
    "confidence": "high",
    "issues": [],
    "checked_by": "source_checker"
  },
  "mode": "ollama",
  "agent": "local_answerer",
  "agent_name": "Local Answerer",
  "datasets": ["default"],
  "missing_datasets": [],
  "pipeline": ["router", "runtime", "local_answerer", "source_checker", "final_formatter"],
  "job": {
    "id": "uuid",
    "agent": "local_answerer",
    "started_at": "timestamp"
  },
  "runtime": {
    "agent": "local_answerer",
    "state": "idle",
    "active_jobs": 0,
    "max_concurrent_jobs": 1
  }
}
```

Common `mode` values:

```text
ollama
extractive
refusal
missing_dataset
agent_unavailable
error
```

Common `source_check.status` values:

```text
checked
skipped
not_needed
```

---

## Guardrail

The assistant is RAG-only.

It should answer only from indexed local files. If retrieval finds weak or no context, it should refuse or return local excerpts instead of guessing.

The source checker is a verification pass. It checks whether the answer is grounded in retrieved local context. It does not rewrite answers.
