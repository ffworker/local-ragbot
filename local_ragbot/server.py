from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from .datasets import index_path_for_dataset, list_indexed_datasets, validate_dataset
from .qa import answer_question


class RagHandler(BaseHTTPRequestHandler):
    index_path: Path
    index_dir: Path
    model: str | None = None

    def do_GET(self) -> None:
        if self.path == "/health":
            self._json({"ok": True})
            return
        if self.path == "/datasets":
            self._json({"datasets": list_indexed_datasets(self.index_dir)})
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
        dataset = str(payload.get("dataset", "default")).strip() or "default"
        try:
            dataset = validate_dataset(dataset)
        except ValueError as error:
            self.send_error(400, str(error))
            return

        index_path = index_path_for_dataset(self.index_dir, dataset)
        if not index_path.exists():
            self._json(
                {
                    "answer": f"Dataset '{dataset}' ist nicht indexiert.",
                    "sources": [],
                    "mode": "missing_dataset",
                    "dataset": dataset,
                }
            )
            return
        result = answer_question(question, index_path, model=self.model)
        result["dataset"] = dataset
        self._json(result)

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
<input id="dataset" value="default" placeholder="dataset"><br><br>
<textarea id="q">What is this bot allowed to answer?</textarea><br>
<button onclick="ask()">Ask</button>
<pre id="out"></pre>
<script>
async function ask(){
  const question = document.getElementById('q').value;
  const dataset = document.getElementById('dataset').value || 'default';
  const res = await fetch('/ask',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({question,dataset})});
  document.getElementById('out').textContent = JSON.stringify(await res.json(), null, 2);
}
</script>"""
        data = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def serve(index_dir: Path, host: str, port: int, model: str | None = None) -> None:
    RagHandler.index_dir = index_dir
    RagHandler.index_path = index_path_for_dataset(index_dir, "default")
    RagHandler.model = model
    server = ThreadingHTTPServer((host, port), RagHandler)
    print(f"Serving on http://{host}:{port}")
    server.serve_forever()
