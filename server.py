"""A lightweight local HTTP API for Veritas. Standard library only; no web framework needed.

Endpoints (JSON in, JSON out):
  GET  /health                          -> {"ok": true, ...}
  GET  /stats                           -> memory and energy-saving stats
  POST /ask      {"question": "..."}    -> answer, confidence, domain, sources, principle notes
  POST /teach    {"fact": "...", "source": "..."}
  POST /correct  {"answer_id": 7, "correction": "..."}
  POST /confirm  {"answer_id": 7}

Self-editing (`improve`) is deliberately NOT exposed over the network.
Requests are handled one at a time, which suits small hardware: a local model
can only think about one thing at a time anyway.
"""
import hmac
import json
import threading
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import config

MAX_BODY = 1_000_000


def make_handler(reasoner, trainer, memory, token="", backend_name=""):
    lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass  # quiet

        def _send(self, code, obj):
            body = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _authorized(self):
            if not token:
                return True
            given = self.headers.get("Authorization", "").removeprefix("Bearer ").strip()
            return hmac.compare_digest(given, token)

        def _json(self):
            n = int(self.headers.get("Content-Length", 0))
            if n > MAX_BODY:
                raise ValueError("Request too large")
            return json.loads(self.rfile.read(n) or b"{}")

        def do_GET(self):
            if not self._authorized():
                return self._send(401, {"error": "unauthorized"})
            if self.path == "/health":
                return self._send(200, {"ok": True, "backend": backend_name})
            if self.path == "/stats":
                with lock:
                    return self._send(200, memory.stats())
            self._send(404, {"error": "not found"})

        def do_POST(self):
            if not self._authorized():
                return self._send(401, {"error": "unauthorized"})
            try:
                data = self._json()
                with lock:
                    if self.path == "/ask":
                        q = str(data.get("question", "")).strip()
                        if not q:
                            return self._send(400, {"error": "'question' is required"})
                        return self._send(200, asdict(reasoner.ask(q)))
                    if self.path == "/teach":
                        fid = trainer.teach(str(data["fact"]), source=str(data.get("source", "api")))
                        return self._send(200, {"memory_id": fid})
                    if self.path == "/correct":
                        fid = trainer.correct(int(data["answer_id"]), str(data["correction"]))
                        return self._send(200, {"memory_id": fid})
                    if self.path == "/confirm":
                        return self._send(200, {"memory_id": trainer.confirm(int(data["answer_id"]))})
                self._send(404, {"error": "not found"})
            except (KeyError, ValueError, TypeError) as e:
                self._send(400, {"error": str(e)})
            except Exception as e:
                self._send(500, {"error": str(e)})

    return Handler


def build_server(reasoner, trainer, memory, host=None, port=None, token=None, backend_name=""):
    handler = make_handler(reasoner, trainer, memory, config.API_TOKEN if token is None else token, backend_name)
    return ThreadingHTTPServer((host or config.API_HOST, config.API_PORT if port is None else port), handler)


def serve(backend=None, host=None, port=None):
    from .llm import make_llm
    from .memory import MemoryBank
    from .reasoner import Reasoner
    from .trainer import Trainer

    memory = MemoryBank(config.DB_PATH)
    llm = make_llm(backend)
    name = f"{backend or config.BACKEND}:{getattr(llm, 'model', '?')}"
    server = build_server(Reasoner(llm, memory), Trainer(memory, llm), memory, host, port, backend_name=name)
    h, p = server.server_address[:2]
    print(f"Veritas API running at http://{h}:{p}  (brain: {name})  Ctrl+C to stop.")
    if h not in ("127.0.0.1", "localhost") and not config.API_TOKEN:
        print("WARNING: reachable from other devices with no VERITAS_API_TOKEN set.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
