from veritas.memory import MemoryBank
from veritas.reasoner import ANSWER_SYSTEM, VERIFY_SYSTEM, Reasoner, _clean_notes


class ScriptedLLM:
    model = "fake"

    def __init__(self, draft, review):
        self.draft, self.review = draft, review

    def complete_json(self, system, user, max_tokens=600):
        return self.review if "fact-checker" in system else self.draft


def test_echoed_labels_and_blanks_are_removed():
    notes = ["hard_line_violated", "none", "", "H2", "...", "N/A",
             "Quote omits the petition clause.", "Quote omits the petition clause."]
    assert _clean_notes(notes) == ["Quote omits the petition clause"]


def test_real_notes_survive_the_real_bug(tmp_path):
    m = MemoryBank(tmp_path / "m.db")
    fid = m.add("Congress shall make no law ... abridging the freedom of speech", kind="official", trust=0.9)
    llm = ScriptedLLM(
        {"answer": "The First Amendment protects free speech.", "confidence": 1.0, "domain": "legal",
         "basis": f"m{fid}", "citations": [f"m{fid}"], "uncertainties": []},
        {"issues": ["Does not mention that it limits only the government."], "adjusted_confidence": 0.9,
         "principle_concerns": ["hard_line_violated"], "hard_line_violated": False, "rule": ""},
    )
    a = Reasoner(llm, m).ask("What does the Constitution say about freedom of speech?")
    assert a.principle_concerns == []                       # the nonsense note is gone
    assert a.issues == ["Does not mention that it limits only the government"]
    assert a.basis == "memory" and a.citations == [fid] and not a.abstained


def test_instructions_ask_for_plain_language_and_on_topic_review():
    assert "plain-language" in ANSWER_SYSTEM and "exactly from MEMORY" in ANSWER_SYSTEM
    assert "THIS question" in VERIFY_SYSTEM


def test_question_about_a_rights_document_is_not_treated_as_legal(tmp_path):
    m = MemoryBank(tmp_path / "m.db")
    fid = m.add("Everyone has the right to education. Education shall be free, at least in the elementary stages.",
                source="udhr.txt", kind="document", trust=0.75)
    llm = ScriptedLLM({"answer": "Article 26 says everyone has the right to education.", "confidence": 0.9,
                       "domain": "general", "basis": "memory", "citations": [fid]},
                      {"issues": [], "adjusted_confidence": 0.85})
    a = Reasoner(llm, m).ask("What does the Universal Declaration of Human Rights say about education?")
    assert a.domain == "general" and not a.abstained
    assert "not legal advice" not in a.text


def test_real_legal_questions_are_still_caught():
    from veritas.reasoner import looks_legal
    assert looks_legal("Can my landlord keep my security deposit?")
    assert looks_legal("What happens if I'm arrested?")
