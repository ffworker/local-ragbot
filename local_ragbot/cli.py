from __future__ import annotations

import argparse
import json
from pathlib import Path

from .agents import DEFAULT_AGENTS_CONFIG, load_agent_config
from .datasets import data_path_for_dataset, index_path_for_dataset, list_indexed_datasets
from .pipeline import answer_with_agent
from .retrieval import build_index
from .runtime import get_runtime
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
    ask.add_argument("--dataset", default=None)
    ask.add_argument("--index-dir", type=Path, default=Path("indexes"))
    ask.add_argument("--model", default=None)
    ask.add_argument("--agent", default=None)
    ask.add_argument("--agents-config", type=Path, default=DEFAULT_AGENTS_CONFIG)
    ask.add_argument("--json", action="store_true")

    server = sub.add_parser("serve", help="Start HTTP server")
    server.add_argument("--index-dir", type=Path, default=Path("indexes"))
    server.add_argument("--host", default="127.0.0.1")
    server.add_argument("--port", type=int, default=8088)
    server.add_argument("--model", default=None)
    server.add_argument("--agents-config", type=Path, default=DEFAULT_AGENTS_CONFIG)

    datasets = sub.add_parser("datasets", help="List indexed datasets")
    datasets.add_argument("--index-dir", type=Path, default=Path("indexes"))

    agents = sub.add_parser("agents", help="List configured agents")
    agents.add_argument("--agents-config", type=Path, default=DEFAULT_AGENTS_CONFIG)
    agents.add_argument("--json", action="store_true")

    runtime_cmd = sub.add_parser("runtime", help="Show agent runtime state")
    runtime_cmd.add_argument("--agents-config", type=Path, default=DEFAULT_AGENTS_CONFIG)
    runtime_cmd.add_argument("--json", action="store_true")

    args = parser.parse_args()

    if args.command == "ingest":
        index_path = index_path_for_dataset(args.index_dir, args.dataset) if args.dataset else args.index
        data_dir = data_path_for_dataset(args.data_dir, args.dataset) if args.dataset else args.data_dir
        count = build_index(data_dir, index_path)
        print(f"Indexed {count} chunks into {index_path}")
        return

    if args.command == "ask":
        result = answer_with_agent(
            question=args.question,
            index_dir=args.index_dir,
            config_path=args.agents_config,
            explicit_agent=args.agent,
            explicit_dataset=args.dataset,
            model_override=args.model,
        )

        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(result["answer"])

            if result.get("agent"):
                print(f"\nAgent: {result['agent']} ({result.get('mode', 'unknown')})")

            if result.get("runtime"):
                runtime = result["runtime"]
                print(
                    f"Runtime: {runtime['state']} "
                    f"jobs={runtime['active_jobs']}/{runtime['max_concurrent_jobs']}"
                )

            if result.get("sources"):
                print("\nSources:")
                for source in result["sources"]:
                    dataset = source.get("dataset")
                    prefix = f"{dataset}/" if dataset else ""
                    print(f"- {prefix}{source['source']} ({source['score']})")

        return

    if args.command == "serve":
        serve(
            args.index_dir,
            args.host,
            args.port,
            model=args.model,
            agents_config=args.agents_config,
        )
        return

    if args.command == "datasets":
        for dataset in list_indexed_datasets(args.index_dir):
            print(dataset)
        return

    if args.command == "agents":
        config = load_agent_config(args.agents_config)

        if args.json:
            print(
                json.dumps(
                    {
                        "defaults": config.defaults,
                        "agents": [
                            {
                                "id": agent.id,
                                "display_name": agent.display_name,
                                "description": agent.description,
                                "datasets": agent.datasets,
                                "model": agent.model,
                                "allowed_tools": agent.allowed_tools,
                                "can_call": agent.can_call,
                                "enabled": agent.enabled,
                                "max_concurrent_jobs": agent.max_concurrent_jobs,
                                "cooldown_seconds": agent.cooldown_seconds,
                                "keep_warm": agent.keep_warm,
                                "priority": agent.priority,
                            }
                            for agent in config.agents.values()
                        ],
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
        else:
            for agent in config.agents.values():
                status = "enabled" if agent.enabled else "disabled"
                print(
                    f"{agent.id:20} {status:8} "
                    f"jobs={agent.max_concurrent_jobs} "
                    f"model={agent.model or 'none'} "
                    f"- {agent.display_name}"
                )

        return

    if args.command == "runtime":
        config = load_agent_config(args.agents_config)
        runtime = get_runtime(config)
        snapshot = runtime.snapshot()

        if args.json:
            print(json.dumps(snapshot, ensure_ascii=False, indent=2))
        else:
            for state in snapshot["agents"]:
                print(
                    f"{state['agent']:20} {state['state']:10} "
                    f"model={state['model']} "
                    f"jobs={state['active_jobs']}/{state['max_concurrent_jobs']} "
                    f"last_used={state['last_used']}"
                )

        return


if __name__ == "__main__":
    main()
