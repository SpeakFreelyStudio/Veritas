"""Answers questions, reviews its own work for facts and principles, and abstains when unsure.

Every question is thought through by the model. Memory (including your corrections) is
given to the model as trusted evidence; it is never used to skip the thinking or the review.
"""
import hashlib
import re
from dataclasses import asdict, dataclass, field

from . import config
from .memory import normalize
from .principles import Principles

ANSWER_SYSTEM = """You are Veritas. Being correct matters more than sounding confident.

PRINCIPLES (follow these):
<<PRINCIPLES>>

Use MEMORY when relevant and cite memory numbers (12 for [m12]). Memories marked "official" are primary
legal or government texts; "correction" memories are fixes from the user and are highly trusted.
Never invent names, numbers, dates, quotes, laws, cases, or sources. If you don't know, say so.
For legal questions: name the jurisdiction the answer applies to, point out any deadlines, and say when
the person should contact legal aid or a lawyer.
If a request would break a hard rule, decline it and offer a lawful, ethical alternative.
"confidence" = honest probability (0-1) that your answer is fully correct.
"domain" = legal, medical, financial, or general.
Reply ONLY with JSON: {"answer":"...","confidence":0.0,"domain":"general","basis":"memory|general_knowledge|mixed|unknown","citations":[12],"uncertainties":["..."]}"""

VERIFY_SYSTEM = """You are a strict fact-checker and principles reviewer. Check the DRAFT answer.

PRINCIPLES:
<<PRINCIPLES>>

1. Facts: list claims unsupported by MEMORY, likely wrong, or stated more confidently than the evidence allows.
2. Principles: list any conflicts with the principles. Set "hard_line_violated" to true ONLY if the draft,
   or fulfilling the request, would break a rule marked H; put that rule's id (like "H2") in "rule".
3. Give your honest probability (0-1) that the draft is fully correct.
Reply ONLY with JSON: {"issues":["..."],"adjusted_confidence":0.0,"principle_concerns":["..."],"hard_line_violated":false,"rule":""}"""

HIGH_STAKES = {"legal", "medical", "financial"}
LEGAL_TERMS = {
    "law", "laws", "legal", "illegal", "court", "courts", "judge", "sue", "sued", "lawsuit", "lawyer",
    "attorney", "evict", "eviction", "landlord", "tenant", "lease", "statute", "rights", "arrest",
    "police", "warrant", "custody", "contract", "wage", "wages", "overtime", "fired", "discrimination",
    "appeal", "benefits", "unemployment", "subpoena", "constitution", "constitutional", "amendment",
    "criminal", "charges", "bail", "probation", "immigration", "deport", "foreclosure", "debt",
}


@dataclass
class Answer:
    text: str
    confidence: float
    basis: str
    citations: list = field(default_factory=list)
    uncertainties: list = field(default_factory=list)
    issues: list = field(default_factory=list)
    abstained: bool = False
    interaction_id: int | None = None
    route: str = "reasoned"  # "reasoned", "blocked", or "cache"
    model_calls: int = 0
    domain: str = "general"
    principle_concerns: list = field(default_factory=list)
    sources: list = field(default_factory=list)


CACHEABLE = ("text", "confidence", "basis", "citations", "uncertainties", "issues", "abstained",
             "domain", "principle_concerns", "sources")


def _clamp(x):
    try:
        return max(0.0, min(1.0, float(x)))
    except (TypeError, ValueError):
        return 0.0


def _ids(values):
    out = []
    for v in values or []:
        m = re.search(r"\d+", str(v))
        if m:
            out.append(int(m.group()))
    return out


def looks_legal(question):
    words = set(re.findall(r"[a-z]+", question.lower()))
    return bool(words & LEGAL_TERMS)


