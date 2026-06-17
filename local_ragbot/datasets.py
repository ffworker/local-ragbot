from __future__ import annotations

import re
from pathlib import Path

DATASET_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,63}$")


def validate_dataset(name: str) -> str:
    dataset = name.strip()
    if not DATASET_RE.fullmatch(dataset):
        raise ValueError("Dataset names may only contain letters, numbers, dots, underscores, and dashes.")
    return dataset


def index_path_for_dataset(index_dir: Path, dataset: str) -> Path:
    return index_dir / f"{validate_dataset(dataset)}.json"


def data_path_for_dataset(data_root: Path, dataset: str) -> Path:
    return data_root / validate_dataset(dataset)


def list_indexed_datasets(index_dir: Path) -> list[str]:
    if not index_dir.exists():
        return []
    return sorted(path.stem for path in index_dir.glob("*.json") if DATASET_RE.fullmatch(path.stem))

