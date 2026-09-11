from veritas import config
from veritas.trainer import chunk_text


def test_pasted_web_text_is_never_cut_off():
    text = ("Section 8.\nThe Congress shall have Power To lay and collect Taxes, Duties, Imposts and "
            "Excises, to pay the Debts and provide for the common Defence; ") * 6
    chunks = chunk_text(text)
    assert all(len(c) <= config.MEMORY_CHARS for c in chunks)  # the AI sees every piece in full
    assert "".join(chunks).replace("\n", "").replace(" ", "") == text.replace("\n", "").replace(" ", "")


def test_one_giant_unbroken_passage_is_still_split():
    assert all(len(c) <= config.MEMORY_CHARS for c in chunk_text("x" * 3000))
