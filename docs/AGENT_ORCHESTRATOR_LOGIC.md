# Agent Orchestrator Logic

This document explains the design language behind the project.

The project is moving toward a small local "LLM cluster" or "agent control plane", but agents should not be treated as always-running digital people. They should be controlled presets that the runtime wakes only when needed.

## Simple Mental Model

```text
Agent = preset + permissions + memory scope
Worker = temporary job execution
Model = shared local inference resource
Runtime = state, queue, limits, cooldown, warm/cold behavior
Orchestrator = router + scheduler + policy enforcer
```

## Why This Matters

A naive design would run every agent as a permanent process. That sounds cool, but wastes RAM and becomes hard to debug.

The better design:

```text
Agents sleep as configuration.
The orchestrator wakes an agent by creating a temporary worker.
The worker uses retrieval and possibly a model.
The worker returns an answer.
The worker dies.
The agent state is updated.
```

This gives the feeling of living agents without the cost of always-running LLMs.

---

## Core Terms

## Agent

An agent is not a process.

An agent is a configured role:

```text
id
display_name
description
task
model
datasets
allowed_tools
can_call
fallback_agent
max_chunks
min_score
temperature
output_style
system_prompt
route_keywords
```

Example:

```text
devops_agent
    Task: answer Docker/Kubernetes/Ansible/homelab questions
    Datasets: devops, homelab
    Model: llama3.2:1b
    Tools: retrieve, generate
```

The agent says:

```text
Who am I?
What am I allowed to know?
What am I allowed to do?
Which model do I use?
Who may I call?
```

## Worker

A worker is the temporary execution of an agent.

Example:

```text
User asks Docker question
    ↓
Router selects devops_agent
    ↓
Runtime starts one devops_agent worker
    ↓
Worker retrieves devops context
    ↓
Worker calls Ollama
    ↓
Worker returns answer
    ↓
Worker ends
```

The worker lives only for the request.

## Model

A model is the local LLM served by Ollama.

Examples:

```text
llama3.2:1b
qwen2.5-coder
mistral
phi
```

The model is expensive because it uses RAM and CPU/GPU.

Important:

```text
Many agents can share one model.
One agent can be configured to use a different model.
The model is not the agent.
```

## Dataset

A dataset is the local knowledge scope an agent may retrieve from.

Example:

```text
data/default
data/coach-potato
data/devops
data/homelab
```

After ingesting:

```text
indexes/default.json
indexes/coach-potato.json
indexes/devops.json
indexes/homelab.json
```

An agent should only retrieve from datasets assigned to it.

## Router

The router decides which agent should handle a question.

V1 routing should be deterministic:

```text
1. Explicit agent
2. Explicit dataset
3. Keyword rules
4. Default agent
```

Example:

```text
"How do I use Docker Compose?"
    ↓
contains "docker" and "compose"
    ↓
devops_agent
```

## Pipeline

The pipeline is the fixed execution path.

Recommended v1:

```text
router
    ↓
selected agent
    ↓
retrieval
    ↓
generation or extractive fallback
    ↓
source checker placeholder
    ↓
final formatter placeholder
```

The pipeline should appear in JSON output:

```json
{
  "pipeline": ["router", "devops_agent", "source_checker", "final_formatter"]
}
```

## Runtime

The runtime tracks whether agents are available and whether running them would exceed resource limits.

Suggested states:

```text
idle
busy
cooling_down
disabled
error
```

Suggested state object:

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

The runtime answers:

```text
Is this agent enabled?
Is it already busy?
Can this machine afford another job?
Should this request run, queue, fallback, or fail?
```

## Orchestrator

The orchestrator is the combination of:

```text
router
runtime
pipeline
model control
policy enforcement
```

It is the traffic cop.

It should make these decisions:

```text
Which agent should handle this?
Is that agent available?
Which datasets may it use?
Which model should it use?
Is the model available?
Should the job run now or queue?
What should happen if it fails?
```

---

## "Live, Die, Sleep, Evolve"

