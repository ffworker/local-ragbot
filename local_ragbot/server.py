# changed: run the HTTP API on FastAPI, add SSE streaming, and keep session-scoped memory.
from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

import uvicorn
from fastapi import Body, FastAPI, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse

from .agents import DEFAULT_AGENTS_CONFIG, Agent, load_agent_config
from .datasets import index_path_for_dataset, list_indexed_datasets, validate_dataset
from .formatter import format_extractive_answer, format_refusal_answer, format_unavailable_answer
from .llm import ollama_generate_stream, reset_prompt_history, set_prompt_history
from .pipeline import _build_prompt, answer_with_agent
from .retrieval import IndexedChunk, retrieve
from .router import route_agent
from .runtime import AgentUnavailable, get_runtime
from .source_checker import check_answer_grounding


MAX_HISTORY_MESSAGES = 6
MAX_STORED_MESSAGES = 24

app = FastAPI(title="Local RAG Bot")


@dataclass
class ServerState:
    index_dir: Path = Path("indexes")
    model: str | None = None
    agents_config: Path = DEFAULT_AGENTS_CONFIG


STATE = ServerState()
SESSION_MEMORY: dict[str, list[dict[str, str]]] = {}
SESSION_LOCK = threading.Lock()


@app.get("/health")
def health() -> dict[str, bool]:
    return {"ok": True}


@app.get("/datasets")
def datasets() -> dict[str, list[str]]:
    return {"datasets": list_indexed_datasets(STATE.index_dir)}


@app.get("/agents")
def agents() -> dict[str, Any]:
    config = load_agent_config(STATE.agents_config)
    return {
        "defaults": config.defaults,
        "agents": [
            {
                "id": agent.id,
                "display_name": agent.display_name,
                "description": agent.description,
                "datasets": agent.datasets,
                "model": agent.model,
                "allowed_tools": agent.allowed_tools,
                "can_call": agent.can_call,
            }
            for agent in config.agents.values()
        ],
    }


@app.get("/runtime")
def runtime() -> dict[str, Any]:
    config = load_agent_config(STATE.agents_config)
    return get_runtime(config).snapshot()


@app.get("/", response_class=HTMLResponse)
def home() -> str:
    return _html()


