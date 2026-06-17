from __future__ import annotations

from .agents import Agent, AgentConfig


def route_agent(
    question: str,
    config: AgentConfig,
    explicit_agent: str | None = None,
    explicit_dataset: str | None = None,
) -> Agent:
    if explicit_agent:
        return config.get(explicit_agent)

    if explicit_dataset:
        for agent in config.agents.values():
            if explicit_dataset in agent.datasets and "retrieve" in agent.allowed_tools:
                return agent

    question_lower = question.casefold()
    best_agent: Agent | None = None
    best_score = 0

    for agent in config.agents.values():
        if "retrieve" not in agent.allowed_tools:
            continue

        score = sum(1 for keyword in agent.route_keywords if keyword.casefold() in question_lower)

        if score > best_score:
            best_score = score
            best_agent = agent

    return best_agent or config.default_agent
