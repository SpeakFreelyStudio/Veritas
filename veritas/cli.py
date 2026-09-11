"""Command-line interface. Run `python -m veritas --help`."""
import argparse
import json
import sys

from . import config
from .memory import MemoryBank


def _memory():
    return MemoryBank(config.DB_PATH)


_BACKEND = None  # set by --backend


def _llm(backend=None):
    from .llm import make_llm
    return make_llm(backend or _BACKEND or config.BACKEND)


def print_answer(a):
    print(f"\n{a.text}")
    meta = f"[confidence {a.confidence:.0%} | {a.domain}"
    if a.route == "cache":
        meta += " | reused earlier answer"
    print(meta + f" | answer #{a.interaction_id}]")
    for s in a.sources:
        where = ", ".join(x for x in (s.get("jurisdiction"), f"as of {s['as_of']}" if s.get("as_of") else None) if x)
        print(f"  Source m{s['id']}: {s['source']} ({s['kind']}{', ' + where if where else ''})")
    if not a.abstained:
        for issue in a.issues[:3]:
            print(f"  ! Fact-check note: {issue}")
        for c in a.principle_concerns[:3]:
            print(f"  ! Principles note: {c}")


def cmd_ask(args):
    from .reasoner import Reasoner
    print_answer(Reasoner(_llm(), _memory()).ask(args.question))


def cmd_chat(args):
    from .reasoner import Reasoner
    from .trainer import Trainer
    mem, llm = _memory(), _llm()
    reasoner, trainer = Reasoner(llm, mem), Trainer(mem, llm)
    last = None
    print("Veritas chat. Commands: /teach <fact>  /correct <right answer>  /good  /quit")
    while True:
        try:
            line = input("\nyou> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not line:
            continue
        if line == "/quit":
            break
        try:
            if line.startswith("/teach "):
                print(f"Stored as memory m{trainer.teach(line[7:])}.")
            elif line.startswith(("/correct", "/good")) and last is None:
                print("Ask a question first, then /correct or /good applies to my answer.")
            elif line.startswith("/correct "):
                print(f"Thanks. Stored correction as memory m{trainer.correct(last, line[9:])}.")
            elif line == "/good":
                print(f"Confirmed and stored as memory m{trainer.confirm(last)}.")
            elif line.startswith("/"):
                print("Commands: /teach <fact>  /correct <right answer>  /good  /quit")
            else:
                a = reasoner.ask(line)
                last = a.interaction_id
                print_answer(a)
        except (ValueError, RuntimeError) as e:
            print(f"Error: {e}")


def cmd_teach(args):
    from .trainer import Trainer
    print(f"Stored as memory m{Trainer(_memory()).teach(args.fact, source=args.source)}.")


def cmd_correct(args):
    from .trainer import Trainer
    print(f"Stored correction as memory m{Trainer(_memory()).correct(args.answer_id, args.correction)}.")


def cmd_import(args):
    from .trainer import Trainer
    llm = _llm() if args.distill else None
    ids = Trainer(_memory(), llm).import_file(
        args.path, distill=args.distill, official=args.official,
        jurisdiction=args.jurisdiction, as_of=args.as_of)
    kind = "official source" if args.official else "document"
    print(f"Imported {len(ids)} memories from {args.path} as {kind}.")


def cmd_forget(args):
    print("Forgotten." if _memory().forget(args.memory_id) else "No such memory.")


def cmd_principles(args):
    from .principles import Principles
    p = Principles()
    print(p.core)
    print(f"\n(principles file: {p.path} | fingerprint {p.fingerprint})")


def cmd_sources(args):
    rows = _memory().sources()
    if not rows:
        print("No documents loaded yet.")
    for r in rows:
        where = ", ".join(x for x in (r["jurisdiction"], f"as of {r['as_of']}" if r["as_of"] else None) if x)
        print(f"{r['source']}: {r['pieces']} pieces ({r['kind']}{', ' + where if where else ''})")


def cmd_forget_source(args):
    n = _memory().forget_source(args.source)
    print(f"Removed {n} memories from {args.source}." if n else f"No memories found from '{args.source}'. "
          "Run `python3 -m veritas sources` to see the exact names.")


def cmd_stats(args):
    print(json.dumps(_memory().stats(), indent=2))


def cmd_improve(args):
    from .self_improve import improve
    print(improve(args.goal, _llm(_BACKEND or config.IMPROVE_BACKEND), root=args.root))


def cmd_serve(args):
    from .server import serve
    serve(backend=_BACKEND, host=args.host, port=args.port)


def main(argv=None):
    p = argparse.ArgumentParser(prog="veritas", description="An assistant that prefers correct over confident.")
    p.add_argument("--backend", choices=["ollama", "anthropic"],
                   help="AI brain: 'ollama' (small, local, low energy) or 'anthropic' (large, cloud)")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("ask", help="Ask one question"); s.add_argument("question"); s.set_defaults(fn=cmd_ask)
    s = sub.add_parser("chat", help="Interactive chat"); s.set_defaults(fn=cmd_chat)
    s = sub.add_parser("teach", help="Add a fact to memory"); s.add_argument("fact")
    s.add_argument("--source", default="user"); s.set_defaults(fn=cmd_teach)
    s = sub.add_parser("correct", help="Correct a past answer"); s.add_argument("answer_id", type=int)
    s.add_argument("correction"); s.set_defaults(fn=cmd_correct)
    s = sub.add_parser("import", help="Import a .txt/.md document into memory"); s.add_argument("path")
    s.add_argument("--distill", action="store_true", help="Use the AI to break it into atomic facts")
    s.add_argument("--official", action="store_true",
                   help="Primary legal/government source (statute, regulation, constitution, court opinion)")
    s.add_argument("--jurisdiction", help="Where it applies, e.g. US or PA")
    s.add_argument("--as-of", dest="as_of", help="Date you copied it from the official site, e.g. 2026-09-10")
    s.set_defaults(fn=cmd_import)
    s = sub.add_parser("forget", help="Delete a memory"); s.add_argument("memory_id", type=int); s.set_defaults(fn=cmd_forget)
    s = sub.add_parser("principles", help="Show the principles Veritas follows"); s.set_defaults(fn=cmd_principles)
    s = sub.add_parser("sources", help="List loaded documents"); s.set_defaults(fn=cmd_sources)
    s = sub.add_parser("forget-source", help="Remove everything loaded from one document")
    s.add_argument("source"); s.set_defaults(fn=cmd_forget_source)
    s = sub.add_parser("stats", help="Memory bank stats"); s.set_defaults(fn=cmd_stats)
    s = sub.add_parser("improve", help="Have Veritas propose a fix to its own code")
    s.add_argument("goal"); s.add_argument("--root", default="."); s.set_defaults(fn=cmd_improve)

    s = sub.add_parser("serve", help="Run the local HTTP API")
    s.add_argument("--host"); s.add_argument("--port", type=int); s.set_defaults(fn=cmd_serve)

    args = p.parse_args(argv)
    global _BACKEND
    _BACKEND = args.backend
    try:
        args.fn(args)
    except (ValueError, RuntimeError, FileNotFoundError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main(sys.argv[1:])
