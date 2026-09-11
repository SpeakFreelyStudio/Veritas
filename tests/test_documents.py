from veritas.memory import MemoryBank
from veritas.reasoner import VERIFY_SYSTEM
from veritas.trainer import Trainer, chunk_text

UDHR_25_27 = """Article 25
Everyone has the right to a standard of living adequate for the health and well-being of himself and of his family, including food, clothing, housing and medical care and necessary social services.
Motherhood and childhood are entitled to special care and assistance.
Article 26
Everyone has the right to education. Education shall be free, at least in the elementary and fundamental stages. Elementary education shall be compulsory.
Education shall be directed to the full development of the human personality.
Parents have a prior right to choose the kind of education that shall be given to their children.
Article 27
Everyone has the right freely to participate in the cultural life of the community."""


def test_each_article_stays_whole_and_separate():
    pieces = chunk_text(UDHR_25_27)
    art26 = [p for p in pieces if p.startswith("Article 26")]
    assert len(art26) == 1
    assert "right to education" in art26[0] and "Parents have a prior right" in art26[0]
    assert "cultural life" not in art26[0] and "standard of living" not in art26[0]


def test_constitution_style_headings_are_recognized():
    text = "Article. I.\nSection. 1.\nAll legislative Powers...\nSection. 2.\nThe House of Representatives...\nAmendment I\nCongress shall make no law..."
    pieces = chunk_text(text)
    assert any(p.startswith("Section. 2.") for p in pieces) and any(p.startswith("Amendment I") for p in pieces)


def test_forget_source_removes_a_whole_document_for_reloading(tmp_path):
    m = MemoryBank(tmp_path / "m.db")
    doc = tmp_path / "udhr.txt"
    doc.write_text(UDHR_25_27)
    t = Trainer(m)
    t.import_file(doc)
    m.add("Unrelated fact about rivers.", source="notes")
    loaded = {r["source"]: r["pieces"] for r in m.sources()}
    assert loaded["udhr.txt"] == 3 and loaded["notes"] == 1
    assert m.forget_source("udhr.txt") == 3
    assert [r["source"] for r in m.sources()] == ["notes"] and m.search("education") == []


def test_reviewer_counts_a_missing_main_point_as_a_real_problem():
    assert "main point" in VERIFY_SYSTEM and "lower your confidence" in VERIFY_SYSTEM
