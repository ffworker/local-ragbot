from __future__ import annotations

from pathlib import Path

from .agents import DEFAULT_AGENTS_CONFIG, Agent, load_agent_config
from .datasets import index_path_for_dataset, validate_dataset
from .llm import ollama_generate
from .retrieval import IndexedChunk, retrieve
from .router import route_agent


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

    pipeline = ["router", agent.id]

    if not usable:
        return {
            "answer": "Dazu finde ich in den lokalen Daten nichts.",
            "sources": [],
            "mode": "refusal",
            "agent": agent.id,
            "agent_name": agent.display_name,
            "datasets": datasets,
            "missing_datasets": missing_datasets,
            "pipeline": pipeline,
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

    if generated:
        answer = generated.strip()
        mode = "ollama"
    else:
        answer = _fallback_answer(usable)
        mode = "extractive"

    if "source_checker" in agent.can_call:
        pipeline.append("source_checker")

    pipeline.append("final_formatter")

    return {
        "answer": answer,
        "sources": [
            {
                "dataset": dataset_name,
                "source": chunk.source,
                "score": round(score, 3),
            }
            for dataset_name, chunk, score in usable
        ],
        "mode": mode,
        "agent": agent.id,
        "agent_name": agent.display_name,
        "datasets": datasets,
        "missing_datasets": missing_datasets,
        "pipeline": pipeline,
    }
