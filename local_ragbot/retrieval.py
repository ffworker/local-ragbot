from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import asdict, dataclass
from pathlib import Path

from .chunking import Chunk, chunk_text

TOKEN_RE = re.compile(r"[\wÄÖÜäöüß]+", re.UNICODE)
SUPPORTED_SUFFIXES = {".md", ".markdown", ".txt", ".json"}


@dataclass
class IndexedChunk:
    source: str
    chunk_id: str
    text: str
    vector: list[float]


def tokenize(text: str) -> list[str]:
    return [token.casefold() for token in TOKEN_RE.findall(text)]


def embed(text: str, dims: int = 384) -> list[float]:
    vector = [0.0] * dims
    tokens = tokenize(text)
    if not tokens:
        return vector

    for token in tokens:
        digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
        raw = int.from_bytes(digest, "big")
        index = raw % dims
        sign = -1.0 if raw & 1 else 1.0
        vector[index] += sign

    norm = math.sqrt(sum(value * value for value in vector)) or 1.0
    return [value / norm for value in vector]


def cosine(left: list[float], right: list[float]) -> float:
    return sum(a * b for a, b in zip(left, right))


def read_documents(data_dir: Path) -> list[Chunk]:
    chunks: list[Chunk] = []
    for path in sorted(data_dir.rglob("*")):
        if not path.is_file() or path.suffix.casefold() not in SUPPORTED_SUFFIXES:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        source = str(path.relative_to(data_dir))
        chunks.extend(chunk_text(source, text))
    return chunks


def build_index(data_dir: Path, index_path: Path) -> int:
    chunks = read_documents(data_dir)
    indexed = [
        IndexedChunk(
            source=chunk.source,
            chunk_id=chunk.chunk_id,
            text=chunk.text,
            vector=embed(chunk.text),
        )
        for chunk in chunks
    ]
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_text(
        json.dumps({"version": 1, "chunks": [asdict(item) for item in indexed]}, indent=2),
        encoding="utf-8",
    )
    return len(indexed)


def load_index(index_path: Path) -> list[IndexedChunk]:
    payload = json.loads(index_path.read_text(encoding="utf-8"))
    return [IndexedChunk(**item) for item in payload.get("chunks", [])]


def retrieve(index_path: Path, question: str, limit: int = 4) -> list[tuple[IndexedChunk, float]]:
    question_vector = embed(question)
    scored = [(chunk, cosine(question_vector, chunk.vector)) for chunk in load_index(index_path)]
    scored.sort(key=lambda item: item[1], reverse=True)
    return scored[:limit]

