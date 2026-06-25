# changed: use Ollama nomic embeddings with persistent Chroma, plus keyword fallback metadata indexes.
from __future__ import annotations

import json
import math
import re
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import httpx

from .chunking import Chunk, chunk_text

TOKEN_RE = re.compile(r"[\wÄÖÜäöüß]+", re.UNICODE)
SUPPORTED_SUFFIXES = {".md", ".markdown", ".txt", ".json"}
OLLAMA_HOST = "http://localhost:11434"
EMBED_MODEL = "nomic-embed-text"


@dataclass
class IndexedChunk:
    source: str
    chunk_id: str
    text: str
    dataset: str = "default"
    section: str = "document"
    chunk_index: int = 0


def tokenize(text: str) -> list[str]:
    return [token.casefold() for token in TOKEN_RE.findall(text)]


def ollama_embed(
    text: str,
    model: str = EMBED_MODEL,
    host: str = OLLAMA_HOST,
    timeout: float = 60.0,
) -> list[float] | None:
    try:
        response = httpx.post(
            f"{host.rstrip('/')}/api/embeddings",
            json={"model": model, "prompt": text},
            timeout=timeout,
        )
        response.raise_for_status()
        data = response.json()
    except (httpx.HTTPError, ValueError):
        return None

    embedding = data.get("embedding")
    if not isinstance(embedding, list):
        return None

    try:
        return [float(value) for value in embedding]
    except (TypeError, ValueError):
        return None


def read_documents(data_dir: Path, dataset: str = "default") -> list[Chunk]:
    chunks: list[Chunk] = []
    for path in sorted(data_dir.rglob("*")):
        if not path.is_file() or path.suffix.casefold() not in SUPPORTED_SUFFIXES:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        source = str(path.relative_to(data_dir))
        chunks.extend(chunk_text(source, text, dataset=dataset, suffix=path.suffix))
    return chunks


def build_index(data_dir: Path, index_path: Path) -> int:
    dataset = _dataset_from_index_path(index_path)
    chunks = read_documents(data_dir, dataset=dataset)
    indexed = [
        IndexedChunk(
            source=chunk.source,
            chunk_id=chunk.chunk_id,
            text=chunk.text,
            dataset=chunk.dataset,
            section=chunk.section,
            chunk_index=chunk.chunk_index,
        )
        for chunk in chunks
    ]

    index_path.parent.mkdir(parents=True, exist_ok=True)

    embeddings: list[list[float]] = []
    for chunk in indexed:
        embedding = ollama_embed(chunk.text)
        if embedding is None:
            embeddings = []
            break
        embeddings.append(embedding)

    backend = "keyword"
    if embeddings and _write_chroma(index_path, indexed, embeddings):
        backend = "chromadb"
    else:
        _remove_chroma_collection(index_path)

    _write_marker(index_path, indexed, backend=backend)
    return len(indexed)


def load_index(index_path: Path) -> list[IndexedChunk]:
    payload = json.loads(index_path.read_text(encoding="utf-8"))
    return [_chunk_from_payload(item, index_path) for item in payload.get("chunks", [])]


def retrieve(index_path: Path, question: str, limit: int = 4) -> list[tuple[IndexedChunk, float]]:
    question_embedding = ollama_embed(question)
    if question_embedding is not None:
        chroma_results = _retrieve_chroma(index_path, question_embedding, limit)
        if chroma_results:
            return chroma_results

    return _retrieve_keyword(index_path, question, limit)


def _dataset_from_index_path(index_path: Path) -> str:
    return index_path.stem or "default"


def _chroma_path(index_path: Path) -> Path:
    return index_path.with_suffix("")


def _collection_name(index_path: Path) -> str:
    name = re.sub(r"[^a-zA-Z0-9._-]", "_", _dataset_from_index_path(index_path))
    name = name.strip("._-") or "default"
    if len(name) < 3:
        name = f"ds_{name}"
    return name[:63]


