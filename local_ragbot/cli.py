from __future__ import annotations

import argparse
import json
from pathlib import Path

from .qa import answer_question
from .retrieval import build_index
from .server import serve


def main() -> None:
    parser = argparse.ArgumentParser(prog="local-ragbot")
    sub = parser.add_subparsers(dest="command", required=True)

    ingest = sub.add_parser("ingest", help="Index local documents")
    ingest.add_argument("data_dir", type=Path)
    ingest.add_argument("--index", type=Path, default=Path("indexes/default.json"))

    ask = sub.add_parser("ask", help="Ask a question")
    ask.add_argument("question")
    ask.add_argument("--index", type=Path, default=Path("indexes/default.json"))
    ask.add_argument("--model", default=None)
    ask.add_argument("--json", action="store_true")

    server = sub.add_parser("serve", help="Start HTTP server")
    server.add_argument("--index", type=Path, default=Path("indexes/default.json"))
    server.add_argument("--host", default="127.0.0.1")
    server.add_argument("--port", type=int, default=8088)
    server.add_argument("--model", default=None)

    args = parser.parse_args()

    if args.command == "ingest":
        count = build_index(args.data_dir, args.index)
        print(f"Indexed {count} chunks into {args.index}")
        return

    if args.command == "ask":
        result = answer_question(args.question, args.index, model=args.model)
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
        serve(args.index, args.host, args.port, model=args.model)


if __name__ == "__main__":
    main()