@app.post("/ask")
def ask(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    question, dataset, agent, session_id = _parse_payload(payload)
    missing = _missing_dataset_result(dataset)
    if missing:
        return missing

    history = _history_for(session_id)
    token = set_prompt_history(history)
    try:
        result = answer_with_agent(
            question=question,
            index_dir=STATE.index_dir,
            config_path=STATE.agents_config,
            explicit_agent=agent,
            explicit_dataset=dataset,
            model_override=STATE.model,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    finally:
        reset_prompt_history(token)

    _remember(session_id, question, str(result.get("answer", "")))
    return result


@app.post("/stream")
def stream(payload: dict[str, Any] = Body(...)) -> StreamingResponse:
    question, dataset, agent, session_id = _parse_payload(payload)
    missing = _missing_dataset_result(dataset)
    if missing:
        return StreamingResponse(
            _stream_static_result(missing, session_id, question),
            media_type="text/event-stream",
        )

    history = _history_for(session_id)
    return StreamingResponse(
        _stream_agent_answer(question, dataset, agent, session_id, history),
        media_type="text/event-stream",
    )


def _parse_payload(payload: dict[str, Any]) -> tuple[str, str | None, str | None, str | None]:
    question = str(payload.get("question", "")).strip()
    if not question:
        raise HTTPException(status_code=400, detail="Missing question")

    raw_dataset = payload.get("dataset")
    dataset = None
    if raw_dataset:
        try:
            dataset = validate_dataset(str(raw_dataset).strip())
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    raw_agent = payload.get("agent")
    agent = str(raw_agent).strip() if raw_agent else None

    raw_session_id = payload.get("session_id")
    session_id = str(raw_session_id).strip() if raw_session_id else None

    return question, dataset, agent, session_id


def _missing_dataset_result(dataset: str | None) -> dict[str, Any] | None:
    if not dataset:
        return None

    index_path = index_path_for_dataset(STATE.index_dir, dataset)
    if index_path.exists():
        return None

    return {
        "answer": f"Dataset '{dataset}' ist nicht indexiert.",
        "sources": [],
        "mode": "missing_dataset",
        "dataset": dataset,
    }


def _history_for(session_id: str | None) -> list[dict[str, str]]:
    if not session_id:
        return []

    with SESSION_LOCK:
        return list(SESSION_MEMORY.get(session_id, [])[-MAX_HISTORY_MESSAGES:])


def _remember(session_id: str | None, question: str, answer: str) -> None:
    if not session_id:
        return

    with SESSION_LOCK:
        messages = SESSION_MEMORY.setdefault(session_id, [])
        messages.extend(
            [
                {"role": "user", "content": question},
                {"role": "assistant", "content": answer},
            ]
        )
        del messages[:-MAX_STORED_MESSAGES]


def _stream_static_result(
    result: dict[str, Any],
    session_id: str | None,
    question: str,
) -> Iterator[str]:
    answer = str(result.get("answer", ""))
    if answer:
        yield _sse({"token": answer})
    yield _sse({"done": True, "sources": result.get("sources", []), "mode": result.get("mode", "")})
    _remember(session_id, question, answer)


def _stream_agent_answer(
    question: str,
    dataset: str | None,
    explicit_agent: str | None,
    session_id: str | None,
    history: list[dict[str, str]],
) -> Iterator[str]:
    config = load_agent_config(STATE.agents_config)
    selected_dataset = validate_dataset(dataset) if dataset else None
    agent = route_agent(
        question=question,
        config=config,
        explicit_agent=explicit_agent,
        explicit_dataset=selected_dataset,
    )

    checker_agent = None
    checker_id = config.defaults.get("source_checker")
    if checker_id:
        checker_agent = config.get(checker_id)

    runtime = get_runtime(config)

    try:
        with runtime.run_agent(agent) as job:
            yield from _stream_running_agent(
                agent=agent,
                question=question,
                index_dir=STATE.index_dir,
                dataset=selected_dataset,
                model_override=STATE.model,
                checker_agent=checker_agent,
                history=history,
                job=job.to_dict(),
                runtime_state=lambda: runtime.get_state(agent.id),
                session_id=session_id,
            )
    except AgentUnavailable as error:
        runtime_state = runtime.get_state(agent.id)
        formatted = format_unavailable_answer(
            str(error),
            agent_name=agent.display_name,
            runtime=runtime_state,
        )
        answer = formatted.answer
        yield _sse({"token": answer})
        yield _sse(
            {
                "done": True,
                "sources": [],
                "mode": "agent_unavailable",
                "pipeline": ["router", "runtime_denied", agent.id, "final_formatter"],
                "agent": agent.id,
                "agent_name": agent.display_name,
                "datasets": [selected_dataset] if selected_dataset else agent.datasets,
                "missing_datasets": [],
                "job": None,
                "runtime": runtime_state,
            }
        )
        _remember(session_id, question, answer)


def _stream_running_agent(
    agent: Agent,
    question: str,
    index_dir: Path,
    dataset: str | None,
    model_override: str | None,
    checker_agent: Agent | None,
    history: list[dict[str, str]],
    job: dict[str, Any],
    runtime_state: Any,
    session_id: str | None,
) -> Iterator[str]:
    datasets, usable, missing_datasets = _collect_usable(agent, question, index_dir, dataset)
    pipeline = ["router", "runtime", agent.id]

    if not usable:
        formatted = format_refusal_answer(
            "Dazu finde ich in den lokalen Daten nichts.",
            agent_name=agent.display_name,
            datasets=datasets,
            missing_datasets=missing_datasets,
        )
        answer = formatted.answer
        yield _sse({"token": answer})
        yield _sse(
            {
                "done": True,
                "sources": [],
                "mode": "refusal",
                "agent": agent.id,
                "agent_name": agent.display_name,
                "datasets": datasets,
                "missing_datasets": missing_datasets,
                "pipeline": pipeline + ["final_formatter"],
                "job": job,
                "runtime": runtime_state(),
            }
        )
        _remember(session_id, question, answer)
        return

    sources = _sources(usable)
    model = model_override if model_override is not None else agent.model
    model = model.strip() if model else ""
    generated_parts: list[str] = []

    if model and "generate" in agent.allowed_tools:
        prompt = _build_prompt(agent, question, usable)
        token_stream = ollama_generate_stream(
            prompt,
            model=model,
            system_prompt=agent.system_prompt,
            temperature=agent.temperature,
            chat_history=history,
        )

        if token_stream is not None:
            try:
                for token in token_stream:
                    generated_parts.append(token)
                    yield _sse({"token": token})
            except Exception:
                generated_parts = []

    source_check = {
        "status": "skipped",
        "grounded": None,
        "confidence": "unknown",
        "issues": ["source checker was not called"],
        "checked_by": None,
    }

    if generated_parts:
        answer = "".join(generated_parts).strip()
        mode = "ollama"
        if checker_agent and checker_agent.id in agent.can_call:
            pipeline.append(checker_agent.id)
            source_check = check_answer_grounding(
                checker_agent=checker_agent,
                answer=answer,
                question=question,
                usable=usable,
            ).to_dict()
    else:
        raw_answer = _fallback_answer(usable)
        formatted = format_extractive_answer(
            raw_answer,
            usable=usable,
            sources=sources,
            agent_name=agent.display_name,
        )
        answer = formatted.answer
        mode = "extractive"
        yield _sse({"token": answer})

    pipeline.append("final_formatter")
    yield _sse(
        {
            "done": True,
            "sources": sources,
            "mode": mode,
            "agent": agent.id,
            "agent_name": agent.display_name,
            "datasets": datasets,
            "missing_datasets": missing_datasets,
            "pipeline": pipeline,
            "source_check": source_check,
            "job": job,
            "runtime": runtime_state(),
        }
    )
    _remember(session_id, question, answer)


def _collect_usable(
    agent: Agent,
    question: str,
    index_dir: Path,
    dataset: str | None,
) -> tuple[list[str], list[tuple[str, IndexedChunk, float]], list[str]]:
    datasets = [dataset] if dataset else agent.datasets
    datasets = [item for item in datasets if item]

    if not datasets:
        datasets = ["default"]

    usable: list[tuple[str, IndexedChunk, float]] = []
    missing_datasets: list[str] = []

    for dataset_name in datasets:
        index_path = index_path_for_dataset(index_dir, dataset_name)
        if not index_path.exists():
            missing_datasets.append(dataset_name)
            continue

        for chunk, score in retrieve(index_path, question, limit=agent.max_chunks):
            if score >= agent.min_score:
                usable.append((dataset_name, chunk, score))

    usable.sort(key=lambda item: item[2], reverse=True)
    return datasets, usable[: agent.max_chunks], missing_datasets


def _sources(usable: list[tuple[str, IndexedChunk, float]]) -> list[dict[str, Any]]:
    return [
        {
            "dataset": dataset_name,
            "source": chunk.source,
            "score": round(score, 3),
        }
        for dataset_name, chunk, score in usable
    ]


def _fallback_answer(usable: list[tuple[str, IndexedChunk, float]]) -> str:
    excerpts = "\n\n".join(
        f"[{dataset}/{chunk.source}]\n{chunk.text}" for dataset, chunk, _score in usable[:2]
    )
    return f"Ich habe dazu diese lokalen Stellen gefunden:\n\n{excerpts}"


def _sse(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _html() -> str:
    return """<!doctype html>
<meta charset="utf-8">
<title>Local RAG Bot</title>
<style>
body{font-family:system-ui,sans-serif;max-width:860px;margin:40px auto;padding:0 16px;line-height:1.5}
textarea,input{width:100%;box-sizing:border-box}
textarea{min-height:100px}
button{padding:8px 14px;cursor:pointer}
pre{white-space:pre-wrap;background:#f6f6f6;padding:14px;border-radius:8px;overflow:auto}
.answer{background:#fff;border:1px solid #ddd}
small{color:#666}
details{margin-top:16px}
</style>

<h1>Local RAG Bot</h1>

<label>Dataset <small>(optional)</small></label>
<input id="dataset" placeholder="default, coach-potato, devops, homelab">

<br><br>

<label>Agent <small>(optional)</small></label>
<input id="agent" placeholder="local_answerer, coach_agent, devops_agent">

<br><br>

<label>Session <small>(optional, remembers last 6 messages)</small></label>
<input id="session" placeholder="demo-session">

<br><br>

<label>Question</label>
<textarea id="q">What is this bot allowed to answer?</textarea><br>

<button onclick="ask(false)">Ask</button>
<button onclick="ask(true)">Stream</button>

<h2>Answer</h2>
<pre id="answer" class="answer"></pre>

<details>
  <summary>Debug JSON</summary>
  <pre id="debug"></pre>
</details>

<script>
async function ask(stream){
  const question = document.getElementById('q').value;
  const dataset = document.getElementById('dataset').value;
  const agent = document.getElementById('agent').value;
  const session_id = document.getElementById('session').value;

  const payload = {question};
  if (dataset) payload.dataset = dataset;
  if (agent) payload.agent = agent;
  if (session_id) payload.session_id = session_id;

  document.getElementById('answer').textContent = '';
  document.getElementById('debug').textContent = '';

  const res = await fetch(stream ? '/stream' : '/ask',{
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify(payload)
  });

  if (!stream) {
    const data = await res.json();
    document.getElementById('answer').textContent = data.answer || '';
    document.getElementById('debug').textContent = JSON.stringify(data, null, 2);
    return;
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const {value, done} = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, {stream:true});
    const events = buffer.split('\n\n');
    buffer = events.pop();

    for (const event of events) {
      if (!event.startsWith('data: ')) continue;
      const data = JSON.parse(event.slice(6));
      if (data.token) document.getElementById('answer').textContent += data.token;
      if (data.done) document.getElementById('debug').textContent = JSON.stringify(data, null, 2);
    }
  }
}
</script>"""


def serve(
    index_dir: Path,
    host: str,
    port: int,
    model: str | None = None,
    agents_config: Path = DEFAULT_AGENTS_CONFIG,
) -> None:
    STATE.index_dir = index_dir
    STATE.model = model
    STATE.agents_config = agents_config

    uvicorn.run(app, host=host, port=port)