class Reasoner:
    def __init__(self, llm, memory, min_confidence=None, use_cache=None, principles=None):
        self.llm = llm
        self.memory = memory
        self.min_confidence = config.MIN_CONFIDENCE if min_confidence is None else min_confidence
        self.use_cache = config.CACHE if use_cache is None else use_cache
        self.principles = principles or Principles()  # fails closed if missing
        self.answer_system = ANSWER_SYSTEM.replace("<<PRINCIPLES>>", self.principles.core)
        self.verify_system = VERIFY_SYSTEM.replace("<<PRINCIPLES>>", self.principles.core)

    def ask(self, question):
        key = None
        if self.use_cache:
            raw = "|".join([normalize(question), str(self.memory.version()), getattr(self.llm, "model", "?"),
                            str(self.min_confidence), self.principles.fingerprint])
            key = hashlib.sha256(raw.encode()).hexdigest()
            cached = self.memory.cache_get(key)
            if cached:
                return self._finish(question, Answer(**cached, route="cache"))
        result = self._reason(question)
        if key and result.route == "reasoned":
            self.memory.cache_put(key, {k: v for k, v in asdict(result).items() if k in CACHEABLE})
        return self._finish(question, result)

    # ------------------------------------------------------------------------
    def _reason(self, question):
        facts = self.memory.search(question, k=config.MEMORY_RESULTS)
        mem = self._format(facts)

        try:
            draft = self.llm.complete_json(
                self.answer_system, f"MEMORY:\n{mem}\n\nQUESTION: {question}", max_tokens=config.ANSWER_TOKENS
            )
        except Exception as e:
            return Answer(f"I couldn't produce a reliable answer ({e}).", 0.0, "unknown",
                          abstained=True, model_calls=1)

        answer_text = str(draft.get("answer", "")).strip()
        stated = _clamp(draft.get("confidence", 0))
        domain = str(draft.get("domain", "general")).lower()
        if domain not in HIGH_STAKES and looks_legal(question):
            domain = "legal"

        try:
            check = self.llm.complete_json(
                self.verify_system,
                f"QUESTION: {question}\nMEMORY:\n{mem}\nDRAFT: {answer_text}\nSTATED CONFIDENCE: {stated}",
                max_tokens=config.VERIFY_TOKENS,
            )
        except Exception:
            check = {"issues": ["Review step failed; confidence reduced."],
                     "adjusted_confidence": stated * 0.8}

        # Hard rules: block outright.
        if check.get("hard_line_violated") is True:
            rule = str(check.get("rule", "")).upper()
            text = (f"I can't help with this as asked, because it conflicts with a core principle "
                    f"({rule or 'hard rule'}: {self.principles.describe(rule)}).\n"
                    "If you're dealing with an unfair situation, I can help you understand your rights "
                    "and the lawful ways to respond.")
            return Answer(text, 0.0, "principles", abstained=True, route="blocked", model_calls=2,
                          domain=domain, principle_concerns=list(check.get("principle_concerns", [])))

        final = min(stated, _clamp(check.get("adjusted_confidence", stated)))  # review can only lower
        by_id = {f.id: f for f in facts}
        citations = [c for c in _ids(draft.get("citations")) if c in by_id]
        cited = [by_id[c] for c in citations]
        uncertainties = [str(u) for u in draft.get("uncertainties", [])]
        issues = [str(i) for i in check.get("issues", [])]
        concerns = [str(c) for c in check.get("principle_concerns", [])]

        if domain == "legal" and not any(f.kind == "official" for f in cited):
            final = min(final, config.LEGAL_UNSOURCED_CAP)
            uncertainties.append("Not verified against an official legal source in my memory.")

        threshold = max(self.min_confidence, config.HIGH_STAKES_CONFIDENCE) if domain in HIGH_STAKES \
            else self.min_confidence
        basis = draft.get("basis", "unknown")
        sources = [{"id": f.id, "kind": f.kind, "source": f.source,
                    "jurisdiction": f.jurisdiction, "as_of": f.as_of} for f in cited]

        result = Answer(answer_text, final, basis, citations, uncertainties, issues,
                        model_calls=2, domain=domain, principle_concerns=concerns, sources=sources)
        if final < threshold or basis == "unknown" or not answer_text:
            result.abstained = True
            result.text = self._abstain(answer_text, final, uncertainties + issues)
        if domain == "legal":
            result.text += (f"\n\nThis is legal information, not legal advice. Laws differ by state and change "
                            f"over time, and deadlines can be short. For help with your situation, contact "
                            f"{config.LEGAL_REFERRAL}.")
        return result

    def _finish(self, question, result):
        result.interaction_id = self.memory.log_interaction(
            question, result.text, result.confidence, result.model_calls
        )
        return result

    @staticmethod
    def _format(facts):
        if not facts:
            return "(none)"
        n = config.MEMORY_CHARS
        lines = []
        for f in facts:
            tags = [f.kind]
            if f.jurisdiction:
                tags.append(f.jurisdiction)
            if f.as_of:
                tags.append(f"as of {f.as_of}")
            lines.append(f"[m{f.id}] ({', '.join(tags)}; trust {f.trust:.2f}) {f.content[:n]}")
        return "\n".join(lines)

    @staticmethod
    def _abstain(tentative, confidence, concerns):
        lines = [f"I'm not confident enough to answer that reliably (confidence about {confidence:.0%})."]
        if tentative and confidence >= 0.3:
            lines.append(f"My best unverified understanding: {tentative}")
        if concerns:
            lines.append("What's holding me back: " + "; ".join(concerns[:3]))
        lines.append("You can teach me a reliable source, then ask again.")
        return "\n".join(lines)
