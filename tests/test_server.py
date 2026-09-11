import json
import threading
import urllib.error
import urllib.request

from veritas.memory import MemoryBank
from veritas.reasoner import Reasoner
from veritas.server import build_server
from veritas.trainer import Trainer


class FakeLLM:
    model = "fake"

    def complete_json(self, system, user, max_tokens=600):
        if "fact-checker" in system:
            return {"issues": [], "adjusted_confidence": 0.9}
        return {"answer": "42", "confidence": 0.9, "basis": "general_knowledge"}


def _start(tmp_path, token=""):
    m = MemoryBank(tmp_path / "m.db")
    srv = build_server(Reasoner(FakeLLM(), m), Trainer(m), m, "127.0.0.1", 0, token=token)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}"


def _call(url, path, body=None, token=""):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url + path, data=data, headers={"Content-Type": "application/json"})
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())


def test_ask_teach_correct_over_http(tmp_path):
    srv, url = _start(tmp_path)
    try:
        assert _call(url, "/health")["ok"]
        a = _call(url, "/ask", {"question": "Meaning of life?"})
        assert a["text"] == "42" and a["model_calls"] == 2
        assert "memory_id" in _call(url, "/teach", {"fact": "Test fact"})
        _call(url, "/correct", {"answer_id": a["interaction_id"], "correction": "Nobody knows"})
        assert _call(url, "/stats")["corrections"] == 1
    finally:
        srv.shutdown()


def test_token_required_when_set(tmp_path):
    srv, url = _start(tmp_path, token="secret")
    try:
        try:
            _call(url, "/stats")
            assert False
        except urllib.error.HTTPError as e:
            assert e.code == 401
        assert "facts" in _call(url, "/stats", token="secret")
    finally:
        srv.shutdown()


def test_improve_not_exposed(tmp_path):
    srv, url = _start(tmp_path)
    try:
        _call(url, "/improve", {"goal": "x"})
        assert False
    except urllib.error.HTTPError as e:
        assert e.code == 404
    finally:
        srv.shutdown()
