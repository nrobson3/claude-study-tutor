#!/usr/bin/env python3
"""Keep the vault and its GitHub repo in step.

Commands
    pull
        Pull the latest from GitHub (rebase, autostash). Safe to run any time.
    push [-m MESSAGE]
        Rebuild the course maps, keep files over 50 MB out of git (they are
        added to .gitignore and listed), commit everything else and push.
        Refuses to run in the middle of a rebase or merge, or on a detached HEAD.

Meant for a PRIVATE vault repo: the slides and past tests in it belong to their authors.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

VAULT = Path(__file__).resolve().parent.parent
LIMIT_MB = 50
LARGE_MARKER = "# Large files kept on this laptop only (added by scripts/sync.py)"
SKIP_DIRS = {".git", ".cache", "__pycache__", ".trash"}
GIT_ENV = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}  # never hang on a credential prompt
GIT_TIMEOUT = 120


def git(*args: str, check: bool = True, stdin: str | None = None) -> subprocess.CompletedProcess:
    try:
        proc = subprocess.run(
            ["git", *args], cwd=VAULT, text=True, capture_output=True, encoding="utf-8",
            errors="replace", env=GIT_ENV, timeout=GIT_TIMEOUT, input=stdin,
        )
    except subprocess.TimeoutExpired:
        sys.exit(f"git {' '.join(args)} timed out after {GIT_TIMEOUT} s (network or sign-in problem?)")
    if check and proc.returncode != 0:
        sys.stderr.write(proc.stdout + proc.stderr)
        sys.exit(f"git {' '.join(args)} failed")
    return proc


def has_remote() -> bool:
    return bool(git("remote", check=False).stdout.strip())


def branch() -> str:
    """Current branch name (works before the first commit); "HEAD" when detached."""
    proc = git("symbolic-ref", "--short", "-q", "HEAD", check=False)
    return proc.stdout.strip() if proc.returncode == 0 and proc.stdout.strip() else "HEAD"


def has_upstream() -> bool:
    return git("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}", check=False).returncode == 0


def unfinished_operation() -> str | None:
    gitdir = Path(git("rev-parse", "--git-dir").stdout.strip())
    if not gitdir.is_absolute():
        gitdir = VAULT / gitdir
    for name, what in (("rebase-merge", "a rebase"), ("rebase-apply", "a rebase"),
                       ("MERGE_HEAD", "a merge"), ("CHERRY_PICK_HEAD", "a cherry-pick")):
        if (gitdir / name).exists():
            return what
    if branch() == "HEAD":
        return "a detached HEAD"
    return None


def cmd_pull(_args) -> None:
    if not has_remote():
        print("No GitHub remote yet; nothing to pull.")
        return
    problem = unfinished_operation()
    if problem:
        sys.exit(f"The repo is in the middle of {problem}. Sort that out (git status) before pulling.")
    if has_upstream():
        proc = git("pull", "--rebase", "--autostash", check=False)
    else:
        b = branch()
        exists = git("ls-remote", "--heads", "origin", b, check=False)
        if exists.returncode != 0:
            sys.exit("Couldn't reach GitHub: " + (exists.stderr.strip() or "unknown error"))
        if not exists.stdout.strip():
            print(f"GitHub has no '{b}' branch yet; nothing to pull.")
            return
        proc = git("pull", "--rebase", "--autostash", "origin", b, check=False)
    out = (proc.stdout + proc.stderr).strip()
    if proc.returncode != 0:
        sys.stderr.write(out + "\n")
        if unfinished_operation():
            sys.exit("Pull stopped on a conflict. Resolve it (git status), then run the pull again.")
        sys.exit("Pull failed (see the message above).")
    print(out or "Up to date.")


def large_files() -> list[str]:
    """Vault-relative paths of files over the limit: untracked ones on disk, and tracked ones."""
    limit = LIMIT_MB * 1024 * 1024
    found: set[str] = set()
    for root, dirs, files in os.walk(VAULT):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for fname in files:
            p = Path(root) / fname
            try:
                if p.stat().st_size > limit:
                    found.add(p.relative_to(VAULT).as_posix())
            except OSError:
                continue
    return sorted(found)


def tracked(paths: list[str]) -> set[str]:
    if not paths:
        return set()
    out = git("ls-files", "-z", "--", *paths, check=False).stdout
    return {p for p in out.split("\0") if p}


def ignored(paths: list[str]) -> set[str]:
    if not paths:
        return set()
    # -z needs --stdin; it keeps unusual file names unquoted.
    out = git("check-ignore", "-z", "--stdin", "--no-index", check=False, stdin="\0".join(paths) + "\0").stdout
    return {p for p in out.split("\0") if p}


def keep_large_local(paths: list[str]) -> list[str]:
    if not paths:
        return []
    already = ignored(paths)
    in_git = tracked(paths)
    new = [p for p in paths if p not in already]
    if new:
        gi = VAULT / ".gitignore"
        text = gi.read_text(encoding="utf-8") if gi.exists() else ""
        if LARGE_MARKER not in text:
            text = text.rstrip("\n") + "\n\n" + LARGE_MARKER + "\n"
        for r in new:
            escaped = "".join("\\" + ch if ch in "[]*?!#" else ch for ch in r)
            text = text.rstrip("\n") + "\n/" + escaped + "\n"
        gi.write_text(text, encoding="utf-8")
    for r in paths:
        if r in in_git:  # stop tracking it, keep the file on disk
            git("rm", "--cached", "--quiet", "--", r, check=False)
    return [p for p in paths if p in new or p in in_git]


def rebuild_maps() -> None:
    graph = VAULT / "scripts" / "graph.py"
    if graph.exists():
        proc = subprocess.run([sys.executable, str(graph), "maps"], cwd=VAULT, text=True,
                              capture_output=True, encoding="utf-8", errors="replace")
        if proc.returncode != 0:
            sys.stderr.write(proc.stdout + proc.stderr)
            print("(maps not rebuilt; continuing with the push)")


def cmd_push(args) -> None:
    problem = unfinished_operation()
    if problem:
        sys.exit(f"Not pushing: the repo is in the middle of {problem}. Sort that out (git status) first.")
    rebuild_maps()
    for r in keep_large_local(large_files()):
        print(f"Kept local only (over {LIMIT_MB} MB): {r}")
    git("add", "-A")
    staged = [p for p in git("diff", "--cached", "--name-only", "-z").stdout.split("\0") if p]
    if not staged:
        print("Nothing to commit.")
    else:
        message = args.message or f"Study session {datetime.now():%Y-%m-%d %H:%M}"
        git("commit", "-q", "-m", message)
        print(f"Committed {len(staged)} file(s): {message}")
    if not has_remote():
        print("No GitHub remote yet; committed locally only.")
        return
    proc = git("push", check=False) if has_upstream() else git("push", "-u", "origin", branch(), check=False)
    if proc.returncode != 0:
        sys.stderr.write(proc.stdout + proc.stderr)
        sys.exit("Push failed. Run  python scripts/sync.py pull  and push again.")
    print("Pushed to GitHub.")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Sync the study vault with GitHub")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("pull").set_defaults(func=cmd_pull)
    p = sub.add_parser("push")
    p.add_argument("-m", "--message", help="commit message")
    p.set_defaults(func=cmd_push)
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()
