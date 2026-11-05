#!/usr/bin/env python3
"""Write .claude/settings.json: the lesson-log hooks, pointed at this computer's Python
and this vault's scripts/lesson_log.py.

Run once after cloning (and again if the vault moves or Python changes):
    python scripts/setup_hooks.py
"""
import json
import sys
from pathlib import Path

VAULT = Path(__file__).resolve().parent.parent
EVENTS = [
    ("UserPromptSubmit", None),
    ("PreToolUse", "AskUserQuestion"),
    ("PostToolUse", "AskUserQuestion|Bash|PowerShell"),
    ("Stop", None),
]


def settings(python=sys.executable, vault=VAULT):
    hook = {"type": "command", "command": str(python),
            "args": [str(Path(vault) / "scripts" / "lesson_log.py"), "hook"], "timeout": 15}
    out = {}
    for event, matcher in EVENTS:
        entry = {"hooks": [dict(hook)]}
        if matcher:
            entry = {"matcher": matcher, **entry}
        out[event] = [entry]
    return {"hooks": out}


def main():
    path = VAULT / ".claude" / "settings.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(settings(), indent=2) + "\n", encoding="utf-8")
    print("wrote", path)


if __name__ == "__main__":
    main()
