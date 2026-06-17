# Local RAG Bot Roadmap

This roadmap is written for humans and LLM contributors. Use the checkboxes to track progress before making larger architectural changes.

## Current North Star

Build a local-first agent orchestration runtime:

```text
User / API / Voice
    ↓
Router / Orchestrator
    ↓
Agent Preset
    ↓
Local RAG Retrieval
    ↓
Ollama or Extractive Fallback
    ↓
Grounded Answer
```

The project should stay small, inspectable, and resource-aware.

---

## Phase 0 — Baseline Local RAG

Goal: basic local document question answering.

### Checklist

- [ ] `python -m local_ragbot ingest ...` works
- [ ] `python -m local_ragbot ask ...` works
- [ ] `python -m local_ragbot serve ...` works
- [ ] Local files are read from `data/<dataset>/`
- [ ] Index files are written to `indexes/<dataset>.json`
- [ ] Missing context returns refusal instead of hallucination
- [ ] Without Ollama, answer mode is `extractive`
- [ ] With Ollama, answer mode is `ollama`

### Done When

A user can add `.md`, `.txt`, or `.json` files, ingest them, and ask questions from the CLI or HTTP server.

---

## Phase 1 — Agent Presets

Goal: define agents as static config.

### Files

```text
config/agents.toml
local_ragbot/agents.py
```

### Checklist

- [ ] `config/agents.toml` exists
- [ ] Each agent has a stable `id`
- [ ] Each agent has `display_name`
- [ ] Each agent has `description`
- [ ] Each agent has `task`
- [ ] Each agent has `model`
- [ ] Each agent has `datasets`
- [ ] Each agent has `allowed_tools`
- [ ] Each agent has `can_call`
- [ ] Each agent has `fallback_agent`
- [ ] Each agent has `max_chunks`
- [ ] Each agent has `min_score`
- [ ] Each agent has `temperature`
- [ ] Each agent has `output_style`
- [ ] Each agent has `system_prompt`
- [ ] Each agent has `route_keywords`
- [ ] `python -m local_ragbot agents` lists all configured agents

### Done When

Agents can be listed and loaded without breaking existing `ingest` and `ask` commands.

---

## Phase 2 — Deterministic Router

Goal: select the right agent without using an LLM.

### Files

```text
local_ragbot/router.py
```

### Routing Order

```text
1. Explicit --agent
2. Explicit --dataset
3. route_keywords match
4. defaults.default_agent
```

### Checklist

- [ ] Explicit `--agent devops_agent` selects `devops_agent`
- [ ] Explicit `--dataset coach-potato` selects an agent that owns `coach-potato`
- [ ] Docker/Kubernetes questions route to `devops_agent`
- [ ] Training/handstand questions route to `coach_agent`
- [ ] Unknown questions route to `local_answerer`
- [ ] Router does not call an LLM
- [ ] Router behavior is visible in JSON output

### Done When

The selected agent is predictable and visible in every JSON answer.

---

## Phase 3 — Agent Pipeline

Goal: one request runs through a clear, inspectable pipeline.

### Files

```text
local_ragbot/pipeline.py
local_ragbot/llm.py
local_ragbot/cli.py
local_ragbot/server.py
```

### Pipeline

```text
router
    ↓
selected agent
    ↓
retrieve from allowed datasets
    ↓
generate with model if available
    ↓
extractive fallback if needed
    ↓
source checker placeholder
    ↓
final formatter placeholder
```

### Checklist

- [ ] `ask --agent ... --json` works
- [ ] `/ask` accepts `agent`
- [ ] `/ask` accepts `dataset`
- [ ] `/agents` endpoint exists
- [ ] JSON includes `answer`
- [ ] JSON includes `sources`
- [ ] JSON includes `mode`
- [ ] JSON includes `agent`
- [ ] JSON includes `agent_name`
- [ ] JSON includes `datasets`
- [ ] JSON includes `missing_datasets`
- [ ] JSON includes `pipeline`
- [ ] Ollama fallback remains safe
- [ ] Existing CLI behavior does not break

### Done When

A user can see exactly which agent answered, which datasets were used, and whether Ollama or extractive fallback was used.

---

## Phase 4 — Runtime State

Goal: make the project feel more like a tiny "LLM cluster" control plane.

### New File

```text
local_ragbot/runtime.py
```

### Concepts

```text
idle
busy
cooling_down
disabled
error
```

### Suggested Runtime Fields

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

### Checklist

- [ ] Runtime can list agent states
- [ ] Agent can be `idle`
- [ ] Agent can be `busy`
- [ ] Agent can be `disabled`
- [ ] Agent can be `error`
- [ ] Runtime blocks disabled agents
- [ ] Runtime enforces `max_concurrent_jobs`
- [ ] Runtime records `last_used`
- [ ] Runtime records last error
- [ ] Runtime state is visible via CLI
- [ ] Runtime state is visible via HTTP endpoint

