# Current State

This file describes what currently exists in the project.

## Implemented

- Local dataset ingestion
- Dataset-separated indexes
- CLI ask/ingest/serve/datasets/agents/runtime commands
- HTTP server
- Browser UI
- Agent config via `config/agents.toml`
- Agent loader
- Deterministic router
- Runtime state
- Runtime job metadata
- Ollama generation
- Extractive fallback
- Final formatter
- Source checker
- Debug JSON output

## Current Pipeline

```text
router
    ↓
runtime
    ↓
selected agent
    ↓
retrieval
    ↓
ollama generation or extractive fallback
    ↓
source_checker
    ↓
final_formatter
Important Response Fields
answer          human-readable Markdown
raw_answer      raw model/extractive answer
display         render metadata
sources         retrieved local sources
source_check    grounding check result
mode            ollama/extractive/refusal/etc.
agent           selected agent id
agent_name      selected agent display name
datasets        datasets checked
pipeline        executed pipeline trace
job             temporary job metadata
runtime         agent runtime state
Not Implemented Yet
Persistent runtime state across process restarts
Job queue
Model pool
Warm/cold model management
Markdown-to-HTML rendering
STT/TTS
Agent proposal system
Dashboard
Persistent conversation memory
Design Rule

Agents are presets, not permanent processes.

Workers are temporary executions.

Models are shared resources.

The orchestrator owns routing and availability decisions.
