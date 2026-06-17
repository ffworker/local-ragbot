from __future__ import annotations

from pathlib import Path

from .llm import ollama_generate
from .retrieval import retrieve


def answer_question(
    question: str,
    index_path: Path,
    model: str | None = None,
    min_score: float = 0.12,
    limit: int = 4,
) -> dict:
    results = retrieve(index_path, question, limit=limit)
    usable = [(chunk, score) for chunk, score in results if score >= min_score]

    if not usable:
        return {
            "answer": "Dazu finde ich in den lokalen Daten nichts.",
            "sources": [],
            "mode": "refusal",
        }

    context = "\n\n".join(
        f"Source: {chunk.source}\nScore: {score:.3f}\nText: {chunk.text}"
        for chunk, score in usable
    )
    prompt = f"Local context:\n{context}\n\nQuestion: {question}\n\nAnswer:"

    generated = ollama_generate(prompt, model) if model else None
    if generated:
        answer = generated.strip()
        mode = "ollama"
    else:
        excerpts = "\n\n".join(f"[{chunk.source}] {chunk.text}" for chunk, _ in usable[:2])
        answer = f"Ich habe dazu diese lokalen Stellen gefunden:\n\n{excerpts}"
        mode = "extractive"

    return {
        "answer": answer,
        "sources": [{"source": chunk.source, "score": round(score, 3)} for chunk, score in usable],
        "mode": mode,
    }

