from __future__ import annotations

import argparse
import json
from pathlib import Path

from .datasets import data_path_for_dataset, index_path_for_dataset, list_indexed_datasets
from .qa import answer_question
from .retrieval import build_index
from .server import serve


def main() -> None:
    parser = argparse.ArgumentParser(prog="local-ragbot")
    sub = parser.add_subparsers(dest="command", required=True)

    ingest = sub.add_parser("ingest", help="Index local documents")
    ingest.add_argument("data_dir", type=Path)
    ingest.add_argument("--index", type=Path, default=Path("indexes/default.json"))
    ingest.add_argument("--dataset", default=None)
    ingest.add_argument("--index-dir", type=Path, default=Path("indexes"))

    ask = sub.add_parser("ask", help="Ask a question")
    ask.add_argument("question")
    ask.add_argument("--index", type=Path, default=Path("indexes/default.json"))
    ask.add_argument("--dataset", default=None)
    ask.add_argument("--index-dir", type=Path, default=Path("indexes"))
    ask.add_argument("--model", default=None)
    ask.add_argument("--json", action="store_true")

    server = sub.add_parser("serve", help="Start HTTP server")
    server.add_argument("--index-dir", type=Path, default=Path("indexes"))
    server.add_argument("--host", default="127.0.0.1")
    server.add_argument("--port", type=int, default=8088)
    server.add_argument("--model", default=None)

    datasets = sub.add_parser("datasets", help="List indexed datasets")
    datasets.add_argument("--index-dir", type=Path, default=Path("indexes"))

    args = parser.parse_args()

    if args.command == "ingest":
        index_path = index_path_for_dataset(args.index_dir, args.dataset) if args.dataset else args.index
        data_dir = data_path_for_dataset(args.data_dir, args.dataset) if args.dataset else args.data_dir
        count = build_index(data_dir, index_path)
        print(f"Indexed {count} chunks into {index_path}")
        return

    if args.command == "ask":
        index_path = index_path_for_dataset(args.index_dir, args.dataset) if args.dataset else args.index
        result = answer_question(args.question, index_path, model=args.model)
        if args.dataset:
            result["dataset"] = args.dataset
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(result["answer"])
            if result["sources"]:
                print("\nSources:")
                for source in result["sources"]:
                    print(f"- {source['source']} ({source['score']})")
        return

    if args.command == "serve":
        serve(args.index_dir, args.host, args.port, model=args.model)
        return

    if args.command == "datasets":
        for dataset in list_indexed_datasets(args.index_dir):
            print(dataset)


if __name__ == "__main__":
    main()
