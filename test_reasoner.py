from veritas.memory import MemoryBank
from veritas.reasoner import Reasoner
from veritas.trainer import Trainer


class FakeLLM:
    def __init__(self, *responses):
        self.responses = list(responses)

    def complete_json(self, system, user, max_tokens=2000):
        return self.responses.pop(0)


def test_answers_when_confident_and_drops_fake_citations(tmp_path):
    m = MemoryBank(tmp_path / "m.db")
    fid = m.add("Water boils at 100 C at sea level.")
    llm = FakeLLM(
        {"answer": "100 C", "confidence": 0.95, "basis": "memory", "citations": [fid, 999]},
        {"issues": [], "adjusted_confidence": 0.93},
    )
    a = Reasoner(llm, m, min_confidence=0.7).ask("At what temperature does water boil?")
    assert not a.abstained and a.text == "100 C"
    assert a.citations == [fid]  # 999 was invented, so it's removed
    assert a.confidence == 0.93


def test_abstains_when_fact_checker_disagrees(tmp_path):
    m = MemoryBank(tmp_path / "m.db")
    llm = FakeLLM(
        {"answer": "It was 1842.", "confidence": 0.9, "basis": "general_knowledge"},
        {"issues": ["Date is unsupported"], "adjusted_confidence": 0.4},
    )
    a = Reasoner(llm, m, min_confidence=0.7).ask("When was it founded?")
    assert a.abstained and "not confident" in a.text


def test_bad_json_means_abstain(tmp_path):
    class Broken:
        def complete_json(self, *a, **k):
            raise ValueError("garbage")

    a = Reasoner(Broken(), MemoryBank(tmp_path / "m.db")).ask("anything")
    assert a.abstained and a.confidence == 0.0


def test_correction_becomes_trusted_memory(tmp_path):
    m = MemoryBank(tmp_path / "m.db")
    iid = m.log_interaction("Capital of Australia?", "Sydney", 0.8)
    fid = Trainer(m).correct(iid, "Canberra")
    fact = m.get(fid)
    assert "Canberra" in fact.content and fact.trust >= 0.9
