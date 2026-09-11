"""How Veritas learns: taught facts, corrections, confirmations, and imported documents."""
from pathlib import Path

from . import config

DISTILL_SYSTEM = """Extract standalone, atomic factual statements from the text below.
Only include claims the text itself makes. Do not add outside knowledge or interpretation.
Each fact must make sense on its own (replace pronouns with names).
Respond ONLY with JSON: {"facts": ["..."]}"""


def chunk_text(text, max_chars=1000):
    chunks, current = [], ""
    for para in (p.strip() for p in text.split("\n\n")):
        if not para:
            continue
        if current and len(current) + len(para) > max_chars:
            chunks.append(current)
            current = ""
        current = f"{current}\n\n{para}".strip()
    if current:
        chunks.append(current)
    return chunks


class Trainer:
    def __init__(self, memory, llm=None):
        self.memory = memory
        self.llm = llm

    def teach(self, fact, source="user", trust=None):
        return self.memory.add(fact, source, trust or config.TRUST["fact"], kind="fact")

    def correct(self, interaction_id, correction):
        row = self.memory.get_interaction(interaction_id)
        if row is None:
            raise ValueError(f"No interaction #{interaction_id}")
        self.memory.set_feedback(interaction_id, f"corrected: {correction}")
        return self.memory.add(
            f"Q: {row['question']} | Correct answer: {correction}",
            source=f"user correction of #{interaction_id}",
            trust=config.TRUST["correction"], kind="correction",
        )

    def confirm(self, interaction_id):
        row = self.memory.get_interaction(interaction_id)
        if row is None:
            raise ValueError(f"No interaction #{interaction_id}")
        if row["answer"].startswith(("I'm not confident enough", "I can't help with this")):
            raise ValueError("That reply wasn't an answer. Use correct() to give the right answer instead.")
        self.memory.set_feedback(interaction_id, "confirmed")
        return self.memory.add(
            f"Q: {row['question']} | Confirmed answer: {row['answer']}",
            source=f"user-confirmed #{interaction_id}",
            trust=config.TRUST["confirmed"], kind="confirmed",
        )

    def import_file(self, path, distill=False, official=False, jurisdiction=None, as_of=None):
        """official=True marks primary sources (statutes, regulations, constitutions, court opinions).
        Official texts are stored word-for-word; summarizing them could change their legal meaning."""
        if official and distill:
            raise ValueError("Official legal texts must be imported word-for-word. Remove --distill.")
        path = Path(path)
        text = path.read_text(encoding="utf-8", errors="ignore")
        kind = "official" if official else "document"
        ids = []
        for chunk in chunk_text(text):
            facts = self.llm.complete_json(DISTILL_SYSTEM, chunk).get("facts", []) if (distill and self.llm) else [chunk]
            for fact in facts:
                if str(fact).strip():
                    ids.append(self.memory.add(str(fact), source=path.name, trust=config.TRUST[kind],
                                               kind=kind, jurisdiction=jurisdiction, as_of=as_of))
        return ids
