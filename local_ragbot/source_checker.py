from __future__ import annotations

import json
import re
from dataclasses import dataclass

from .agents import Agent
from .llm import ollama_generate
from .retrieval import IndexedChunk


@dataclass(frozen=True)
class SourceCheck:
    status: str
    grounded: bool | None
    confidence: str
    issues: list[str]
    checked_by: str | None = None

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "grounded": self.grounded,
            "confidence": self.confidence,
            "issues": self.issues,
            "checked_by": self.checked_by,
        }


def _source_name(dataset: str, chunk: IndexedChunk) -> str:
    return f"{dataset}/{chunk.source}"


def _context_text(usable: list[tuple[str, IndexedChunk, float]], max_chars: int = 6000) -> str:
    blocks: list[str] = []

    for dataset, chunk, score in usable:
        blocks.append(
            f"Source: {_source_name(dataset, chunk)}\n"
            f"Score: {score:.3f}\n"
            f"Text:\n{chunk.text}"
        )

    context = "\n\n---\n\n".join(blocks)

    if len(context) > max_chars:
        return context[: max_chars - 3].rstrip() + "..."

    return context


def _extract_json(text: str) -> dict | None:
    text = text.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not match:
        return None

    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


def check_answer_grounding(
    *,
    checker_agent: Agent | None,
    answer: str,
    question: str,
    usable: list[tuple[str, IndexedChunk, float]],
) -> SourceCheck:
    if checker_agent is None:
        return SourceCheck(
            status="skipped",
            grounded=None,
            confidence="unknown",
            issues=["source checker agent is not configured"],
            checked_by=None,
        )

    if not checker_agent.model:
        return SourceCheck(
            status="skipped",
            grounded=None,
            confidence="unknown",
            issues=["source checker has no model configured"],
            checked_by=checker_agent.id,
        )

    if "verify" not in checker_agent.allowed_tools:
        return SourceCheck(
            status="skipped",
            grounded=None,
            confidence="unknown",
            issues=["source checker is not allowed to verify"],
            checked_by=checker_agent.id,
        )

    context = _context_text(usable)

    prompt = f"""You are a strict grounding checker.

Your job:
- Check whether the answer is supported by the local context.
- Do not judge whether the answer is useful.
- Do not rewrite the answer.
- Only decide whether the answer makes claims not supported by the context.

Return ONLY valid JSON with this exact shape:

{{
  "grounded": true,
  "confidence": "high",
  "issues": []
}}

Allowed confidence values:
- "high"
- "medium"
- "low"

Question:
{question}

Answer:
{answer}

Local context:
{context}
"""

    raw = ollama_generate(
        prompt,
        model=checker_agent.model,
        system_prompt=checker_agent.system_prompt,
        temperature=checker_agent.temperature,
    )

    if not raw:
        return SourceCheck(
            status="skipped",
            grounded=None,
            confidence="unknown",
            issues=["source checker model unavailable or returned no response"],
            checked_by=checker_agent.id,
        )

    parsed = _extract_json(raw)

    if parsed is None:
        return SourceCheck(
            status="skipped",
            grounded=None,
            confidence="unknown",
            issues=["source checker returned invalid JSON"],
            checked_by=checker_agent.id,
        )

    grounded = parsed.get("grounded")
    confidence = str(parsed.get("confidence", "unknown")).strip().lower()
    issues = parsed.get("issues", [])

    if not isinstance(grounded, bool):
        grounded = None

    if confidence not in {"high", "medium", "low"}:
        confidence = "unknown"

    if not isinstance(issues, list):
        issues = [str(issues)]

    clean_issues = [str(issue).strip() for issue in issues if str(issue).strip()]

    return SourceCheck(
        status="checked",
        grounded=grounded,
        confidence=confidence,
        issues=clean_issues,
        checked_by=checker_agent.id,
    )
