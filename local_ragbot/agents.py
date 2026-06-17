from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_AGENTS_CONFIG = Path("config/agents.toml")


@dataclass(frozen=True)
class Agent:
    id: str
    display_name: str
    description: str
    task: str
    model: str
    datasets: list[str]
    allowed_tools: list[str]
    can_call: list[str]
    fallback_agent: str
    max_chunks: int
    min_score: float
    temperature: float
    output_style: str
    system_prompt: str
    route_keywords: list[str]

    # Runtime / orchestration fields.
    enabled: bool = True
    max_concurrent_jobs: int = 1
    cooldown_seconds: int = 0
    keep_warm: bool = False
    priority: int = 50


@dataclass(frozen=True)
class AgentConfig:
    defaults: dict[str, str]
    agents: dict[str, Agent]

    def get(self, agent_id: str) -> Agent:
        try:
            return self.agents[agent_id]
        except KeyError as error:
            known = ", ".join(sorted(self.agents))
            raise ValueError(f"Unknown agent '{agent_id}'. Known agents: {known}") from error

    @property
    def default_agent(self) -> Agent:
        return self.get(self.defaults.get("default_agent", "local_answerer"))


def _as_str_list(value: Any) -> list[str]:
    if not value:
        return []
    if not isinstance(value, list):
        raise ValueError(f"Expected list[str], got {type(value).__name__}")
    return [str(item) for item in value]


def _as_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().casefold() in {"1", "true", "yes", "y", "on"}
    return bool(value)


def load_agent_config(path: Path = DEFAULT_AGENTS_CONFIG) -> AgentConfig:
    if not path.exists():
        raise FileNotFoundError(f"Agent config not found: {path}")

    with path.open("rb") as file:
        payload = tomllib.load(file)

    defaults = {str(key): str(value) for key, value in payload.get("defaults", {}).items()}
    agents: dict[str, Agent] = {}

    for raw in payload.get("agents", []):
        agent = Agent(
            id=str(raw["id"]),
            display_name=str(raw.get("display_name", raw["id"])),
            description=str(raw.get("description", "")),
            task=str(raw.get("task", "")),
            model=str(raw.get("model", "")),
            datasets=_as_str_list(raw.get("datasets")),
            allowed_tools=_as_str_list(raw.get("allowed_tools")),
            can_call=_as_str_list(raw.get("can_call")),
            fallback_agent=str(raw.get("fallback_agent", "")),
            max_chunks=int(raw.get("max_chunks", 4)),
            min_score=float(raw.get("min_score", 0.12)),
            temperature=float(raw.get("temperature", 0.1)),
            output_style=str(raw.get("output_style", "concise")),
            system_prompt=str(raw.get("system_prompt", "")),
            route_keywords=_as_str_list(raw.get("route_keywords")),

            enabled=_as_bool(raw.get("enabled"), default=True),
            max_concurrent_jobs=int(raw.get("max_concurrent_jobs", 1)),
            cooldown_seconds=int(raw.get("cooldown_seconds", 0)),
            keep_warm=_as_bool(raw.get("keep_warm"), default=False),
            priority=int(raw.get("priority", 50)),
        )

        if agent.id in agents:
            raise ValueError(f"Duplicate agent id in config: {agent.id}")

        agents[agent.id] = agent

    if not agents:
        raise ValueError(f"No agents configured in {path}")

    default_agent = defaults.get("default_agent")
    if default_agent and default_agent not in agents:
        raise ValueError(f"Default agent '{default_agent}' does not exist")

    return AgentConfig(defaults=defaults, agents=agents)
