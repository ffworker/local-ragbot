from __future__ import annotations

from pathlib import Path

from .agents import DEFAULT_AGENTS_CONFIG, Agent, load_agent_config
from .datasets import index_path_for_dataset, validate_dataset
from .llm import ollama_generate
from .retrieval import IndexedChunk, retrieve
from .router import route_agent
from .runtime import AgentUnavailable, get_runtime
from .runtime import AgentUnavailable, get_runtime
from .source_checker import check_answer_grounding
from .formatter import (
    format_extractive_answer,
    format_generated_answer,
    format_refusal_answer,
    format_unavailable_answer,
)


def _source_name(dataset: str, chunk: IndexedChunk) -> str:
    return f"{dataset}/{chunk.source}"


def _build_prompt(agent: Agent, question: str, usable: list[tuple[str, IndexedChunk, float]]) -> str:
    context = "\n\n".join(
        f"Source: {_source_name(dataset, chunk)}\n"
        f"Score: {score:.3f}\n"
        f"Text: {chunk.text}"
        for dataset, chunk, score in usable
    )

    return (
        f"Agent: {agent.display_name}\n"
        f"Task: {agent.task}\n"
        f"Output style: {agent.output_style}\n\n"
        "Formatting rules:\n"
        "- Use Markdown.\n"
        "- Start with a short direct answer.\n"
        "- Use headings when helpful.\n"
        "- Use bullet points for steps or lists.\n"
        "- Keep paragraphs short.\n"
        "- Do not dump raw context unless asked.\n"
        "- Cite source names from the context when possible.\n\n"
        f"Local context:\n{context}\n\n"
        f"Question: {question}\n\n"
        f"Answer:"
    )


def _fallback_answer(usable: list[tuple[str, IndexedChunk, float]]) -> str:
    excerpts = "\n\n".join(
        f"[{_source_name(dataset, chunk)}]\n{chunk.text}"
        for dataset, chunk, _score in usable[:2]
    )
    return f"Ich habe dazu diese lokalen Stellen gefunden:\n\n{excerpts}"


def _execute_agent_answer(
    agent: Agent,
    question: str,
    index_dir: Path,
    dataset: str | None,
    model_override: str | None,
    checker_agent: Agent | None = None,
) -> dict:
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

        results = retrieve(index_path, question, limit=agent.max_chunks)
        for chunk, score in results:
            if score >= agent.min_score:
                usable.append((dataset_name, chunk, score))

    usable.sort(key=lambda item: item[2], reverse=True)
    usable = usable[: agent.max_chunks]

    pipeline = ["router", "runtime", agent.id]

    if not usable:
        raw_answer = "Dazu finde ich in den lokalen Daten nichts."
        formatted = format_refusal_answer(
            raw_answer,
            agent_name=agent.display_name,
            datasets=datasets,
            missing_datasets=missing_datasets,
        )

        return {
            **formatted.to_dict(),
            "sources": [],
            "mode": "refusal",
            "agent": agent.id,
            "agent_name": agent.display_name,
            "datasets": datasets,
            "missing_datasets": missing_datasets,
            "pipeline": pipeline + ["final_formatter"],
        }

    model = model_override if model_override is not None else agent.model
    model = model.strip() if model else ""

    generated = None
    if model and "generate" in agent.allowed_tools:
        prompt = _build_prompt(agent, question, usable)
        generated = ollama_generate(
            prompt,
            model=model,
            system_prompt=agent.system_prompt,
            temperature=agent.temperature,
        )
    
    sources = [
        {
            "dataset": dataset_name,
            "source": chunk.source,
            "score": round(score, 3),
        }
        for dataset_name, chunk, score in usable
    ]

    if generated:
        raw_answer = generated.strip()
        mode = "ollama"
    else:
        raw_answer = _fallback_answer(usable)
        mode = "extractive"

    source_check = {
        "status": "skipped",
        "grounded": None,
        "confidence": "unknown",
        "issues": ["source checker was not called"],
        "checked_by": None,
    }

    if checker_agent and checker_agent.id in agent.can_call:
        pipeline.append(checker_agent.id)
        source_check = check_answer_grounding(
            checker_agent=checker_agent,
            answer=raw_answer,
            question=question,
            usable=usable,
        ).to_dict()

    pipeline.append("final_formatter")

    if mode == "extractive":
        formatted = format_extractive_answer(
            raw_answer,
            usable=usable,
            sources=sources,
            agent_name=agent.display_name,
        )
    else:
        formatted = format_generated_answer(
            raw_answer,
            sources=sources,
            agent_name=agent.display_name,
            mode=mode,
        )

    return {
        **formatted.to_dict(),
        "sources": sources,
        "mode": mode,
        "agent": agent.id,
        "agent_name": agent.display_name,
        "datasets": datasets,
        "missing_datasets": missing_datasets,
        "pipeline": pipeline,
        "source_check": source_check,
    }
    

def answer_with_agent(
    question: str,
    index_dir: Path,
    config_path: Path = DEFAULT_AGENTS_CONFIG,
    explicit_agent: str | None = None,
    explicit_dataset: str | None = None,
    model_override: str | None = None,
) -> dict:
    config = load_agent_config(config_path)
    dataset = validate_dataset(explicit_dataset) if explicit_dataset else None

    agent = route_agent(
        question=question,
        config=config,
        explicit_agent=explicit_agent,
        explicit_dataset=dataset,
    )
    
    checker_agent = None
    checker_id = config.defaults.get("source_checker")
    if checker_id:
        checker_agent = config.get(checker_id)
        
    runtime = get_runtime(config)

    try:
        with runtime.run_agent(agent) as job:
            result = _execute_agent_answer(
                agent=agent,
                question=question,
                index_dir=index_dir,
                dataset=dataset,
                model_override=model_override,
                checker_agent=checker_agent,
            )

        result["job"] = job.to_dict()
        result["runtime"] = runtime.get_state(agent.id)
        return result

    except AgentUnavailable as error:
        runtime_state = runtime.get_state(agent.id)
        raw_answer = str(error)
        formatted = format_unavailable_answer(
            raw_answer,
            agent_name=agent.display_name,
            runtime=runtime_state,
        )

    return {
        **formatted.to_dict(),
        "sources": [],
        "mode": "agent_unavailable",
        "agent": agent.id,
        "agent_name": agent.display_name,
        "datasets": [dataset] if dataset else agent.datasets,
        "missing_datasets": [],
        "pipeline": ["router", "runtime_denied", agent.id, "final_formatter"],
        "job": None,
        "runtime": runtime_state,
    }
