"""Loads PRINCIPLES.md. Protected: Veritas cannot edit this file or PRINCIPLES.md.

Fails closed: if the principles are missing or damaged, Veritas will not run.
"""
import hashlib
import os
import re
from pathlib import Path

DEFAULT_PATH = Path(__file__).resolve().parent.parent / "PRINCIPLES.md"
START, END = "<!-- CORE START -->", "<!-- CORE END -->"


class PrinciplesError(RuntimeError):
    pass


class Principles:
    def __init__(self, path=None):
        self.path = Path(path or os.getenv("VERITAS_PRINCIPLES") or DEFAULT_PATH)
        if not self.path.exists():
            raise PrinciplesError(f"Principles file not found at {self.path}. Veritas will not run without it.")
        text = self.path.read_text(encoding="utf-8")
        if START not in text or END not in text:
            raise PrinciplesError("PRINCIPLES.md is missing its CORE START/END markers.")
        self.core = text.split(START, 1)[1].split(END, 1)[0].strip()
        self.hard_rules = dict(re.findall(r"^- \*\*(H\d+)\*\*\s+(.+)$", self.core, re.M))
        if not self.core or not self.hard_rules:
            raise PrinciplesError("PRINCIPLES.md core section is empty or has no hard rules (H1, H2, ...).")
        self.fingerprint = hashlib.sha256(self.core.encode()).hexdigest()[:12]

    def describe(self, rule_id):
        rule_id = str(rule_id or "").strip().upper()
        return self.hard_rules.get(rule_id, "a core principle")
