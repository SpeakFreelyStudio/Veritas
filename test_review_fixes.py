"""Regression tests for problems found in code review. Each one was a real, reproduced bug."""
import socket
import subprocess
import threading
from pathlib import Path

import pytest

import veritas.self_improve as si
from veritas.llm import extract_json
from veritas.memory import MemoryBank
from veritas.reasoner import Reasoner
from veritas.server import build_server
from veritas.trainer import Trainer


class ScriptedLLM:
    model = "fake"

    def __init__(self, draft, review):
        self.draft, self.review = draft, review

    def complete_json(self, system, user, max_tokens=600):
        if "fact-checker" in system:
            if isinstance(self.review, Exception):
                raise self.review
            return self.review
        return self.draft


# 1. Self-editing could bypass protections
@pytest.mark.parametrize("path", [
    "veritas/Self_Improve.py", "VERITAS/principles.py", "veritas//self_improve.py",
    "veritas/./principles.py", "veritas/principles.py ", "veritas/conftest.py",
    "veritas/sitecustomize.py", "veritas\\principles.py", "veritas/../tests/x.py",
])
def test_protection_bypass_attempts_are_rejected(path):
    assert not si.is_allowed(path)


def test_normal_edits_still_allowed():
    assert si.is_allowed("veritas/memory.py") and si.is_allowed("veritas/tools/calc.py")


# 2. Hard-rule flag written as a string
@pytest.mark.parametrize("flag", ["true", "True", "yes", 1])
def test_hard_rule_flag_as_string_still_blocks(tmp_path, flag):
    llm = ScriptedLLM({"answer": "harmful steps", "confidence": 0.9, "basis": "general_knowledge"},
                      {"adjusted_confidence": 0.9, "hard_line_violated": flag, "rule": "H2"})
    a = Reasoner(llm, MemoryBank(tmp_path / "m.db")).ask("x")
    assert a.route == "blocked" and "harmful steps" not in a.text


# 3. Review failure must fail closed
def test_failed_review_never_shows_unreviewed_answer(tmp_path):
    llm = ScriptedLLM({"answer": "harmful steps", "confidence": 0.95, "basis": "general_knowledge"},
                      RuntimeError("timeout"))
    a = Reasoner(llm, MemoryBank(tmp_path / "m.db")).ask("x")
    assert a.abstained and "harmful steps" not in a.text


# 4. Strings where lists were expected
def test_string_fields_are_not_split_into_letters(tmp_path):
    m = MemoryBank(tmp_path / "m.db")
    ids = [m.add(f"fact number {i}") for i in range(12)]
    llm = ScriptedLLM({"answer": "ok", "confidence": 0.9, "basis": "memory",
                       "citations": str(ids[-1]), "uncertainties": "date unclear"},
                      {"adjusted_confidence": 0.9, "issues": "minor wording"})
    a = Reasoner(llm, m).ask("fact number")
    assert a.uncertainties == ["date unclear"] and a.issues == ["minor wording"]
    assert a.citations in ([ids[-1]], [])  # never split "12" into 1 and 2


def test_json_found_even_with_braces_in_prose():
    assert extract_json('Note {not json}. Answer: {"a": 1} done') == {"a": 1}


# 5 & 6. API robustness
def _server(tmp_path):
    m = MemoryBank(tmp_path / "m.db")
    srv = build_server(Reasoner(ScriptedLLM({}, {}), m), Trainer(m), m, "127.0.0.1", 0, token="secret")
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def _raw(port, data):
    s = socket.create_connection(("127.0.0.1", port))
    s.settimeout(5)
    s.sendall(data)
    try:
        return s.recv(100).decode(errors="replace").split("\r\n")[0]
    finally:
        s.close()


def test_negative_content_length_rejected_quickly(tmp_path):
    srv = _server(tmp_path)
    try:
        line = _raw(srv.server_address[1], b"POST /ask HTTP/1.1\r\nHost: x\r\n"
                    b"Authorization: Bearer secret\r\nContent-Length: -1\r\n\r\n")
        assert " 400 " in line
    finally:
        srv.shutdown()


def test_non_ascii_password_is_rejected_not_crashed(tmp_path):
    srv = _server(tmp_path)
    try:
        req = "GET /stats HTTP/1.1\r\nHost: x\r\nAuthorization: Bearer caf\u00e9\r\n\r\n".encode("latin-1")
        assert " 401 " in _raw(srv.server_address[1], req)
    finally:
        srv.shutdown()


# 7. Failed save must be reported and fully undone
def test_failed_commit_is_reported_and_undone(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    (repo / "veritas").mkdir(parents=True)
    (repo / "veritas" / "config.py").write_text("X = 1\n")
    env = ["-c", "user.email=t@t", "-c", "user.name=t"]
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", *env, "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", *env, "commit", "-qm", "init"], cwd=repo, check=True)
    base = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=repo,
                          capture_output=True, text=True).stdout.strip()

    real_git = si._git

    def git_that_cannot_commit(root, *args):
        if args and args[0] == "commit":
            return subprocess.CompletedProcess(args, 1, "", "Please tell me who you are.")
        return real_git(root, *args)

    monkeypatch.setattr(si, "_git", git_that_cannot_commit)
    monkeypatch.setattr(si, "_run_tests", lambda root: (True, ""))

    class LLM:
        def complete_json(self, *a, **k):
            return {"summary": "t", "changes": [{"path": "veritas/config.py", "new_content": "X = 2\n"}]}

    msg = si.improve("x", LLM(), repo, approve=lambda: True, log=lambda *a: None)
    assert "couldn't be saved" in msg
    assert (repo / "veritas" / "config.py").read_text() == "X = 1\n"
    status = real_git(repo, "status", "--porcelain").stdout.strip()
    branch = real_git(repo, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    assert status == "" and branch == base
