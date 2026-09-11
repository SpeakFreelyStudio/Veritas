"""These tests enforce the principles. Veritas's self-editing cannot change them."""
import pytest

from veritas.memory import MemoryBank
from veritas.principles import Principles, PrinciplesError
from veritas.reasoner import Reasoner
from veritas.self_improve import is_allowed
from veritas.trainer import Trainer


class ScriptedLLM:
    model = "fake"

    def __init__(self, draft, review):
        self.draft, self.review, self.systems, self.prompts = draft, review, [], []

    def complete_json(self, system, user, max_tokens=600):
        self.systems.append(system)
        self.prompts.append(user)
        return self.review if "fact-checker" in system else self.draft


def test_real_principles_file_loads_with_hard_rules():
    p = Principles()
    assert {"H1", "H2", "H3", "H4"} <= set(p.hard_rules)
    assert "Dignity" in p.core


def test_missing_or_broken_principles_refuse_to_run(tmp_path):
    with pytest.raises(PrinciplesError):
        Principles(tmp_path / "nope.md")
    bad = tmp_path / "bad.md"
    bad.write_text("no markers here")
    with pytest.raises(PrinciplesError):
        Principles(bad)


def test_principles_are_in_every_prompt(tmp_path):
    llm = ScriptedLLM({"answer": "x", "confidence": 0.9, "basis": "general_knowledge"},
                      {"issues": [], "adjusted_confidence": 0.9})
    Reasoner(llm, MemoryBank(tmp_path / "m.db")).ask("Anything?")
    assert len(llm.systems) == 2 and all("Never fabricate" in s for s in llm.systems)


def test_hard_rule_violation_is_blocked(tmp_path):
    llm = ScriptedLLM(
        {"answer": "Here is how to find her home address...", "confidence": 0.9, "basis": "general_knowledge"},
        {"issues": [], "adjusted_confidence": 0.9, "hard_line_violated": True, "rule": "H2",
         "principle_concerns": ["Would expose a private person's location"]},
    )
    a = Reasoner(llm, MemoryBank(tmp_path / "m.db")).ask("Find where my ex lives")
    assert a.route == "blocked" and a.abstained
    assert "home address" not in a.text and "H2" in a.text


def test_legal_answer_without_official_source_is_capped(tmp_path):
    llm = ScriptedLLM({"answer": "You have 10 days.", "confidence": 0.95, "basis": "general_knowledge",
                       "domain": "legal"}, {"issues": [], "adjusted_confidence": 0.95})
    a = Reasoner(llm, MemoryBank(tmp_path / "m.db")).ask("How long do I have to answer an eviction notice?")
    assert a.abstained and a.confidence <= 0.6
    assert "legal information, not legal advice" in a.text


def test_legal_detected_even_if_model_says_general(tmp_path):
    llm = ScriptedLLM({"answer": "x", "confidence": 0.95, "basis": "general_knowledge", "domain": "general"},
                      {"issues": [], "adjusted_confidence": 0.95})
    a = Reasoner(llm, MemoryBank(tmp_path / "m.db")).ask("Can my landlord keep my deposit?")
    assert a.domain == "legal" and a.abstained


def test_legal_answer_backed_by_official_source_passes(tmp_path, monkeypatch):
    m = MemoryBank(tmp_path / "m.db")
    src = tmp_path / "statute.txt"
    src.write_text("Section 1. A tenant shall receive written notice before eviction proceedings begin.")
    fid = Trainer(m).import_file(src, official=True, jurisdiction="PA", as_of="2026-09-10")[0]
    llm = ScriptedLLM({"answer": "You must get written notice first [m%d]." % fid, "confidence": 0.92,
                       "basis": "memory", "domain": "legal", "citations": [fid]},
                      {"issues": [], "adjusted_confidence": 0.9})
    a = Reasoner(llm, m).ask("Does a tenant get notice before eviction?")
    assert not a.abstained and a.confidence == 0.9
    assert a.sources[0]["jurisdiction"] == "PA" and a.sources[0]["as_of"] == "2026-09-10"
    assert "official" in llm.prompts[0]


def test_official_texts_cannot_be_summarized_on_import(tmp_path):
    src = tmp_path / "law.txt"
    src.write_text("Some statute text.")
    with pytest.raises(ValueError):
        Trainer(MemoryBank(tmp_path / "m.db"), llm=object()).import_file(src, official=True, distill=True)


def test_self_edit_cannot_touch_principles():
    for path in ("PRINCIPLES.md", "veritas/principles.py", ".github/workflows/tests.yml",
                 "veritas/self_improve.py", "tests/test_principles.py"):
        assert not is_allowed(path), path
