from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Chunk:
    source: str
    chunk_id: str
    text: str


def chunk_text(source: str, text: str, max_words: int = 160, overlap_words: int = 35) -> list[Chunk]:
    words = text.split()
    if not words:
        return []

    chunks: list[Chunk] = []
    step = max(1, max_words - overlap_words)
    for idx, start in enumerate(range(0, len(words), step)):
        part = words[start : start + max_words]
        if not part:
            break
        chunks.append(Chunk(source=source, chunk_id=f"{source}#{idx}", text=" ".join(part)))
        if start + max_words >= len(words):
            break
    return chunks

