## Core Goal

Build a local agent control plane:

```text
User / API / Voice
    ↓
Router
    ↓
Runtime availability check
    ↓
Selected Agent Preset
    ↓
Local Retrieval
    ↓
Ollama generation or extractive fallback
    ↓
Source checker
    ↓
Final formatter
    ↓
Grounded, readable answer
```

Do not turn the project into a large framework too early. Prefer small files, plain Python, no unnecessary dependencies, and clear JSON output.

---

## Important Files and Responsibilities

```text
config/agents.toml
    Static agent definitions:
    - agent id
    - display name
    - task
    - model
    - datasets
    - system prompt
    - route keywords
    - allowed tools
    - allowed handoff targets
    - runtime limits

local_ragbot/agents.py
    Loads and validates config/agents.toml.

local_ragbot/router.py
    Deterministically chooses the answering agent for a question.

local_ragbot/runtime.py
    Tracks runtime state:
    - idle
    - busy
    - disabled
    - error

    Also tracks:
    - active jobs
    - max concurrent jobs
    - total jobs
    - failed jobs
    - last used
    - last error
    - current job id

local_ragbot/pipeline.py
    Executes one request:
    - load config
    - route to an agent
    - check runtime availability
    - retrieve local chunks
    - call Ollama if configured
    - fall back to extractive snippets
    - call source checker if allowed
    - call final formatter
    - return answer, raw_answer, display, source_check, runtime, job, mode, sources, agent, datasets, and pipeline trace

local_ragbot/source_checker.py
    Verifies whether an answer is grounded in retrieved local context.
    It returns a verdict object.
    It must not rewrite the answer.

local_ragbot/formatter.py
    Formats raw answers into readable Markdown.
    It returns:
    - answer
    - raw_answer
    - display

local_ragbot/retrieval.py
    Reads local files, chunks text, creates simple hashed vectors, retrieves matching chunks.

local_ragbot/llm.py
    Talks to Ollama.
    Keep this small and isolated.

local_ragbot/server.py
    HTTP API and simple browser UI.
    Current important endpoints:
    - GET /health
    - GET /datasets
    - GET /agents
    - GET /runtime
    - POST /ask

local_ragbot/cli.py
    CLI entrypoint.
    Current important commands:
    - ingest
    - ask
    - serve
    - datasets
    - agents
    - runtime
```

---

## Preferred JSON Response Shape

Every `ask --json` or `POST /ask` response should aim to include:

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
      "dataset": "devops",
      "source": "docker.md",
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
  "agent": "devops_agent",
  "agent_name": "DevOps Agent",
  "datasets": ["devops", "homelab"],
  "missing_datasets": [],
  "pipeline": ["router", "runtime", "devops_agent", "source_checker", "final_formatter"],
  "job": {
    "id": "uuid",
    "agent": "devops_agent",
    "started_at": "timestamp"
  },
  "runtime": {
    "agent": "devops_agent",
    "state": "idle",
    "enabled": true,
    "model": "llama3.2:1b",
    "active_jobs": 0,
    "max_concurrent_jobs": 1,
    "total_jobs": 1,
    "failed_jobs": 0,
    "last_used": "timestamp",
    "last_error": null,
    "current_job_id": null,
    "keep_warm": false,
    "cooldown_seconds": 0,
    "priority": 50
  }
}
```

Valid `mode` values should stay simple:

```text
ollama
extractive
refusal
missing_dataset
agent_unavailable
error
```

Valid `source_check.status` values should stay simple:

```text
checked
skipped
not_needed
```

Important rules:

* `answer` is for humans.
* `raw_answer` is for debugging.
* `display.format` should currently be `markdown`.
* `source_check` reports grounding; it does not rewrite answers.
* `pipeline` must reflect the actual executed stages.
* `runtime` must describe agent availability after the request.
* `job` must describe the temporary request execution.

---

## Testing Expectations

When changing routing, agents, runtime, formatting, source checking, or pipeline behavior, verify:

```bash
python -m local_ragbot agents
python -m local_ragbot agents --json

python -m local_ragbot runtime
python -m local_ragbot runtime --json

python -m local_ragbot datasets --index-dir indexes

python -m local_ragbot ask "What is this bot allowed to answer?" \
  --agent local_answerer \
  --dataset default \
  --index-dir indexes \
  --json

python -m local_ragbot ask "How do I use Docker Compose here?" \
  --index-dir indexes \
  --json

python -m local_ragbot ask "What is this bot allowed to answer?" \
  --agent local_answerer \
  --dataset default \
  --index-dir indexes \
  --model "" \
  --json

python -m local_ragbot serve --index-dir indexes --host 127.0.0.1 --port 8088
```

HTTP smoke tests:

```bash
curl -s http://127.0.0.1:8088/health | python -m json.tool
curl -s http://127.0.0.1:8088/datasets | python -m json.tool
curl -s http://127.0.0.1:8088/agents | python -m json.tool
curl -s http://127.0.0.1:8088/runtime | python -m json.tool

curl -s -X POST http://127.0.0.1:8088/ask \
  -H "Content-Type: application/json" \
  -d '{"agent":"local_answerer","dataset":"default","question":"What is this bot allowed to answer?"}' \
  | python -m json.tool
```

Expected behavior:

* `agents` lists configured agents.
* `runtime` lists runtime state.
* `ask --json` shows `answer`, `raw_answer`, `display`, `agent`, `mode`, `sources`, `source_check`, `job`, `runtime`, and `pipeline`.
* If Ollama is unavailable, mode falls back to `extractive`.
* If context is missing, mode is `refusal` or `missing_dataset`.
* If the agent is unavailable, mode is `agent_unavailable`.
* The pipeline trace should include real stages only.
* `source_checker` should appear only when configured and allowed by `can_call`.
* `final_formatter` should appear when formatting actually ran.