### CLI Ideas

```bash
python -m local_ragbot runtime
python -m local_ragbot runtime --json
```

### API Ideas

```text
GET /runtime
GET /runtime/agents
```

### Done When

The orchestrator can say whether an agent is available before trying to run it.

---

## Phase 5 — Job Queue and Resource Limits

Goal: avoid resource crashes when multiple requests arrive.

### Concepts

```text
job
queue
active_jobs
max_concurrent_jobs
timeout
cooldown
priority
```

### Checklist

- [ ] Each request gets a job ID
- [ ] Jobs have state: `queued`, `running`, `done`, `failed`
- [ ] Agents respect `max_concurrent_jobs`
- [ ] Requests can be rejected or queued when busy
- [ ] Timeouts are enforced
- [ ] Failed jobs capture an error
- [ ] JSON output includes job state when relevant
- [ ] HTTP server does not crash on parallel requests

### Done When

The app can handle multiple requests without accidentally loading too many models or running too many agent calls.

---

## Phase 6 — Model Pool / Warm-Cold Behavior

Goal: manage Ollama models as shared resources.

### Concepts

```text
cold  = model not loaded, lowest RAM, slower first answer
warm  = model kept available, faster answer, uses RAM
hot   = active session/worker, fastest, highest resource cost
```

### Checklist

- [ ] Agent config supports `keep_warm`
- [ ] Agent config supports `cooldown_seconds`
- [ ] Main/default agent can stay warm
- [ ] Heavy agents default to cold
- [ ] Runtime exposes model status if possible
- [ ] Model choice is per-agent
- [ ] Model override still works for testing

### Done When

The project can explain and control why a model is warm, cold, or in use.

---

## Phase 7 — Voice Adapters

Goal: add speech input/output without mixing voice into every agent.

### New File

```text
local_ragbot/voice.py
```

### Correct Flow

```text
audio input
    ↓
STT adapter
    ↓
text question
    ↓
normal orchestrator
    ↓
text answer
    ↓
TTS adapter
    ↓
audio output
```

### Checklist

- [ ] Voice layer is optional
- [ ] Normal text pipeline still works
- [ ] STT converts audio to text
- [ ] TTS converts answer text to audio
- [ ] Agents remain text-first
- [ ] `/voice/ask` or CLI voice command is added only after text routing is stable
- [ ] Voice session can keep a model warm temporarily

### Done When

A voice question uses the same router, agents, datasets, and pipeline as a typed question.

---

## Phase 8 — Source Checker as Real Agent

Goal: add a second controlled pass that checks grounding.

### Checklist

- [ ] `source_checker` can inspect answer + context
- [ ] It flags unsupported claims
- [ ] It can force fallback/refusal
- [ ] It cannot rewrite arbitrary facts
- [ ] It has strict temperature
- [ ] It is optional/configurable
- [ ] It appears in the pipeline trace

### Done When

The system can detect answers that drift away from retrieved local context.

---

## Phase 9 — Agent Improvement Proposals

Goal: allow agents to suggest improvements without self-modifying.

### Concepts

```text
proposal
approval
config change
memory change
dataset suggestion
routing improvement
```

### Checklist

- [ ] Agents can write proposals to `proposals/`
- [ ] Proposals are Markdown or JSON
- [ ] Proposals never auto-apply
- [ ] User must approve changes
- [ ] Proposals can suggest dataset additions
- [ ] Proposals can suggest route keyword additions
- [ ] Proposals can suggest model changes
- [ ] Proposals can suggest prompt changes

### Done When

Agents can "evolve" by making reviewable suggestions, not by silently changing themselves.

---

## Phase 10 — Dashboard

Goal: make the local agent cluster visible.

### Possible Views

```text
Agents
Datasets
Runtime state
Models
Jobs
Recent questions
Failures
Proposals
```

### Checklist

- [ ] `/` browser UI shows agents
- [ ] UI can select dataset
- [ ] UI can select agent
- [ ] UI displays mode
- [ ] UI displays sources
- [ ] UI displays pipeline trace
- [ ] UI displays runtime state
- [ ] UI displays errors clearly

### Done When

A human can understand what happened without reading logs.

---

## Definition of "Good"

Before adding big new features, verify:

- [ ] Can I explain which agent answered?
- [ ] Can I explain why that agent was selected?
- [ ] Can I see which model was used?
- [ ] Can I see which dataset was used?
- [ ] Can I see which sources were used?
- [ ] Can I see whether Ollama or fallback answered?
- [ ] Can I see whether the answer refused correctly?
- [ ] Can I test it from CLI?
- [ ] Can I test it from HTTP?
- [ ] Did we avoid unnecessary dependencies?
