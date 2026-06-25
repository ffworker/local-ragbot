# changed: replace fixed-size word windows with structure-aware chunks and metadata.
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


MAX_TXT_WORDS = 400
MAX_MD_WORDS = 500
FENCE_RE = re.compile(r"^\s*" + "`" * 3)


@dataclass(frozen=True)
class Chunk:
    source: str
    chunk_id: str
    text: str
    dataset: str
    section: str
    chunk_index: int

    @property
    def metadata(self) -> dict[str, str | int]:
        return {
            "source": self.source,
            "dataset": self.dataset,
            "section": self.section,
            "chunk_index": self.chunk_index,
        }


def chunk_text(source: str, text: str, dataset: str = "default", suffix: str | None = None) -> list[Chunk]:
    suffix = (suffix or Path(source).suffix).casefold()
    if suffix in {".md", ".markdown"}:
        return _chunk_markdown(source, text, dataset)
    if suffix == ".json":
        return _chunk_json(source, text, dataset)
    return _chunk_plain_text(source, text, dataset)


def _make_chunk(
    source: str,
    dataset: str,
    section: str,
    index: int,
    text: str,
) -> Chunk | None:
    clean = text.strip()
    if not clean:
        return None
    return Chunk(
        source=source,
        chunk_id=f"{source}#{index}",
        text=clean,
        dataset=dataset,
        section=section or "document",
        chunk_index=index,
    )


def _word_count(text: str) -> int:
    return len(text.split())


def _chunk_plain_text(source: str, text: str, dataset: str) -> list[Chunk]:
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n+", text) if part.strip()]
    chunks: list[Chunk] = []
    current: list[str] = []
    current_words = 0

    def flush() -> None:
        nonlocal current, current_words
        chunk = _make_chunk(source, dataset, "paragraphs", len(chunks), "\n\n".join(current))
        if chunk:
            chunks.append(chunk)
        current = []
        current_words = 0

    for paragraph in paragraphs:
        words = paragraph.split()
        if len(words) > MAX_TXT_WORDS:
            if current:
                flush()
            for start in range(0, len(words), MAX_TXT_WORDS):
                chunk = _make_chunk(
                    source,
                    dataset,
                    "paragraphs",
                    len(chunks),
                    " ".join(words[start : start + MAX_TXT_WORDS]),
                )
                if chunk:
                    chunks.append(chunk)
            continue

        if current and current_words + len(words) > MAX_TXT_WORDS:
            flush()

        current.append(paragraph)
        current_words += len(words)

    if current:
        flush()

    return chunks


def _chunk_markdown(source: str, text: str, dataset: str) -> list[Chunk]:
    sections = _split_markdown_sections(text)
    chunks: list[Chunk] = []

    for section, section_text in sections:
        for part in _pack_markdown_blocks(section_text):
            chunk = _make_chunk(source, dataset, section, len(chunks), part)
            if chunk:
                chunks.append(chunk)

    return chunks


def _split_markdown_sections(text: str) -> list[tuple[str, str]]:
    sections: list[tuple[str, list[str]]] = [("intro", [])]
    in_fence = False

    for line in text.splitlines():
        if FENCE_RE.match(line):
            in_fence = not in_fence

        if not in_fence and line.startswith("## "):
            heading = line.lstrip("#").strip() or "section"
            sections.append((heading, [line]))
            continue

        sections[-1][1].append(line)

    return [(section, "\n".join(lines).strip()) for section, lines in sections if "\n".join(lines).strip()]


def _pack_markdown_blocks(text: str) -> list[str]:
    blocks = _markdown_blocks(text)
    chunks: list[str] = []
    current: list[str] = []
    current_words = 0

    for block in blocks:
        block_words = _word_count(block)
        if current and current_words + block_words > MAX_MD_WORDS:
            chunks.append("\n\n".join(current).strip())
            current = []
            current_words = 0

        current.append(block)
        current_words += block_words

    if current:
        chunks.append("\n\n".join(current).strip())

    return chunks


def _markdown_blocks(text: str) -> list[str]:
    blocks: list[str] = []
    current: list[str] = []
    in_fence = False

    for line in text.splitlines():
        if FENCE_RE.match(line):
            in_fence = not in_fence
            current.append(line)
            continue

        if not in_fence and not line.strip():
            if current:
                blocks.append("\n".join(current).strip())
                current = []
            continue

        current.append(line)

    if current:
        blocks.append("\n".join(current).strip())

    return [block for block in blocks if block]


def _chunk_json(source: str, text: str, dataset: str) -> list[Chunk]:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return _chunk_plain_text(source, text, dataset)

    entries: list[tuple[str, Any]]
    if isinstance(payload, list):
        entries = [(f"[{index}]", item) for index, item in enumerate(payload)]
    elif isinstance(payload, dict):
        entries = [(str(key), value) for key, value in payload.items()]
    else:
        entries = [("document", payload)]

    chunks: list[Chunk] = []
    for section, value in entries:
        rendered = json.dumps(value, ensure_ascii=False, indent=2)
        chunk = _make_chunk(source, dataset, section, len(chunks), rendered)
        if chunk:
            chunks.append(chunk)

    return chunks
