"""How Veritas learns: taught facts, corrections, confirmations, and imported documents."""
import re
from pathlib import Path

from . import config

DISTILL_SYSTEM = """Extract standalone, atomic factual statements from the text below.
Only include claims the text itself makes. Do not add outside knowledge or interpretation.
Each fact must make sense on its own (replace pronouns with names).
Respond ONLY with JSON: {"facts": ["..."]}"""


def _split_long(text, max_chars):
    """Break an oversized passage at sentence ends (or spaces) so nothing gets cut off."""
    pieces, current = [], ""
    for sentence in re.split(r"(?<=[.;:!?])\s+", text):
        while len(sentence) > max_chars:  # one enormous sentence: split at a space
            cut = sentence.rfind(" ", 0, max_chars)
            cut = cut if cut > 0 else max_chars
            if current:
                pieces.append(current)
                current = ""
            pieces.append(sentence[:cut].strip())
            sentence = sentence[cut:].strip()
        if current and len(current) + len(sentence) + 1 > max_chars:
            pieces.append(current)
            current = ""
        current = f"{current} {sentence}".strip()
    if current:
        pieces.append(current)
    return pieces


# Lines like "Article 26", "Article. I.", "Section. 8.", "Amendment XIV", "§ 250.501", "Chapter 3"
HEADING = re.compile(r"^(article|section|amendment|chapter|part|§)\b\.?\s*[\dIVXLCivxlc]+", re.IGNORECASE)


def chunk_text(text, max_chars=None):
    """Split a document into pieces small enough that the AI always sees each one in full.
    A new piece starts at every Article, Section, or Amendment heading, so each one stays whole
    and never gets mixed with its neighbors."""
    max_chars = max_chars or config.MEMORY_CHARS
    lines = []
    for line in (l.strip() for l in re.split(r"\n+", text)):
        if line:
            lines.extend(_split_long(line, max_chars) if len(line) > max_chars else [line])
    chunks, current = [], ""
    for line in lines:
        if current and (HEADING.match(line) or len(current) + len(line) + 1 > max_chars):
            chunks.append(current)
            current = ""
        current = f"{current}\n{line}".strip()
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
