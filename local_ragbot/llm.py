from __future__ import annotations

import json
import urllib.error
import urllib.request


SYSTEM_PROMPT = """You are a local RAG assistant.
Answer only from the provided local context.
If the context does not contain the answer, say that the local documents do not contain it.
Keep the answer concise and cite source names from the context."""


def ollama_generate(
    prompt: str,
    model: str,
    host: str = "http://127.0.0.1:11434",
    system_prompt: str | None = None,
    temperature: float = 0.1,
    num_ctx: int = 2048,
) -> str | None:
    payload = {
        "model": model,
        "stream": False,
        "prompt": prompt,
        "system": system_prompt or SYSTEM_PROMPT,
        "options": {
            "temperature": temperature,
            "num_ctx": num_ctx,
        },
    }

    request = urllib.request.Request(
        f"{host.rstrip('/')}/api/generate",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return None

    return data.get("response")