def _write_marker(index_path: Path, chunks: list[IndexedChunk], backend: str) -> None:
    payload = {
        "version": 2,
        "backend": backend,
        "embedding_model": EMBED_MODEL if backend == "chromadb" else None,
        "chroma_path": str(_chroma_path(index_path)),
        "collection": _collection_name(index_path),
        "chunks": [asdict(chunk) for chunk in chunks],
    }
    index_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_chroma(
    index_path: Path,
    chunks: list[IndexedChunk],
    embeddings: list[list[float]],
) -> bool:
    try:
        import chromadb
    except ImportError:
        return False

    chroma_path = _chroma_path(index_path)
    chroma_path.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(chroma_path))
    collection_name = _collection_name(index_path)

    try:
        client.delete_collection(collection_name)
    except Exception:
        pass

    try:
        collection = client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )
        if chunks:
            collection.upsert(
                ids=[chunk.chunk_id for chunk in chunks],
                documents=[chunk.text for chunk in chunks],
                embeddings=embeddings,
                metadatas=[
                    {
                        "source": chunk.source,
                        "dataset": chunk.dataset,
                        "section": chunk.section,
                        "chunk_index": chunk.chunk_index,
                    }
                    for chunk in chunks
                ],
            )
    except Exception:
        return False

    return True


def _remove_chroma_collection(index_path: Path) -> None:
    chroma_path = _chroma_path(index_path)
    if not chroma_path.exists():
        return

    try:
        shutil.rmtree(chroma_path)
    except OSError:
        pass


def _retrieve_chroma(
    index_path: Path,
    question_embedding: list[float],
    limit: int,
) -> list[tuple[IndexedChunk, float]]:
    if not _chroma_path(index_path).exists():
        return []

    try:
        import chromadb
    except ImportError:
        return []

    try:
        client = chromadb.PersistentClient(path=str(_chroma_path(index_path)))
        collection = client.get_collection(_collection_name(index_path))
        result = collection.query(
            query_embeddings=[question_embedding],
            n_results=limit,
            include=["documents", "metadatas", "distances"],
        )
    except Exception:
        return []

    ids = result.get("ids", [[]])[0]
    documents = result.get("documents", [[]])[0]
    metadatas = result.get("metadatas", [[]])[0]
    distances = result.get("distances", [[]])[0]

    chunks: list[tuple[IndexedChunk, float]] = []
    for chunk_id, document, metadata, distance in zip(ids, documents, metadatas, distances):
        metadata = metadata or {}
        score = max(0.0, 1.0 - float(distance))
        chunks.append(
            (
                IndexedChunk(
                    source=str(metadata.get("source", "")),
                    chunk_id=str(chunk_id),
                    text=str(document or ""),
                    dataset=str(metadata.get("dataset", _dataset_from_index_path(index_path))),
                    section=str(metadata.get("section", "document")),
                    chunk_index=int(metadata.get("chunk_index", 0)),
                ),
                score,
            )
        )

    return chunks


def _retrieve_keyword(index_path: Path, question: str, limit: int) -> list[tuple[IndexedChunk, float]]:
    question_terms = set(tokenize(question))
    if not question_terms:
        return [(chunk, 0.0) for chunk in load_index(index_path)[:limit]]

    scored = [(_keyword_score(question_terms, chunk.text), chunk) for chunk in load_index(index_path)]
    scored.sort(key=lambda item: item[0], reverse=True)
    return [(chunk, score) for score, chunk in scored[:limit]]


def _keyword_score(question_terms: set[str], text: str) -> float:
    tokens = tokenize(text)
    if not tokens:
        return 0.0

    token_counts: dict[str, int] = {}
    for token in tokens:
        token_counts[token] = token_counts.get(token, 0) + 1

    overlap = question_terms.intersection(token_counts)
    if not overlap:
        return 0.0

    weighted_overlap = sum(1.0 + math.log(token_counts[token]) for token in overlap)
    return min(1.0, weighted_overlap / max(1, len(question_terms)))


def _chunk_from_payload(item: dict[str, Any], index_path: Path) -> IndexedChunk:
    return IndexedChunk(
        source=str(item.get("source", "")),
        chunk_id=str(item.get("chunk_id", "")),
        text=str(item.get("text", "")),
        dataset=str(item.get("dataset", _dataset_from_index_path(index_path))),
        section=str(item.get("section", "document")),
        chunk_index=int(item.get("chunk_index", 0)),
    )
