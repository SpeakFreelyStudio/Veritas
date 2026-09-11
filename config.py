"""Settings. Override any of these with environment variables."""
import os

# ---- Which AI "brain" to use ------------------------------------------------
# "ollama" = small model on your own computer (low energy, private, free)
# "anthropic" = large cloud model (more capable, needs an API key)
BACKEND = os.getenv("VERITAS_BACKEND", "ollama")
IMPROVE_BACKEND = os.getenv("VERITAS_IMPROVE_BACKEND", "anthropic")
LOCAL_MODEL = os.getenv("VERITAS_LOCAL_MODEL", "llama3.2:3b")
OLLAMA_URL = os.getenv("VERITAS_OLLAMA_URL", "http://localhost:11434")
MODEL = os.getenv("VERITAS_MODEL", "claude-sonnet-5")

# ---- Honesty and stakes -----------------------------------------------------
MIN_CONFIDENCE = float(os.getenv("VERITAS_MIN_CONFIDENCE", "0.7"))
# Legal, medical, and financial answers must clear a higher bar.
HIGH_STAKES_CONFIDENCE = float(os.getenv("VERITAS_HIGH_STAKES_CONFIDENCE", "0.85"))
# A legal answer not backed by an official source in memory can't exceed this confidence.
LEGAL_UNSOURCED_CAP = float(os.getenv("VERITAS_LEGAL_UNSOURCED_CAP", "0.6"))
LEGAL_REFERRAL = os.getenv(
    "VERITAS_LEGAL_REFERRAL",
    "a legal aid organization or a lawyer (in Pennsylvania, PALawHelp.org lists free legal help)",
)

# How much Veritas trusts each kind of memory.
TRUST = {
    "correction": 0.95,  # you corrected an answer
    "official": 0.90,    # primary sources: statutes, regulations, constitutions, court opinions
    "confirmed": 0.85,   # you confirmed an answer was right
    "fact": 0.80,        # something you taught it
    "document": 0.75,    # other imported documents
}

# ---- Efficiency --------------------------------------------------------------
DB_PATH = os.getenv("VERITAS_DB", "veritas_memory.db")
MEMORY_RESULTS = int(os.getenv("VERITAS_MEMORY_RESULTS", "5"))
MEMORY_CHARS = int(os.getenv("VERITAS_MEMORY_CHARS", "500"))
ANSWER_TOKENS = int(os.getenv("VERITAS_ANSWER_TOKENS", "700"))
VERIFY_TOKENS = int(os.getenv("VERITAS_VERIFY_TOKENS", "300"))
# Off by default so Veritas thinks through every question. Turn on to reuse answers
# when neither the question, memory, nor principles have changed.
CACHE = os.getenv("VERITAS_CACHE", "0") == "1"

# ---- API server --------------------------------------------------------------
API_HOST = os.getenv("VERITAS_API_HOST", "127.0.0.1")
API_PORT = int(os.getenv("VERITAS_API_PORT", "8765"))
API_TOKEN = os.getenv("VERITAS_API_TOKEN", "")
