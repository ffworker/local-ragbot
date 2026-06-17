from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class FormattedAnswer:
    answer: str
    raw_answer: str
    display: dict

    def to_dict(self) -> dict:
        return {
            "answer": self.answer,
            "raw_answer": self.raw_answer,
            "display": self.display,
        }


def _collapse_blank_lines(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _trim_inline(text: str, max_chars: int = 1600) -> str:
    text = " ".join(text.split())
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3].rstrip() + "..."


def _source_label(source: dict) -> str:
    dataset = source.get("dataset")
    name = source.get("source", "unknown")
    return f"{dataset}/{name}" if dataset else str(name)


def _sources_markdown(sources: list[dict]) -> str:
    if not sources:
        return ""

    lines = ["## Sources", ""]

    for source in sources:
        label = _source_label(source)
        score = source.get("score")
        if score is None:
            lines.append(f"- `{label}`")
        else:
            lines.append(f"- `{label}` — score `{score}`")

    return "\n".join(lines)


def _metadata_line(agent_name: str, mode: str) -> str:
    return f"_Answered by: `{agent_name}` · mode: `{mode}`_"


def format_refusal_answer(
    raw_answer: str,
    *,
    agent_name: str,
    datasets: list[str],
    missing_datasets: list[str],
) -> FormattedAnswer:
    lines = [
        "## Answer",
        "",
        raw_answer.strip(),
        "",
        "---",
        "",
        _metadata_line(agent_name, "refusal"),
    ]

    if datasets:
        lines.extend(["", "## Checked datasets", ""])
        lines.extend(f"- `{dataset}`" for dataset in datasets)

    if missing_datasets:
        lines.extend(["", "## Missing datasets", ""])
        lines.extend(f"- `{dataset}`" for dataset in missing_datasets)

    return FormattedAnswer(
        answer=_collapse_blank_lines("\n".join(lines)),
        raw_answer=raw_answer,
        display={
            "format": "markdown",
            "title": "Answer",
            "kind": "refusal",
        },
    )


def format_extractive_answer(
    raw_answer: str,
    *,
    usable: list[tuple[str, object, float]],
    sources: list[dict],
    agent_name: str,
) -> FormattedAnswer:
    lines = [
        "## Answer",
        "",
        "I found relevant local context, but no LLM-generated answer was available.",
        "",
        "## Relevant excerpts",
        "",
    ]

    for number, (dataset, chunk, score) in enumerate(usable[:3], start=1):
        label = f"{dataset}/{chunk.source}"
        excerpt = _trim_inline(chunk.text)

        lines.extend(
            [
                f"### {number}. `{label}`",
                "",
                f"> {excerpt}",
                "",
                f"_Score: `{round(score, 3)}`_",
                "",
            ]
        )

    source_block = _sources_markdown(sources)
    if source_block:
        lines.extend(["---", "", source_block])

    lines.extend(["", "---", "", _metadata_line(agent_name, "extractive")])

    return FormattedAnswer(
        answer=_collapse_blank_lines("\n".join(lines)),
        raw_answer=raw_answer,
        display={
            "format": "markdown",
            "title": "Answer",
            "kind": "extractive",
        },
    )


def format_generated_answer(
    raw_answer: str,
    *,
    sources: list[dict],
    agent_name: str,
    mode: str,
) -> FormattedAnswer:
    cleaned = _collapse_blank_lines(raw_answer)

    # If the model already made a good Markdown answer, keep it.
    # If it returned plain text, wrap it in a stable readable structure.
    if not cleaned.startswith("#"):
        body = "\n".join(["## Answer", "", cleaned])
    else:
        body = cleaned

    source_block = _sources_markdown(sources)

    lines = [body]

    if source_block:
        lines.extend(["", "---", "", source_block])

    lines.extend(["", "---", "", _metadata_line(agent_name, mode)])

    return FormattedAnswer(
        answer=_collapse_blank_lines("\n".join(lines)),
        raw_answer=raw_answer,
        display={
            "format": "markdown",
            "title": "Answer",
            "kind": "generated",
        },
    )


def format_unavailable_answer(
    raw_answer: str,
    *,
    agent_name: str,
    runtime: dict | None = None,
) -> FormattedAnswer:
    lines = [
        "## Agent unavailable",
        "",
        raw_answer.strip(),
        "",
        "---",
        "",
        f"_Agent: `{agent_name}`_",
    ]

    if runtime:
        lines.extend(
            [
                "",
                "## Runtime",
                "",
                f"- State: `{runtime.get('state', 'unknown')}`",
                f"- Active jobs: `{runtime.get('active_jobs', '?')}/{runtime.get('max_concurrent_jobs', '?')}`",
            ]
        )

    return FormattedAnswer(
        answer=_collapse_blank_lines("\n".join(lines)),
        raw_answer=raw_answer,
        display={
            "format": "markdown",
            "title": "Agent unavailable",
            "kind": "agent_unavailable",
        },
    )
