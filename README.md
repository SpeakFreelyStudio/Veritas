# Veritas

An AI assistant built to help everyday people understand their rights, grounded in human rights principles and committed to being correct over sounding confident.

It runs on a small AI model on your own computer, follows a written set of principles, keeps a memory bank of trusted sources, learns from your corrections, serves a local API, and can propose and test fixes to its own code.

## How it stays factual and moral

**Principles.** [`PRINCIPLES.md`](PRINCIPLES.md) is Veritas's moral compass, drawn from the Universal Declaration of Human Rights, the Declaration of Independence, major ethical traditions, and research on human values. It has six hard rules that are never broken (like never fabricating facts, never helping anyone harm a person, and never assisting fraud) and nine weighed principles (like dignity, fairness, due process, and care for the less powerful). Run `python -m veritas principles` to see them.

**Two-step review on every question.** First, the model drafts an answer with an honest confidence score, with the principles in front of it. Then an independent review checks the draft for both factual errors and principle conflicts. The review can lower confidence but never raise it. If a hard rule would be broken, the answer is blocked.

**Higher standards for high stakes.** Legal, medical, and financial answers need 85% confidence instead of 70%. Legal answers that aren't backed by an official source in memory are capped at 60%, so Veritas says it isn't sure. Every legal answer notes that it's information, not advice, and points to legal aid.

**Trusted sources, clearly labeled.** Memories are ranked by trust: your corrections, then official legal texts, then confirmed answers, then facts you teach it, then other documents. Official sources carry a jurisdiction and date, and answers show them. See [`sources/SOURCES.md`](sources/SOURCES.md) for official links and how to load them.

**Thinks through every question.** Your corrections are given to the model as trusted evidence, but it still reasons and reviews each time. It never simply repeats a stored answer. (Optional caching exists for low-power setups, but it's off by default.)

**Guardrails it can't edit.** The self-editing feature cannot change `PRINCIPLES.md`, the code that loads it, the tests that enforce it, or the GitHub settings. If the principles file is missing or damaged, Veritas refuses to run.

## Running it on GitHub

**Automatic testing.** The included GitHub Actions workflow (`.github/workflows/tests.yml`) runs all tests on GitHub every time code is pushed, on three Python versions. Check the **Actions** tab of your repository: a green check means everything works.

**Running in your browser (Codespaces).** On your repository page, click **Code → Codespaces → Create codespace**. GitHub opens a ready-to-use environment in your browser with Python and everything installed. From its terminal, run `python -m pytest -q`, or use the cloud model with `--backend anthropic` after setting your API key. Codespaces has free monthly hours; check GitHub's current limits.

## Honest limitations

- Veritas does not contain "all the laws." It works from the official sources you load, and it tells you when it has none for a question.
- Small local models make more mistakes than large ones, so Veritas will say "I'm not sure" more often. That's the design working.
- Written principles make good behavior more likely but can't guarantee it. Human review of answers and sources is what keeps it trustworthy. Ideally, a legal aid organization would review the legal sources you load.
- "Training" means learning through memory and feedback, not retraining the model.
- During `improve`, tests run the AI's proposed code in a temporary folder before you see the diff. For stronger isolation, use Docker, a VM, or Codespaces.

## Setup on your own computer

Requires Python 3.10+ and git.

1. Install Ollama from https://ollama.com and pull a small model: `ollama pull llama3.2:3b`
2. Get Veritas and run the tests:
   ```bash
   git clone https://github.com/<you>/veritas.git
   cd veritas
   pip install pytest
   python -m pytest -q          # should say 31 passed
   ```

To use the cloud model instead: `pip install anthropic`, set `ANTHROPIC_API_KEY`, and add `--backend anthropic` to any command.

## Usage

```bash
python -m veritas chat                                  # interactive (/teach, /correct, /good, /quit)
python -m veritas ask "Can my landlord enter without notice?"
python -m veritas principles                            # show the principles it follows
python -m veritas import pa-statute.txt --official --jurisdiction PA --as-of 2026-09-10
python -m veritas import research-notes.md --distill    # non-official documents can be summarized
python -m veritas teach "Our show records on Wednesdays." --source "studio calendar"
python -m veritas correct 7 "The correct answer is 1829."
python -m veritas stats
python -m veritas forget 12
python -m veritas improve "Explain deadlines more prominently in legal answers."
python -m veritas serve                                 # local API at http://127.0.0.1:8765
```

## Local API

| Method | Path | Body | Returns |
|---|---|---|---|
| GET | `/health` | | status and model |
| GET | `/stats` | | memory stats |
| POST | `/ask` | `{"question": "..."}` | answer, confidence, domain, sources, notes, answer id |
| POST | `/teach` | `{"fact": "...", "source": "..."}` | memory id |
| POST | `/correct` | `{"answer_id": 7, "correction": "..."}` | memory id |
| POST | `/confirm` | `{"answer_id": 7}` | memory id |

By default the API only accepts connections from your own computer. To allow other devices, set `VERITAS_API_HOST=0.0.0.0` **and** `VERITAS_API_TOKEN`. Self-editing is not available over the API.

## Settings (environment variables)

| Variable | Default | Meaning |
|---|---|---|
| `VERITAS_BACKEND` | `ollama` | `ollama` (local, small) or `anthropic` (cloud, large) |
| `VERITAS_LOCAL_MODEL` | `llama3.2:3b` | Ollama model |
| `VERITAS_MIN_CONFIDENCE` | `0.7` | Bar for everyday answers |
| `VERITAS_HIGH_STAKES_CONFIDENCE` | `0.85` | Bar for legal, medical, financial answers |
| `VERITAS_LEGAL_UNSOURCED_CAP` | `0.6` | Max confidence for legal answers without an official source |
| `VERITAS_LEGAL_REFERRAL` | PALawHelp.org | Where legal answers send people for help |
| `VERITAS_PRINCIPLES` | `PRINCIPLES.md` | Path to the principles file |
| `VERITAS_CACHE` | `0` | Set to `1` to reuse answers when nothing has changed |
| `VERITAS_IMPROVE_BACKEND` | `anthropic` | Model used for self-editing |
| `VERITAS_API_HOST` / `_PORT` / `_TOKEN` | `127.0.0.1` / `8765` / none | API server |

## Project layout

```
PRINCIPLES.md            moral compass (human-edited only)
sources/SOURCES.md       official legal sources and how to load them
veritas/
  reasoner.py            draft -> facts + principles review -> answer, abstain, or block
  principles.py          loads PRINCIPLES.md; refuses to run without it (protected)
  memory.py              SQLite memory with trust levels, jurisdictions, and dates
  trainer.py             teach, correct, confirm, import
  llm.py                 local (Ollama) and cloud backends
  server.py              local HTTP API
  self_improve.py        propose -> sandbox test -> diff -> approve -> git branch (protected)
  cli.py, config.py
tests/                   31 tests, including principle enforcement (protected)
.github/workflows/       runs the tests on GitHub automatically (protected)
.devcontainer/           one-click Codespaces setup
```