The desired feeling:

```text
Agents live, die, evolve, and sleep.
```

The realistic implementation:

| Desired Concept | Implementation |
|---|---|
| Agent lives | Agent exists in config |
| Agent sleeps | No worker is running |
| Agent wakes | Router selects it |
| Agent works | Runtime starts temporary worker |
| Agent dies | Worker finishes |
| Agent remembers | Runtime/history/proposals are saved |
| Agent evolves | It writes a proposal; human approves |
| Agent cluster | Many agent configs share one local runtime |
| Instant ready | Some models stay warm, not every agent |

## Cold, Warm, and Hot

Model readiness is separate from agent existence.

```text
Cold:
    model not loaded
    slow first answer
    lowest RAM usage

Warm:
    model kept available
    faster answer
    uses RAM while idle

Hot:
    active request/session
    fastest response
    highest resource usage
```

Recommended defaults:

```text
default assistant: warm if machine can afford it
specialized agents: cold
voice session: warm while active
heavy/coder agents: cold unless explicitly needed
```

## Why Not Keep Every Agent Running?

Because agents are mostly prompts and config. Keeping all of them alive would waste resources.

Better:

```text
Keep config always available.
Keep only selected model(s) warm.
Start workers only when needed.
```

---

## Handoff Logic

Agents should not freely talk to every other agent.

Use explicit `can_call` rules.

Good:

```text
devops_agent -> source_checker -> final_formatter
coach_agent  -> source_checker -> final_formatter
```

Bad:

```text
devops_agent -> coach_agent -> notes_agent -> devops_agent
```

If loops are ever allowed, enforce a hard max step count.

Recommended v1:

```text
No agent-to-agent conversations.
Only fixed pipeline stages.
```

## Tools

Tools are abilities.

Examples:

```text
retrieve
generate
verify
format
stt
tts
```

An agent may only use tools in `allowed_tools`.

Example:

```toml
allowed_tools = ["retrieve", "generate"]
```

This means the agent can retrieve context and generate an answer, but cannot modify files or update its own config.

---

## STT/TTS Logic

Speech-to-text and text-to-speech should not be part of every agent.

Correct architecture:

```text
audio input
    ↓
STT adapter
    ↓
text question
    ↓
orchestrator
    ↓
normal selected agent
    ↓
text answer
    ↓
TTS adapter
    ↓
audio output
```

This keeps the whole system text-first and easier to debug.

Future voice components:

```text
voice.py
/voice/ask
voice session state
temporary warm model behavior
```

Agents can later have voice preferences:

```toml
voice_enabled = true
voice_name = "default"
speak_responses = true
```

But the core agent should still answer text.

---

## Evolution Logic

Agents should not edit themselves automatically.

Safe evolution flow:

```text
Agent notices weakness
    ↓
Agent writes proposal
    ↓
Proposal is saved to proposals/
    ↓
Human reviews
    ↓
Human approves
    ↓
Config/data changes are applied
```

Examples:

```text
"Add keyword 'workflow' to devops_agent because GitHub Actions questions were routed poorly."

"Add docker-compose examples to data/devops because answers lack enough local context."

"Use a coder model for devops_agent because shell/script answers are weak."
```

Unsafe:

```text
Agent silently edits agents.toml.
Agent silently changes its own prompt.
Agent silently expands its own permissions.
Agent silently reads unrelated datasets.
```

## Source Grounding Logic

The project should remain local-grounded.

If retrieved context is weak:

```text
refuse
```

or:

```text
return closest excerpts
```

Do not guess.

The answer should always expose:

```text
mode
agent
sources
pipeline
datasets
missing_datasets
```

This makes debugging possible.

---

## Final Target Shape

The long-term target is:

```text
Local Agent Control Plane
├── Agent registry
├── Router
├── Runtime state
├── Job queue
├── Model pool
├── Dataset registry
├── RAG pipeline
├── Source checker
├── Voice adapters
├── Proposal system
└── Dashboard
```

The project should get there gradually without losing the current simplicity.
