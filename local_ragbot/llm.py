# changed: switch Ollama calls to httpx and add streaming plus request-scoped chat history support.
from __future__ import annotations

import json
from collections.abc import Iterable, Iterator
from contextvars import ContextVar, Token
from typing import Any

import httpx


SYSTEM_PROMPT = """You are a local RAG assistant.
Answer only from the provided local context.
If the context does not contain the answer, say that the local documents do not contain it.
Keep the answer concise and cite source names from the context."""

_HISTORY: ContextVar[tuple[dict[str, str], ...]] = ContextVar("local_ragbot_history", default=())


def set_prompt_history(messages: Iterable[dict[str, str]]) -> Token[tuple[dict[str, str], ...]]:
    clean = tuple(_clean_message(message) for message in messages if _clean_message(message))
    return _HISTORY.set(clean)


def reset_prompt_history(token: Token[tuple[dict[str, str], ...]]) -> None:
    _HISTORY.reset(token)


def ollama_generate(
    prompt: str,
    model: str,
    host: str = "http://127.0.0.1:11434",
    system_prompt: str | None = None,
    temperature: float = 0.1,
    num_ctx: int = 2048,
    chat_history: Iterable[dict[str, str]] | None = None,
) -> str | None:
    payload = {
        "model": model,
        "stream": False,
        "prompt": _with_history(prompt, chat_history),
        "system": system_prompt or SYSTEM_PROMPT,
        "options": {
            "temperature": temperature,
            "num_ctx": num_ctx,
        },
    }

    try:
        with httpx.Client(timeout=120) as client:
            response = client.post(f"{host.rstrip('/')}/api/generate", json=payload)
            response.raise_for_status()
            data = response.json()
    except (httpx.HTTPError, ValueError):
        return None

    value = data.get("response")
    return str(value) if value is not None else None


def ollama_generate_stream(
    prompt: str,
    model: str,
    host: str = "http://127.0.0.1:11434",
    system_prompt: str | None = None,
    temperature: float = 0.1,
    num_ctx: int = 2048,
    chat_history: Iterable[dict[str, str]] | None = None,
) -> Iterator[str] | None:
    payload = {
        "model": model,
        "stream": True,
        "prompt": _with_history(prompt, chat_history),
        "system": system_prompt or SYSTEM_PROMPT,
        "options": {
            "temperature": temperature,
            "num_ctx": num_ctx,
        },
    }

    client = httpx.Client(timeout=httpx.Timeout(120, connect=10))
    stream = client.stream("POST", f"{host.rstrip('/')}/api/generate", json=payload)

    try:
        response = stream.__enter__()
        response.raise_for_status()
    except httpx.HTTPError:
        stream.__exit__(None, None, None)
        client.close()
        return None

    def tokens() -> Iterator[str]:
        try:
            for line in response.iter_lines():
                if not line:
                    continue

                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue

                token = data.get("response")
                if token:
                    yield str(token)

                if data.get("done"):
                    break
        finally:
            stream.__exit__(None, None, None)
            client.close()

    return tokens()


def _with_history(
    prompt: str,
    chat_history: Iterable[dict[str, str]] | None = None,
) -> str:
    messages = tuple(chat_history) if chat_history is not None else _HISTORY.get()
    history = _format_history(messages)
    if not history:
        return prompt

    return f"{history}\n\nCurrent RAG prompt:\n{prompt}"


def _format_history(messages: Iterable[dict[str, str]]) -> str:
    lines = []
    for message in messages:
        clean = _clean_message(message)
        if clean:
            lines.append(f"{clean['role']}: {clean['content']}")

    if not lines:
        return ""

    return "Conversation history, newest context for resolving follow-up questions:\n" + "\n".join(lines)


def _clean_message(message: dict[str, Any]) -> dict[str, str]:
    role = str(message.get("role", "")).strip().casefold()
    if role not in {"user", "assistant"}:
        role = "user"

    content = str(message.get("content", "")).strip()
    if not content:
        return {}

    return {"role": role, "content": content}
