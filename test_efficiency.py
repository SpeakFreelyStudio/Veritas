from veritas.memory import MemoryBank
from veritas.reasoner import Reasoner
from veritas.trainer import Trainer


class CountingLLM:
    model = "fake"

    def __init__(self):
        self.calls = 0
        self.prompts = []

    def complete_json(self, system, user, max_tokens=600):
        self.calls += 1
        self.prompts.append(user)
        if "fact-checker" in system:
            return {"issues": [], "adjusted_confidence": 0.9}
        return {"answer": "Paris", "confidence": 0.95, "basis": "general_knowledge", "domain": "general"}


def test_every_question_is_thought_through_by_default(tmp_path):
    llm = CountingLLM()
    r = Reasoner(llm, MemoryBank(tmp_path / "m.db"))
    r.ask("What is the capital of France?")
    r.ask("What is the capital of France?")
    assert llm.calls == 4  # no shortcuts unless you turn caching on


def test_optional_cache_when_enabled(tmp_path):
    llm = CountingLLM()
    r = Reasoner(llm, MemoryBank(tmp_path / "m.db"), use_cache=True)
    r.ask("What is the capital of France?")
    second = r.ask("what is the capital of france")
    assert second.route == "cache" and llm.calls == 2


def test_new_memory_invalidates_cache(tmp_path):
    m = MemoryBank(tmp_path / "m.db")
    r = Reasoner(CountingLLM(), m, use_cache=True)
    r.ask("What is the capital of France?")
    m.add("Some new fact about France.")
    assert r.ask("What is the capital of France?").route == "reasoned"


def test_corrections_become_evidence_not_shortcuts(tmp_path):
    m = MemoryBank(tmp_path / "m.db")
    llm = CountingLLM()
    r = Reasoner(llm, m)
    a = r.ask("Capital of Australia?")
    Trainer(m).correct(a.interaction_id, "Canberra")
    before = llm.calls
    r.ask("Capital of Australia?")
    assert llm.calls == before + 2                     # still reasoned and reviewed
    assert "Canberra" in llm.prompts[-2] and "correction" in llm.prompts[-2]  # correction given as evidence


def test_cannot_confirm_a_non_answer(tmp_path):
    m = MemoryBank(tmp_path / "m.db")
    iid = m.log_interaction("q", "I'm not confident enough to answer that reliably.", 0.2)
    try:
        Trainer(m).confirm(iid)
        assert False, "should have refused"
    except ValueError:
        pass


def test_stats_count_ai_calls(tmp_path):
    m = MemoryBank(tmp_path / "m.db")
    Reasoner(CountingLLM(), m).ask("What is the capital of France?")
    s = m.stats()
    assert s["questions_answered"] == 1 and s["total_ai_calls"] == 2
