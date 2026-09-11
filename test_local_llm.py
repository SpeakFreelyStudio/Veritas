import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from veritas.llm import LocalLLM


def test_local_llm_talks_to_ollama_format():
    seen = {}

    class FakeOllama(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_POST(self):
            seen["path"] = self.path
            seen["body"] = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            out = json.dumps({"message": {"role": "assistant", "content": '{"answer": "hi"}'}}).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(out)))
            self.end_headers()
            self.wfile.write(out)

    srv = HTTPServer(("127.0.0.1", 0), FakeOllama)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        llm = LocalLLM(model="tiny", url=f"http://127.0.0.1:{srv.server_address[1]}")
        assert llm.complete_json("sys", "user", max_tokens=123) == {"answer": "hi"}
        b = seen["body"]
        assert seen["path"] == "/api/chat" and b["model"] == "tiny" and b["format"] == "json"
        assert b["options"]["num_predict"] == 123 and b["stream"] is False
    finally:
        srv.shutdown()


def test_helpful_error_when_ollama_is_off():
    llm = LocalLLM(model="tiny", url="http://127.0.0.1:1")
    try:
        llm.complete("s", "u")
        assert False
    except RuntimeError as e:
        assert "Is it running" in str(e)
