from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .qa import answer_question


class RagHandler(BaseHTTPRequestHandler):
    index_path: Path
    model: str | None = None

    def do_GET(self) -> None:
        if self.path == "/health":
            self._json({"ok": True})
            return
        if self.path == "/":
            self._html()
            return
        self.send_error(404)

    def do_POST(self) -> None:
        if urlparse(self.path).path != "/ask":
            self.send_error(404)
            return

        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length).decode("utf-8")
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            self.send_error(400, "Invalid JSON")
            return

        question = str(payload.get("question", "")).strip()
        if not question:
            self.send_error(400, "Missing question")
            return
        self._json(answer_question(question, self.index_path, model=self.model))

    def _json(self, payload: dict) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _html(self) -> None:
        html = """<!doctype html>
<meta charset="utf-8">
<title>Local RAG Bot</title>
<style>
body{font-family:system-ui,sans-serif;max-width:760px;margin:40px auto;padding:0 16px;line-height:1.4}
textarea{width:100%;min-height:90px}button{padding:8px 14px}pre{white-space:pre-wrap;background:#f6f6f6;padding:12px}
</style>
<h1>Local RAG Bot</h1>
<textarea id="q">What is this bot allowed to answer?</textarea><br>
<button onclick="ask()">Ask</button>
<pre id="out"></pre>
<script>
async function ask(){
  const question = document.getElementById('q').value;
  const res = await fetch('/ask',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({question})});
  document.getElementById('out').textContent = JSON.stringify(await res.json(), null, 2);
}
</script>"""
        data = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def serve(index_path: Path, host: str, port: int, model: str | None = None) -> None:
    RagHandler.index_path = index_path
    RagHandler.model = model
    server = ThreadingHTTPServer((host, port), RagHandler)
    print(f"Serving on http://{host}:{port}")
    server.serve_forever()

