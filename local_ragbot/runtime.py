from __future__ import annotations

import uuid
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from threading import Lock
from typing import Iterator

from .agents import Agent, AgentConfig


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class AgentUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class RuntimeJob:
    id: str
    agent: str
    started_at: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class AgentRuntimeState:
    agent: str
    state: str
    enabled: bool
    model: str
    active_jobs: int
    max_concurrent_jobs: int
    total_jobs: int
    failed_jobs: int
    last_used: str | None
    last_error: str | None
    current_job_id: str | None
    keep_warm: bool
    cooldown_seconds: int
    priority: int

    def to_dict(self) -> dict:
        return asdict(self)


class AgentRuntime:
    def __init__(self, config: AgentConfig) -> None:
        self._lock = Lock()
        self._states: dict[str, AgentRuntimeState] = {}

        for agent in config.agents.values():
            self._states[agent.id] = self._state_from_agent(agent)

    def _state_from_agent(self, agent: Agent) -> AgentRuntimeState:
        return AgentRuntimeState(
            agent=agent.id,
            state="idle" if agent.enabled else "disabled",
            enabled=agent.enabled,
            model=agent.model or "none",
            active_jobs=0,
            max_concurrent_jobs=max(1, agent.max_concurrent_jobs),
            total_jobs=0,
            failed_jobs=0,
            last_used=None,
            last_error=None,
            current_job_id=None,
            keep_warm=agent.keep_warm,
            cooldown_seconds=agent.cooldown_seconds,
            priority=agent.priority,
        )

    def ensure_agent(self, agent: Agent) -> AgentRuntimeState:
        with self._lock:
            if agent.id not in self._states:
                self._states[agent.id] = self._state_from_agent(agent)
            return self._states[agent.id]

    def get_state(self, agent_id: str) -> dict:
        with self._lock:
            state = self._states.get(agent_id)
            if not state:
                raise ValueError(f"Unknown runtime agent: {agent_id}")
            return state.to_dict()

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "agents": [
                    state.to_dict()
                    for state in sorted(self._states.values(), key=lambda item: item.agent)
                ]
            }

    @contextmanager
    def run_agent(self, agent: Agent) -> Iterator[RuntimeJob]:
        job = RuntimeJob(
            id=str(uuid.uuid4()),
            agent=agent.id,
            started_at=utc_now(),
        )

        with self._lock:
            state = self._states.get(agent.id)
            if not state:
                state = self._state_from_agent(agent)
                self._states[agent.id] = state

            if not state.enabled:
                raise AgentUnavailable(f"Agent '{agent.id}' is disabled")

            if state.active_jobs >= state.max_concurrent_jobs:
                raise AgentUnavailable(
                    f"Agent '{agent.id}' is busy "
                    f"({state.active_jobs}/{state.max_concurrent_jobs} active jobs)"
                )

            state.active_jobs += 1
            state.total_jobs += 1
            state.state = "busy"
            state.current_job_id = job.id
            state.last_error = None

        try:
            yield job
        except Exception as error:
            with self._lock:
                state = self._states[agent.id]
                state.failed_jobs += 1
                state.last_error = str(error)
                state.state = "error"
            raise
        finally:
            with self._lock:
                state = self._states[agent.id]
                state.active_jobs = max(0, state.active_jobs - 1)
                state.current_job_id = None
                state.last_used = utc_now()

                if state.active_jobs == 0:
                    if state.enabled:
                        state.state = "idle"
                    else:
                        state.state = "disabled"


_RUNTIME: AgentRuntime | None = None


def get_runtime(config: AgentConfig) -> AgentRuntime:
    global _RUNTIME

    if _RUNTIME is None:
        _RUNTIME = AgentRuntime(config)

    return _RUNTIME
