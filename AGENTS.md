# Instructions for LLMs Working on This Repository

This repository is a small local-first RAG bot that is intentionally evolving into an agent orchestration runtime. Keep it simple, deterministic, and debuggable.

## Core Goal

Build a local agent control plane:

```text
User / API / Voice
    ↓
Orchestrator / Router
    ↓
Selected Agent Preset
    ↓
Local Retrieval
    ↓
Ollama / Extractive Fallback
    ↓
Grounded Answer
```

Do not turn the project into a large framework too early. Prefer small files, plain Python, no unnecessary dependencies, and clear JSON output.

## Current Design Principles

1. **Agents are presets, not permanent personalities.**  
   An agent is config: name, task, model, datasets, prompts, permissions, and route rules.

2. **Workers are temporary.**  
   A worker exists only while handling a request. Do not keep one Python process per agent.

3. **Models are shared expensive resources.**  
   Agents may use different models, but Ollama/model loading is the resource bottleneck.

4. **The orchestrator owns control.**  
   Agents do not freely call each other. Routing and handoff must be explicit.

5. **RAG-only by default.**  
   The bot must answer from indexed local files. If local context is missing or weak, it should refuse or return excerpts instead of guessing.

6. **No hidden autonomy.**  
   Agents may later propose changes, but they must not silently edit their own config, memory, or prompts.

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

local_ragbot/agents.py
    Loads and validates config/agents.toml.

local_ragbot/router.py
    Deterministically chooses the agent for a question.

local_ragbot/pipeline.py
    Executes one request:
    - choose/load agent
    - retrieve local chunks
    - call Ollama if configured
    - fall back to extractive snippets
    - return answer, mode, sources, agent, pipeline trace

local_ragbot/retrieval.py
    Reads local files, chunks text, creates simple hashed vectors, retrieves matching chunks.

local_ragbot/llm.py
    Talks to Ollama. Keep this small and isolated.

local_ragbot/server.py
    HTTP API and simple browser UI.

local_ragbot/cli.py
    CLI entrypoint.
```

## Architectural Boundaries

### Allowed

- Add small Python modules with focused responsibility.
- Add tests or simple smoke commands.
- Add CLI flags only when they are useful and clear.
- Add JSON output for debugging.
- Add runtime state, job limits, queues, and model warm/cold behavior gradually.

### Avoid

- Do not add LangChain, CrewAI, Celery, Redis, FastAPI, or databases unless explicitly requested.
- Do not make agents autonomous by default.
- Do not add background task loops before runtime state and resource limits exist.
- Do not allow every agent to call every other agent.
- Do not hide fallback behavior. Always expose `mode`, `agent`, `sources`, and `pipeline`.

## Preferred JSON Response Shape

Every request should aim to return:

```json
{
  "answer": "...",
  "sources": [
    {
      "dataset": "devops",
      "source": "docker.md",
      "score": 0.42
    }
  ],
  "mode": "ollama",
  "agent": "devops_agent",
  "agent_name": "DevOps Agent",
  "datasets": ["devops", "homelab"],
  "missing_datasets": [],
  "pipeline": ["router", "devops_agent", "source_checker", "final_formatter"]
}
```

Valid `mode` values should stay simple:

```text
ollama
extractive
refusal
missing_dataset
error
```

## Agent Routing Rules

Prefer deterministic routing first:

```text
1. If explicit --agent is provided, use that agent.
2. Else if explicit dataset is provided, pick an agent that owns that dataset.
3. Else match question text against route_keywords.
4. Else use defaults.default_agent.
```

Do not add an LLM-router until deterministic routing is reliable and easy to debug.

## Agent Handoff Rules

Agents may only call or hand off to IDs listed in `can_call`.

Good:

```text
devops_agent -> source_checker -> final_formatter
coach_agent  -> source_checker -> final_formatter
```

Bad:

```text
devops_agent <-> coach_agent <-> notes_agent <-> random loop
```

No loops unless there is a hard maximum step limit.

## Future Runtime Direction

The project should move toward:

```text
Agent = preset + permissions + memory scope
Worker = temporary job execution
Model = shared local inference resource
Runtime = state, queue, limits, cooldown, warm/cold behavior
Orchestrator = router + scheduler + policy enforcer
```

Future runtime states:

```text
idle
busy
cooling_down
disabled
error
```

Future runtime fields:

```json
{
  "agent": "devops_agent",
  "state": "idle",
  "active_jobs": 0,
  "max_concurrent_jobs": 1,
  "last_used": "2026-06-17T12:30:00Z",
  "model": "llama3.2:1b"
}
```

## Voice / STT / TTS Guidance

Do not put STT/TTS inside every agent.

Voice should be an outer adapter:

```text
audio input
    ↓
STT adapter
    ↓
text question
    ↓
normal orchestrator / agent pipeline
    ↓
text answer
    ↓
TTS adapter
    ↓
audio output
```

Agents should remain text-first.

## Implementation Style

Use plain Python standard library where possible. The project currently aims to stay dependency-light.

Prefer:

```text
dataclasses
pathlib
json
tomllib
http.server
urllib
```

Avoid adding dependencies unless the user explicitly approves them.

## Testing Expectations

When changing routing, agents, or pipeline behavior, verify:

```bash
python -m local_ragbot agents
python -m local_ragbot datasets --index-dir indexes
python -m local_ragbot ask "What is this bot allowed to answer?" --agent local_answerer --dataset default --index-dir indexes --json
python -m local_ragbot ask "How do I use Docker Compose here?" --index-dir indexes --json
python -m local_ragbot serve --index-dir indexes --host 127.0.0.1 --port 8088
```

Expected behavior:

- `agents` lists configured agents.
- `ask --json` shows `agent`, `mode`, `sources`, and `pipeline`.
- If Ollama is unavailable, mode falls back to `extractive`.
- If context is missing, mode is `refusal` or `missing_dataset`.

## North Star

This project is not trying to become a cloud SaaS product. It is a local-first personal agent runtime.

Build toward a tiny, understandable "LLM cluster" where agents can be configured, routed, limited, inspected, and eventually voice-enabled without losing control.
