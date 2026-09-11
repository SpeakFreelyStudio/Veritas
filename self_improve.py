"""Lets Veritas read and propose fixes to its own code — with guardrails.

Safety design:
  1. Proposed edits are tested in a temporary copy, never your real files.
  2. Protected: tests/, PRINCIPLES.md, veritas/principles.py, .github/, and this file.
     The AI cannot edit its own guardrails, its principles, or delete tests to make them pass.
  3. You see the full diff and must approve it.
  4. Approved changes go on a new git branch, so any change can be undone.
"""
import difflib
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

PROTECTED = ("veritas/self_improve.py", "veritas/principles.py", "PRINCIPLES.md", "tests/", ".github/")
EDITABLE_DIR = "veritas/"
MAX_ATTEMPTS = 3

IMPROVE_SYSTEM = """You are improving the source code of Veritas, the program you are running inside.
Make the smallest change that achieves the goal. All existing tests must keep passing.
Never weaken honesty, the principles review, or the legal safeguards.
You may NOT edit tests/, PRINCIPLES.md, veritas/principles.py, or veritas/self_improve.py.
Respond ONLY with JSON:
{"summary": "...", "changes": [{"path": "veritas/<file>.py", "new_content": "<complete new file contents>"}]}"""


def is_allowed(rel_path):
    rel = str(rel_path).replace("\\", "/")
    if rel.startswith("/") or ".." in rel.split("/"):
        return False
    if not rel.startswith(EDITABLE_DIR) or not rel.endswith(".py"):
        return False
    return not any(rel == p or rel.startswith(p) for p in PROTECTED)


def _git(root, *args):
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True)


def _run_tests(root):
    r = subprocess.run(
        [sys.executable, "-m", "pytest", "-q"], cwd=root, capture_output=True, text=True, timeout=600
    )
    return r.returncode == 0, (r.stdout + r.stderr)[-4000:]


def _read_own_code(root):
    files = sorted(p for p in (root / "veritas").rglob("*.py") if "__pycache__" not in p.parts)
    return "\n\n".join(f"### FILE: {p.relative_to(root).as_posix()}\n{p.read_text()}" for p in files)


def improve(goal, llm, root=".", approve=None, log=print):
    root = Path(root).resolve()
    if approve is None:
        approve = lambda: input("Apply these changes? [y/N] ").strip().lower() == "y"

    if _git(root, "rev-parse", "--is-inside-work-tree").returncode != 0:
        return "Self-improvement needs the project to be a git repository (so changes can be undone)."
    if _git(root, "status", "--porcelain", "--untracked-files=no").stdout.strip():
        return "You have uncommitted changes. Commit or stash them first."

    code = _read_own_code(root)
    feedback = ""
    for attempt in range(1, MAX_ATTEMPTS + 1):
        log(f"Attempt {attempt}: asking for a proposed change...")
        try:
            plan = llm.complete_json(IMPROVE_SYSTEM, f"GOAL: {goal}\n\nCURRENT CODE:\n{code}{feedback}", max_tokens=16000)
        except Exception as e:
            feedback = f"\n\nYour last response was not valid JSON ({e}). Respond with JSON only."
            continue

        changes = [c for c in plan.get("changes", []) if isinstance(c, dict)]
        blocked = [c.get("path") for c in changes if not is_allowed(c.get("path", ""))]
        if not changes or blocked:
            feedback = f"\n\nRejected: no changes, or edits to forbidden paths {blocked}. Only edit files under veritas/ (not self_improve.py)."
            continue

        with tempfile.TemporaryDirectory() as tmp:
            sandbox = Path(tmp) / "repo"
            shutil.copytree(root, sandbox, ignore=shutil.ignore_patterns(".git", "*.db", "__pycache__", ".venv", "venv"))
            for c in changes:
                target = sandbox / c["path"]
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(c["new_content"])
            passed, output = _run_tests(sandbox)

        if not passed:
            log("  Tests failed in the sandbox; asking it to fix its own mistake...")
            feedback = f"\n\nYour previous attempt failed the tests:\n{output}\nFix the problem."
            continue

        log(f"\nProposed change: {plan.get('summary', '(no summary)')}\n")
        for c in changes:
            path = root / c["path"]
            old = path.read_text() if path.exists() else ""
            log("".join(difflib.unified_diff(
                old.splitlines(True), c["new_content"].splitlines(True),
                f"a/{c['path']}", f"b/{c['path']}")))
        log("All tests passed in the sandbox.")

        if not approve():
            return "Changes discarded. Nothing was modified."

        base = _git(root, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip() or "main"
        branch = f"veritas-self-edit-{int(time.time())}"
        _git(root, "checkout", "-b", branch)
        for c in changes:
            target = root / c["path"]
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(c["new_content"])
            _git(root, "add", c["path"])
        _git(root, "commit", "-m", f"Veritas self-edit: {plan.get('summary', goal)[:70]}")
        return (f"Committed on branch '{branch}'.\n"
                f"Keep it:  git checkout {base} && git merge {branch}\n"
                f"Undo it:  git checkout {base} && git branch -D {branch}")

    return f"Couldn't produce a change that passes the tests after {MAX_ATTEMPTS} attempts. Nothing was modified."
